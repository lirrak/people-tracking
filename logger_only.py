"""
Headless Logger entry point for IWR6843AOP radar.
Reads data every 1 second and saves to CSV log.
Does not open any GUI windows or record video.

Run:
    python logger_only.py
"""

import os
import sys
# Add src directory to system path to locate moved core modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import time
import subprocess
import serial
import numpy as np

# Force logging settings for headless logger
import settings
settings.ENABLE_POINTCLOUD_LOG = True
settings.ENABLE_RECORDING = False
settings.ENABLE_WEBCAM = False

from settings import *
from serial_utils import list_serial_ports
from config_sender import send_selected_config
from uart_parser import AutoRadarUARTParser
from filters import TrackHistory, GhostTargetFilter
from pointcloud_processing import VirtualTargetTracker, HAS_SKLEARN, TemporalPointCloudStabilizer
from pointcloud_logger import PointCloudLogger

import socket
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Global sensor data state for Web API Server
latest_sensor_data = {}
sensor_data_lock = threading.Lock()


class SimpleAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/sensors':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            with sensor_data_lock:
                data_copy = latest_sensor_data.copy() if latest_sensor_data else {}
                
            if data_copy:
                response = {"status": "success", "data": data_copy}
            else:
                response = {"status": "waiting", "message": "Đang chờ dữ liệu từ Radar..."}
                
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

        elif self.path == '/api/vitals/alert':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            with sensor_data_lock:
                data_copy = latest_sensor_data.copy() if latest_sensor_data else {}
                
            presence = data_copy.get('presence', False)
            targets = data_copy.get('targets', [])
            
            if not presence or len(targets) == 0:
                response = {
                    "status": "alert",
                    "message": "Cảnh báo: Không phát hiện người trong khu vực",
                    "data": {
                        "presence": presence,
                        "target_count": len(targets)
                    }
                }
            else:
                response = {
                    "status": "normal",
                    "message": "Phát hiện có người hoạt động bình thường",
                    "data": {
                        "presence": presence,
                        "target_count": len(targets),
                        "targets": targets
                    }
                }
                
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": "Not Found"}).encode('utf-8'))

    def log_message(self, format, *args):
        pass


class ReusableHTTPServer(HTTPServer):
    """HTTPServer với allow_reuse_address để tránh lỗi 'Address already in use'"""
    allow_reuse_address = True


def get_local_ip():
    """Tự động lấy địa chỉ IP của máy trong mạng LAN"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_http_server(host='0.0.0.0', port=5002):
    server = ReusableHTTPServer((host, port), SimpleAPIHandler)
    local_ip = get_local_ip()
    print("=" * 50)
    print(f"[*] API Server đã sẵn sàng.")
    print(f"[*] Địa chỉ API: http://{local_ip}:{port}/api/sensors")
    print(f"[*] Địa chỉ Alert: http://{local_ip}:{port}/api/vitals/alert")
    print("=" * 50)
    server.serve_forever()



def wait_for_device(port, timeout=30):
    """
    Chờ cho đường dẫn thiết bị USB xuất hiện lại sau khi radar crash và khởi động lại.
    CP2105 USB bridge cần 3-8 giây để đăng ký lại với hệ điều hành.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(port):
            print(f"[INFO] Device {port} is back online.")
            return True
        time.sleep(0.5)
    print(f"[WARNING] Device {port} did not reappear within {timeout}s.")
    return False


def main():
    global latest_sensor_data
    print("===================================================")
    print(" IWR6843AOP Auto Radar Logger - Headless Version")
    print(" Supports: 3D People Tracking + Log to CSV (1s Interval)")
    print("===================================================")

    list_serial_ports()

    # Bật Web API Server chạy ngầm ở port 5002
    api_thread = threading.Thread(target=run_http_server, args=('0.0.0.0', 5002), daemon=True)
    api_thread.start()

    print(f"CFG port       : {CFG_PORT}")
    print(f"DATA port      : {DATA_PORT}")
    print(f"Config file    : {CONFIG_FILE_PATH}")
    print(f"Skip config    : {SKIP_CONFIG}")
    print(f"Ghost filter   : {ENABLE_GHOST_TARGET_FILTER}")
    print(f"Ghost max miss : {GHOST_MAX_MISSING_FRAMES} frames")
    print(f"Confirm frames : {TARGET_CONFIRM_FRAMES}")
    print(f"Smoothing      : {ENABLE_TARGET_SMOOTHING}")
    print(f"PC processor   : {ENABLE_POINTCLOUD_HUMAN_PROCESSOR}")
    print(f"DBSCAN backend : {'scikit-learn' if HAS_SKLEARN else 'fallback'}")
    print("===================================================")

    if not SKIP_CONFIG:
        send_selected_config()
        # config_sender already waits 2.0s internally for the radar to start streaming
        # Only add a small extra buffer here
        time.sleep(0.2)
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

    pc_logger = PointCloudLogger()

    last_point_cloud = np.empty((0, 5), dtype=np.float32)
    last_targets = []
    last_target_heights = []
    last_presence = None
    last_frame_number = 0
    last_unknown_tlvs = []
    last_mode = "WAITING"
    last_frame_time = time.time()
    last_debug_print_time = 0.0
    last_frame_success_time = time.time()

    parsed_frame_count = 0

    print("[INFO] Reading radar frames...")
    print("[INFO] Press Ctrl+C in terminal to stop.")

    try:
        while True:
            # Read Serial data continuously to avoid OS buffer overflow (4095 bytes limit)
            time.sleep(0.001)
            now = time.time()

            # Read Serial data — wrapped in try/except to detect USB disconnect.
            # When the IWR6843 DSP crashes hard, the CP2105 USB bridge can briefly
            # disconnect, causing data_ser.in_waiting to raise an OSError/IOError.
            # Without this guard the exception would propagate out of the while loop
            # and crash the whole program with "argument must be an int" error.
            try:
                bytes_waiting = data_ser.in_waiting
            except (OSError, serial.SerialException, Exception) as _uart_err:
                print(f"\n[WARNING] UART read error ({_uart_err}). USB may have disconnected. "
                      f"Triggering recovery...")
                bytes_waiting = 0
                # Force the cold watchdog to fire on the next iteration by making
                # it appear as though no bytes have arrived for a long time.
                last_frame_success_time = now - 12.0
                time.sleep(1.0)
                continue

            if bytes_waiting > 0:
                data = data_ser.read(bytes_waiting)
                parser.append_data(data)

            frames = parser.parse_available_frames()

            if frames:
                last_frame_success_time = now

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

                # Log point cloud frame data
                if pc_logger is not None:
                    pc_logger.log_frame(
                        frame_number=frame_number,
                        raw_pc=point_cloud,
                        stable_pc=point_cloud_for_detection,
                        display_pc=display_point_cloud,
                        targets=targets,
                        presence=presence
                    )

                # Format targets for Web API Server
                height_map = {}
                for h_item in target_heights:
                    height_map[h_item["tid"]] = h_item

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

                with sensor_data_lock:
                    latest_sensor_data = {
                        "frame_number": int(frame_number),
                        "presence": bool(presence if presence is not None else (len(targets_list) > 0)),
                        "point_cloud_count": len(display_point_cloud) if display_point_cloud is not None else 0,
                        "targets": targets_list,
                        "mode": mode,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

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

                    if "immMu" in target:
                        mu = target["immMu"]
                        support_note += f" | IMM Prob [CV: {mu[0]*100:.0f}%, STOP: {mu[1]*100:.0f}%]"

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

            # Watchdog auto-recovery (bytes arriving but no valid frames)
            time_since_last_frame = now - last_frame_success_time
            if parser.total_bytes_received > 0 and time_since_last_frame > 8.0:
                print(
                    f"\n[WARNING] Watchdog triggered! No valid frames for {time_since_last_frame:.1f}s "
                    f"({parser.total_bytes_received} bytes received but 0 frames parsed). "
                    f"Reconnecting radar..."
                )
                try:
                    data_ser.close()
                except Exception:
                    pass
                time.sleep(3.0)

                if not SKIP_CONFIG:
                    # Wait for CFG port to reappear before sending config
                    if not os.path.exists(CFG_PORT):
                        print(f"[INFO] Waiting for {CFG_PORT} to reappear (USB reconnect)...")
                        wait_for_device(CFG_PORT, timeout=30)
                    try:
                        # skip_hardware_reset=True: chip is self-rebooting from crash,
                        # our DTR/RTS reset would interrupt its internal recovery.
                        # response_timeout=2.0: sensorStart Done arrives late after crash.
                        send_selected_config(skip_hardware_reset=True, response_timeout=2.0)
                    except Exception as e:
                        print(f"[ERROR] Watchdog config send failed: {e}")

                # Wait for DATA port to reappear before reopening
                if not os.path.exists(DATA_PORT):
                    print(f"[INFO] Waiting for {DATA_PORT} to reappear (USB reconnect)...")
                    wait_for_device(DATA_PORT, timeout=30)

                try:
                    data_ser = serial.Serial(
                        DATA_PORT,
                        DATA_BAUDRATE,
                        timeout=0,
                        write_timeout=0
                    )
                    data_ser.reset_input_buffer()
                    print("[INFO] DATA port reopened successfully.")
                except Exception as e:
                    print(f"[ERROR] Watchdog failed to reopen DATA port: {e}")

                # Reset parser state
                parser = AutoRadarUARTParser()
                last_frame_success_time = time.time()
                print("[INFO] Watchdog reset completed successfully.\n")

            # Cold watchdog: parser instance has received 0 bytes for too long.
            # This fires both on initial startup AND after a watchdog recovery where
            # the parser was reset (total_bytes_received resets to 0 on new instance).
            # Condition uses parser.total_bytes_received (resets each recovery cycle)
            # NOT parsed_frame_count which is a session total and never 0 after 1st frames.
            time_since_start = now - last_frame_success_time
            if parser.total_bytes_received == 0 and time_since_start > 15.0:
                print(
                    f"\n[WARNING] Cold watchdog triggered! "
                    f"0 bytes received from DATA port for {time_since_start:.1f}s. "
                    f"Radar may have been silently reset. Resending config..."
                )
                try:
                    data_ser.close()
                except Exception:
                    pass
                time.sleep(5.0)

                if not SKIP_CONFIG:
                    # Wait for CFG port to reappear before sending config
                    if not os.path.exists(CFG_PORT):
                        print(f"[INFO] Waiting for {CFG_PORT} to reappear (USB reconnect)...")
                        wait_for_device(CFG_PORT, timeout=30)
                    try:
                        # skip_hardware_reset=True: chip is self-rebooting from crash.
                        # response_timeout=2.0: sensorStart Done arrives late.
                        send_selected_config(skip_hardware_reset=True, response_timeout=2.0)
                    except Exception as e:
                        print(f"[ERROR] Cold watchdog config send failed: {e}")

                try:
                    subprocess.run(
                        ["stty", "-F", DATA_PORT, "-hupcl"],
                        check=True, timeout=3,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass

                # Wait for DATA port to reappear before reopening
                if not os.path.exists(DATA_PORT):
                    print(f"[INFO] Waiting for {DATA_PORT} to reappear (USB reconnect)...")
                    wait_for_device(DATA_PORT, timeout=30)

                try:
                    data_ser = serial.Serial(
                        DATA_PORT,
                        DATA_BAUDRATE,
                        timeout=0,
                        write_timeout=0
                    )
                    data_ser.reset_input_buffer()
                    print("[INFO] DATA port reopened after cold watchdog.")
                except Exception as e:
                    print(f"[ERROR] Cold watchdog failed to reopen DATA port: {e}")

                # Reset parser and timer so watchdog doesn't re-fire immediately
                parser = AutoRadarUARTParser()
                last_frame_success_time = time.time()
                print("[INFO] Cold watchdog recovery completed.\n")

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

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")

    except serial.SerialException as e:
        print(f"[ERROR] Serial error: {e}")

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")

    finally:
        # Gracefully close logger and ports
        try:
            if 'pc_logger' in locals() and pc_logger is not None:
                pc_logger.close()
        except Exception as log_err:
            print(f"[WARNING] Error closing logger: {log_err}")

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
