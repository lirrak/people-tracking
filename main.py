"""
Main entry point for IWR6843AOP radar viewer.

Run:
    python main.py
"""

import time
import serial
import numpy as np
import matplotlib.pyplot as plt

from settings import *
from serial_utils import list_serial_ports
from config_sender import send_selected_config
from uart_parser import AutoRadarUARTParser
from filters import TrackHistory, GhostTargetFilter
from pointcloud_processing import VirtualTargetTracker, HAS_SKLEARN, TemporalPointCloudStabilizer
from visualization import setup_3d_plot, update_3d_plot
from sync_recorder import SyncRecorder


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():
    print("===================================================")
    print(" IWR6843AOP Auto Radar Viewer - Human Box Version")
    print(" Supports: 3D People Tracking + Out-of-Box")
    print("===================================================")

    list_serial_ports()

    print(f"CFG port       : {CFG_PORT}")
    print(f"DATA port      : {DATA_PORT}")
    print(f"Config file    : {CONFIG_FILE_PATH}")
    print(f"Skip config    : {SKIP_CONFIG}")
    print(f"Human box      : {SHOW_HUMAN_BOX}")
    print(f"Ghost filter   : {ENABLE_GHOST_TARGET_FILTER}")
    print(f"Ghost max miss : {GHOST_MAX_MISSING_FRAMES} frames")
    print(f"Confirm frames : {TARGET_CONFIRM_FRAMES}")
    print(f"Smoothing      : {ENABLE_TARGET_SMOOTHING}")
    print(f"PC processor   : {ENABLE_POINTCLOUD_HUMAN_PROCESSOR}")
    print(f"DBSCAN backend : {'scikit-learn' if HAS_SKLEARN else 'fallback'}")
    print("===================================================")

    if not SKIP_CONFIG:
        send_selected_config()
        time.sleep(0.5)
    else:
        print("[INFO] SKIP_CONFIG = True. Config will not be sent.")

    print(f"[INFO] Opening DATA port {DATA_PORT} at {DATA_BAUDRATE}")

    data_ser = serial.Serial(
        DATA_PORT,
        DATA_BAUDRATE,
        timeout=0,
        write_timeout=0
    )

    data_ser.reset_input_buffer()

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

    # Khởi tạo bộ ghi hình đồng bộ (Version 11.0)
    recorder = SyncRecorder()
    recorder.start()

    fig, ax = setup_3d_plot()

    last_point_cloud = np.empty((0, 5), dtype=np.float32)
    last_targets = []
    last_target_heights = []
    last_presence = None
    last_frame_number = 0
    last_unknown_tlvs = []
    last_mode = "WAITING"
    last_frame_time = time.time()
    last_plot_time = 0.0
    start_time = time.time()
    last_debug_print_time = 0.0

    parsed_frame_count = 0

    print("[INFO] Reading radar frames...")
    print("[INFO] Figure should remain responsive.")
    print("[INFO] Press Ctrl+C in terminal to stop.")

    try:
        while plt.fignum_exists(fig.number):
            now = time.time()

            bytes_waiting = data_ser.in_waiting

            if bytes_waiting > 0:
                data = data_ser.read(bytes_waiting)
                parser.append_data(data)

            frames = parser.parse_available_frames()

            for frame in frames:
                header = frame["header"]
                frame_number = header.get("frameNumber", 0)

                point_cloud = frame["point_cloud"]
                raw_targets = frame["targets"]
                target_index = frame.get("target_index", np.empty((0,), dtype=np.uint8))

                if ENABLE_POINTCLOUD_TEMPORAL_STABILIZER:
                    point_cloud_for_detection = pointcloud_stabilizer.update(
                        point_cloud,
                        frame_number=frame_number
                    )
                else:
                    point_cloud_for_detection = point_cloud

                cluster_debug = []

                if ENABLE_POINTCLOUD_HUMAN_PROCESSOR:
                    candidate_targets, display_point_cloud, cluster_debug = virtual_tracker.track_and_build(
                        raw_targets=raw_targets,
                        point_cloud=point_cloud_for_detection,
                        target_index=target_index,
                        frame_number=frame_number
                    )
                else:
                    candidate_targets = raw_targets
                    display_point_cloud = point_cloud_for_detection

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
                unknown_tlvs = frame["unknown_tlvs"]
                mode = frame["mode"]

                parsed_frame_count += 1
                last_frame_number = frame_number
                last_point_cloud = display_point_cloud
                last_targets = targets
                last_target_heights = target_heights
                last_presence = presence
                last_unknown_tlvs = unknown_tlvs
                last_mode = mode
                last_frame_time = time.time()

                track_history.update(targets)

                print(
                    f"Frame {frame_number} | "
                    f"Mode: {mode} | "
                    f"Header: {parser.last_header_mode} | "
                    f"TLV length: {parser.last_tlv_length_mode} | "
                    f"TLVs: {parser.last_tlv_types} | "
                    f"Raw points: {len(point_cloud)} | "
                    f"Stable points: {len(point_cloud_for_detection)} | "
                    f"Display points: {len(display_point_cloud)} | "
                    f"Clusters: {len(cluster_debug)} | "
                    f"Targets: {len(targets)} | "
                    f"Raw targets: {len(raw_targets)} | "
                    f"Presence: {presence}"
                )

                if PRINT_FRAME_DEBUG and parsed_frame_count % PRINT_FRAME_DEBUG_EVERY_N_FRAMES == 0:
                    print(f"  Header mode: {parser.last_header_mode}")
                    print(f"  TLV length mode: {parser.last_tlv_length_mode}")
                    print(f"  TLV types: {parser.last_tlv_types}")
                    print(f"  Unknown TLVs: {unknown_tlvs}")
                    if cluster_debug:
                        for cluster_item in cluster_debug[:6]:
                            print(
                                f"  Cluster {cluster_item['cluster_id']} | "
                                f"points={cluster_item['point_count']} | "
                                f"score={cluster_item['score']:.1f} | "
                                f"center={cluster_item['center']}"
                            )

                for target in targets:
                    virtual_note = " | virtual pointcloud detect" if target.get("isVirtual", False) else ""
                    support_note = ""

                    if "supportPointCount" in target:
                        support_note = f" | support_points={target['supportPointCount']}"

                    if "humanScore" in target:
                        support_note += f" | score={target['humanScore']:.1f}"

                    if target.get("source"):
                        support_note += f" | source={target.get('source')}"

                    if target.get("ghostFiltered", False):
                        support_note += f" | missing_frames={target.get('missingFrames', 0)}"

                    print(
                        f"  ID {target['tid']} | "
                        f"pos=({target['posX']:.2f}, "
                        f"{target['posY']:.2f}, "
                        f"{target['posZ']:.2f}) m | "
                        f"vel=({target['velX']:.2f}, "
                        f"{target['velY']:.2f}, "
                        f"{target['velZ']:.2f}) m/s"
                        f"{virtual_note}"
                        f"{support_note}"
                    )

            if PRINT_UART_DEBUG and now - last_debug_print_time > 2.0:
                last_debug_print_time = now

                print(
                    f"[UART DEBUG] bytes_total={parser.total_bytes_received}, "
                    f"in_waiting={bytes_waiting}, "
                    f"buffer={len(parser.buffer)}, "
                    f"parsed_frames={parsed_frame_count}, "
                    f"bad_packets={parser.bad_packets}, "
                    f"mode={last_mode}, "
                    f"header={parser.last_header_mode}, "
                    f"tlv_length={parser.last_tlv_length_mode}, "
                    f"tlvs={parser.last_tlv_types}"
                )

                if parser.total_bytes_received > 0 and parsed_frame_count == 0:
                    print(f"[UART DEBUG] first bytes hex: {parser.first_bytes_hex}")

            should_plot = False

            if frames:
                if last_frame_number % PLOT_EVERY_N_FRAMES == 0:
                    should_plot = True

            if now - last_plot_time >= GUI_REFRESH_INTERVAL_SEC:
                should_plot = True

            if should_plot:
                elapsed = now - start_time
                time_since_last_frame = now - last_frame_time

                if parsed_frame_count == 0:
                    if parser.total_bytes_received == 0 and elapsed > NO_DATA_WARNING_SEC:
                        status_text = (
                            "Status: NO DATA BYTES from DATA UART. "
                            "Check DATA_PORT / firmware / sensorStart."
                        )
                    elif parser.total_bytes_received > 0:
                        status_text = (
                            "Status: DATA BYTES RECEIVED but no valid radar frame. "
                            "Check parser format."
                        )
                    else:
                        status_text = "Status: waiting for radar bytes..."
                else:
                    status_text = (
                        f"Status: running | "
                        f"Last frame age: {time_since_last_frame:.2f}s"
                    )

                parser_status = (
                    f"Bytes: {parser.total_bytes_received} | "
                    f"Parsed frames: {parsed_frame_count} | "
                    f"Buffer: {len(parser.buffer)} | "
                    f"Bad packets: {parser.bad_packets} | "
                    f"Header: {parser.last_header_mode} | "
                    f"TLV length: {parser.last_tlv_length_mode} | "
                    f"TLVs: {parser.last_tlv_types}"
                )

                if last_mode == "OUT_OF_BOX":
                    parser_status += " | NOTE: Out-of-Box has no real tracking target list."

                if last_unknown_tlvs:
                    parser_status += f" | Unknown: {last_unknown_tlvs}"

                update_3d_plot(
                    fig=fig,
                    ax=ax,
                    point_cloud=last_point_cloud,
                    targets=last_targets,
                    target_heights=last_target_heights,
                    track_history=track_history,
                    frame_number=last_frame_number,
                    presence=last_presence,
                    mode=last_mode,
                    status_text=status_text,
                    parser_status=parser_status
                )

                # GHI VIDEO SIDE-BY-SIDE (Version 11.0)
                if recorder.enabled:
                    try:
                        # Trích xuất trực tiếp ảnh RGB từ bộ đệm đồ họa Matplotlib
                        fig.canvas.draw()
                        rgba_buffer = fig.canvas.buffer_rgba()
                        plot_img = np.asarray(rgba_buffer)[:, :, :3]
                        
                        # Ghi khung hình đồng bộ với số frame tương ứng
                        recorder.write_frame(plot_img, frame_number=last_frame_number)
                    except Exception as record_err:
                        print(f"[WARNING] Grab canvas error: {record_err}")

                last_plot_time = now

            plt.pause(0.001)
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
 
    except serial.SerialException as e:
        print(f"[ERROR] Serial error: {e}")

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")

    finally:
        # Dừng webcam và lưu video an toàn (Version 11.0)
        try:
            recorder.stop()
        except Exception as stop_err:
            print(f"[WARNING] Error stopping recorder: {stop_err}")

        try:
            data_ser.close()
        except Exception:
            pass

        print("[INFO] DATA port closed.")
        print(f"[INFO] Last frame number: {last_frame_number}")
        print(f"[INFO] Total parsed frames: {parsed_frame_count}")
        print(f"[INFO] Last detected mode: {last_mode}")
        print(f"[INFO] Last header mode: {parser.last_header_mode}")
        print(f"[INFO] Last TLV types: {parser.last_tlv_types}")
        print(f"[INFO] Last TLV length mode: {parser.last_tlv_length_mode}")
        print(f"[INFO] Total bytes received: {parser.total_bytes_received}")


if __name__ == "__main__":
    main()
