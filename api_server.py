"""
Headless Serial API Server for IWR6843AOP Radar.
Exposes a Serial API that responds to 'GET_DATA' with a JSON line.
"""

import time
import serial
import threading
import json
import sys
import numpy as np

from settings import *
from config_sender import send_selected_config
from uart_parser import AutoRadarUARTParser
from filters import TrackHistory, GhostTargetFilter
from pointcloud_processing import VirtualTargetTracker, TemporalPointCloudStabilizer

# Global lock and latest frame data storage
frame_lock = threading.Lock()
latest_frame_data = {
    "frame_number": 0,
    "presence": False,
    "point_cloud": [],
    "targets": [],
    "mode": "WAITING"
}

# Diagnostic metrics
telemetry = {
    "status": "INIT",
    "port_cfg": CFG_PORT,
    "port_data": DATA_PORT,
    "port_api": API_SERIAL_PORT if ENABLE_SERIAL_API else "DISABLED",
    "total_bytes_received": 0,
    "total_parsed_frames": 0,
    "bad_packets": 0,
    "last_update_time": 0.0
}


def radar_collector_thread():
    """
    Thread 1: Configures the radar, reads DATA UART, processes frames with filters,
    and updates the global frame buffer.
    """
    global latest_frame_data

    print("[RADAR COLLECTOR] Thread started.")

    # 1. Config sending phase
    if not SKIP_CONFIG:
        try:
            print("[RADAR COLLECTOR] Sending configuration...")
            send_selected_config()
            time.sleep(0.5)
        except Exception as e:
            print(f"[RADAR COLLECTOR] Error sending config: {e}", file=sys.stderr)
            telemetry["status"] = "ERROR_CONFIG"
            return
    else:
        print("[RADAR COLLECTOR] SKIP_CONFIG is True. Skipping config send.")

    # 2. Open DATA UART Port
    print(f"[RADAR COLLECTOR] Opening DATA port {DATA_PORT} at {DATA_BAUDRATE}")
    try:
        data_ser = serial.Serial(DATA_PORT, DATA_BAUDRATE, timeout=0, write_timeout=0)
        data_ser.reset_input_buffer()
        telemetry["status"] = "RUNNING"
    except Exception as e:
        print(f"[RADAR COLLECTOR] Error opening DATA port {DATA_PORT}: {e}", file=sys.stderr)
        telemetry["status"] = "ERROR_PORT"
        return

    # 3. Initialize processors & filters
    parser = AutoRadarUARTParser()
    track_history = TrackHistory(max_len=80, max_missing_frames=12)
    pointcloud_stabilizer = TemporalPointCloudStabilizer()
    ghost_filter = GhostTargetFilter(
        max_missing_frames=GHOST_MAX_MISSING_FRAMES,
        min_support_points=GHOST_MIN_SUPPORT_POINTS,
        support_radius_x=GHOST_SUPPORT_RADIUS_X,
        support_radius_y=GHOST_SUPPORT_RADIUS_Y,
        support_radius_z=GHOST_SUPPORT_RADIUS_Z,
        duplicate_distance_xy=GHOST_DUPLICATE_DISTANCE_XY,
        drop_unsupported_immediately=GHOST_DROP_UNSUPPORTED_IMMEDIATELY,
        confirm_frames=TARGET_CONFIRM_FRAMES,
        apply_confirmation_to_firmware_targets=APPLY_CONFIRMATION_TO_FIRMWARE_TARGETS,
        enable_smoothing=ENABLE_TARGET_SMOOTHING,
        smoothing_alpha=TARGET_SMOOTHING_ALPHA,
        smoothing_reset_distance=TARGET_SMOOTHING_RESET_DISTANCE
    )
    virtual_tracker = VirtualTargetTracker()

    print("[RADAR COLLECTOR] Entering read loop...")

    try:
        while True:
            # Read bytes from DATA port
            bytes_waiting = data_ser.in_waiting
            if bytes_waiting > 0:
                data = data_ser.read(bytes_waiting)
                parser.append_data(data)
                telemetry["total_bytes_received"] = parser.total_bytes_received
                telemetry["bad_packets"] = parser.bad_packets

            # Parse frames
            frames = parser.parse_available_frames()

            for frame in frames:
                header = frame["header"]
                frame_number = header.get("frameNumber", 0)

                point_cloud = frame["point_cloud"]
                raw_targets = frame["targets"]
                target_index = frame.get("target_index", np.empty((0,), dtype=np.uint8))

                # Apply temporal point-cloud stabilizer
                if ENABLE_POINTCLOUD_TEMPORAL_STABILIZER:
                    point_cloud_for_detection = pointcloud_stabilizer.update(
                        point_cloud,
                        frame_number=frame_number
                    )
                else:
                    point_cloud_for_detection = point_cloud

                # Track and merge point cloud clusters
                if ENABLE_POINTCLOUD_HUMAN_PROCESSOR:
                    candidate_targets, display_point_cloud, _ = virtual_tracker.track_and_build(
                        raw_targets=raw_targets,
                        point_cloud=point_cloud_for_detection,
                        target_index=target_index,
                        frame_number=frame_number
                    )
                else:
                    candidate_targets = raw_targets
                    display_point_cloud = point_cloud_for_detection

                # Ghost target filter
                if ENABLE_GHOST_TARGET_FILTER:
                    targets = ghost_filter.update(
                        candidate_targets,
                        display_point_cloud,
                        frame_number=frame_number
                    )
                else:
                    targets = candidate_targets

                target_heights = frame["target_heights"]
                presence = frame["presence"]
                mode = frame["mode"]

                # Update track history
                track_history.update(targets)

                # Prepare height map
                height_map = {}
                for h_item in target_heights:
                    height_map[h_item["tid"]] = h_item

                # Build serialized targets array
                targets_list = []
                for t in targets:
                    tid = t["tid"]
                    h_val = 1.7
                    if tid in height_map:
                        h_val = height_map[tid]["maxZ"] - height_map[tid]["minZ"]
                        if not np.isfinite(h_val) or h_val <= 0:
                            h_val = 1.7

                    targets_list.append({
                        "tid": tid,
                        "posX": round(float(t["posX"]), 3),
                        "posY": round(float(t["posY"]), 3),
                        "posZ": round(float(t["posZ"]), 3),
                        "velX": round(float(t["velX"]), 3),
                        "velY": round(float(t["velY"]), 3),
                        "velZ": round(float(t["velZ"]), 3),
                        "humanScore": round(float(t.get("humanScore", 0.0)), 1),
                        "isVirtual": bool(t.get("isVirtual", False)),
                        "height": round(float(h_val), 2)
                    })

                # Format point cloud as standard list
                pc_list = []
                if display_point_cloud is not None and len(display_point_cloud) > 0:
                    for pt in display_point_cloud:
                        pc_list.append([
                            round(float(pt[0]), 3),
                            round(float(pt[1]), 3),
                            round(float(pt[2]), 3),
                            round(float(pt[3]), 3),
                            round(float(pt[4]), 3)
                        ])

                # Update thread-safe latest frame
                with frame_lock:
                    latest_frame_data = {
                        "frame_number": int(frame_number),
                        "presence": bool(presence if presence is not None else (len(targets_list) > 0)),
                        "point_cloud": pc_list,
                        "targets": targets_list,
                        "mode": mode
                    }

                telemetry["total_parsed_frames"] += 1
                telemetry["last_update_time"] = time.time()

            time.sleep(0.005)

    except KeyboardInterrupt:
        print("[RADAR COLLECTOR] Stopping...")
    except Exception as e:
        print(f"[RADAR COLLECTOR] Unexpected error: {e}", file=sys.stderr)
        telemetry["status"] = "ERROR_RUN"
    finally:
        try:
            data_ser.close()
        except:
            pass
        print("[RADAR COLLECTOR] Port closed.")


def serial_api_thread():
    """
    Thread 2: Opens the API Serial port, listens for 'GET_DATA\n', and replies
    with the latest frame data serialized to a JSON line.
    """
    if not ENABLE_SERIAL_API:
        print("[SERIAL API] API is disabled in settings.py.")
        return

    print(f"[SERIAL API] Thread started. Listening on {API_SERIAL_PORT} at {API_SERIAL_BAUDRATE}")

    while True:
        try:
            api_ser = serial.Serial(
                API_SERIAL_PORT,
                API_SERIAL_BAUDRATE,
                timeout=1.0,
                dsrdtr=False,
                rtscts=False
            )
            api_ser.reset_input_buffer()
            api_ser.reset_output_buffer()
            print(f"[SERIAL API] Successfully opened {API_SERIAL_PORT}. Ready for commands.")
            
            while True:
                if api_ser.in_waiting > 0:
                    try:
                        line = api_ser.readline().decode("utf-8", errors="ignore").strip()
                        if line == "GET_DATA":
                            # Fetch current data frame
                            with frame_lock:
                                response_payload = latest_frame_data.copy()
                            
                            # Add telemetry diagnosis to response
                            response_payload["telemetry"] = {
                                "status": telemetry["status"],
                                "total_bytes_received": telemetry["total_bytes_received"],
                                "total_parsed_frames": telemetry["total_parsed_frames"],
                                "bad_packets": telemetry["bad_packets"]
                            }

                            # Convert to single-line JSON and write back
                            json_str = json.dumps(response_payload) + "\n"
                            api_ser.write(json_str.encode("utf-8"))
                            api_ser.flush()
                        
                        elif line == "GET_STATUS":
                            # Alternative debug command for status only
                            status_payload = {
                                "telemetry": telemetry,
                                "timestamp": time.time()
                            }
                            json_str = json.dumps(status_payload) + "\n"
                            api_ser.write(json_str.encode("utf-8"))
                            api_ser.flush()

                    except Exception as parse_err:
                        print(f"[SERIAL API] Error processing command: {parse_err}", file=sys.stderr)
                
                time.sleep(0.005)

        except serial.SerialException as e:
            print(f"[SERIAL API] Serial error on {API_SERIAL_PORT}: {e}. Retrying in 5 seconds...", file=sys.stderr)
            time.sleep(5.0)
        except Exception as e:
            print(f"[SERIAL API] Unexpected API thread error: {e}. Re-initializing...", file=sys.stderr)
            time.sleep(2.0)


def main():
    print("=============================================================")
    print(" IWR6843AOP Headless Daemon Server - Serial API Version")
    print("=============================================================")
    print(f"CLI / Config Port : {CFG_PORT}")
    print(f"DATA Stream Port  : {DATA_PORT}")
    print(f"Serial API Port   : {API_SERIAL_PORT} (Baud: {API_SERIAL_BAUDRATE})")
    print("=============================================================")

    # Start radar worker thread (Thread 1)
    t1 = threading.Thread(target=radar_collector_thread, name="RadarCollector", daemon=True)
    t1.start()

    # Start Serial API responder thread (Thread 2)
    t2 = threading.Thread(target=serial_api_thread, name="SerialAPI", daemon=True)
    t2.start()

    # Hold main thread alive
    try:
        while True:
            # Print periodic console diagnostics every 10 seconds
            time.sleep(10)
            with frame_lock:
                pts_count = len(latest_frame_data["point_cloud"])
                tgts_count = len(latest_frame_data["targets"])
                presence = latest_frame_data["presence"]
            
            print(
                f"[DAEMON DIAG] Status: {telemetry['status']} | "
                f"Parsed Frames: {telemetry['total_parsed_frames']} | "
                f"Bytes Recv: {telemetry['total_bytes_received']} | "
                f"Current Frame Pts: {pts_count} | "
                f"Targets: {tgts_count} | "
                f"Presence: {presence}"
            )
    except KeyboardInterrupt:
        print("\n[INFO] Shutdown requested by console. Exiting...")


if __name__ == "__main__":
    main()
