"""
Headless API Server entry point for IWR6843AOP radar.
Exposes HTTP API server on port 5002 and Serial API to query radar sensor data.

Run:
    python api_server.py
"""

import os
import sys
# Add src directory to system path to locate moved core modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import time
import subprocess
import serial
import numpy as np
import socket
import json
import threading
import hashlib
import base64

# Force headless settings for API server daemon
import settings
settings.ENABLE_RECORDING = False
settings.ENABLE_WEBCAM = False

from settings import *

# Định nghĩa mặc định phòng trường hợp người dùng comment out trong settings.py
if 'ENABLE_SERIAL_API' not in globals():
    ENABLE_SERIAL_API = False
if 'API_SERIAL_PORT' not in globals():
    API_SERIAL_PORT = "COM15"
if 'API_SERIAL_BAUDRATE' not in globals():
    API_SERIAL_BAUDRATE = 115200

from serial_utils import list_serial_ports
from config_sender import send_selected_config
from uart_parser import AutoRadarUARTParser
from filters import TrackHistory, GhostTargetFilter
from pointcloud_processing import VirtualTargetTracker, HAS_SKLEARN, TemporalPointCloudStabilizer
# pointcloud_logger import removed to disable CSV output

# Global sensor data state for Web API Server
latest_sensor_data = {}
sensor_data_lock = threading.Lock()


active_clients = []
clients_lock = threading.Lock()


def calculate_accept_key(sec_key):
    guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    accept_val = hashlib.sha1((sec_key + guid).encode('utf-8')).digest()
    return base64.b64encode(accept_val).decode('utf-8')


def make_websocket_frame(message):
    payload = message.encode('utf-8')
    length = len(payload)
    header = bytearray([0x81])
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(length.to_bytes(2, byteorder='big'))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, byteorder='big'))
    return header + payload


def broadcast_to_ws(data_dict):
    global active_clients
    with clients_lock:
        if not active_clients:
            return
        targets = list(active_clients)
        
    message = json.dumps(data_dict, ensure_ascii=False)
    frame = make_websocket_frame(message)
    
    disconnected_clients = []
    for client in targets:
        try:
            client.sendall(frame)
        except Exception:
            disconnected_clients.append(client)
            
    if disconnected_clients:
        with clients_lock:
            for client in disconnected_clients:
                if client in active_clients:
                    active_clients.remove(client)
                try:
                    client.close()
                except:
                    pass


def handle_client(client_socket):
    global active_clients
    try:
        request = client_socket.recv(2048).decode('utf-8', errors='ignore')
        if not request:
            client_socket.close()
            return
            
        lines = request.split('\r\n')
        req_line = lines[0]
        req_parts = req_line.split(' ')
        method = req_parts[0] if len(req_parts) > 0 else 'GET'
        path = req_parts[1] if len(req_parts) > 1 else '/'
        
        headers = {}
        for line in lines[1:]:
            if ': ' in line:
                key, val = line.split(': ', 1)
                headers[key.strip().lower()] = val.strip()
                
        is_websocket = (headers.get('upgrade', '').lower() == 'websocket')
        
        if is_websocket and 'sec-websocket-key' in headers:
            key = headers['sec-websocket-key']
            accept_key = calculate_accept_key(key)
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
            )
            client_socket.sendall(response.encode('utf-8'))
            
            with clients_lock:
                active_clients.append(client_socket)
                
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                opcode = data[0] & 0x0F
                if opcode == 8:
                    break
        else:
            # HTTP Fallback
            if path == '/api/sensors':
                with sensor_data_lock:
                    data_copy = latest_sensor_data.copy() if latest_sensor_data else {}
                if data_copy:
                    response_data = {"status": "success", "data": data_copy}
                else:
                    response_data = {"status": "waiting", "message": "Đang chờ dữ liệu từ Radar..."}
                body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode('utf-8') + body
            elif path == '/api/vitals/alert':
                with sensor_data_lock:
                    data_copy = latest_sensor_data.copy() if latest_sensor_data else {}
                presence = data_copy.get('presence', False)
                targets = data_copy.get('targets', [])
                any_fall = any(t.get("fall_alert", False) for t in targets)
                
                if any_fall:
                    response_data = {
                        "status": "fall",
                        "message": "CẢNH BÁO: Phát hiện người bị ngã trong phòng!",
                        "data": {"presence": presence, "target_count": len(targets), "targets": targets}
                    }
                elif not presence or len(targets) == 0:
                    response_data = {
                        "status": "alert",
                        "message": "Cảnh báo: Không phát hiện người trong khu vực",
                        "data": {"presence": presence, "target_count": len(targets)}
                    }
                else:
                    response_data = {
                        "status": "normal",
                        "message": "Phát hiện có người hoạt động bình thường",
                        "data": {"presence": presence, "target_count": len(targets), "targets": targets}
                    }
                body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode('utf-8') + body
            else:
                body = json.dumps({"status": "error", "message": "Not Found"}).encode('utf-8')
                response = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode('utf-8') + body
                
            client_socket.sendall(response)
            client_socket.close()
            
    except Exception:
        try:
            client_socket.close()
        except:
            pass
    finally:
        with clients_lock:
            if client_socket in active_clients:
                active_clients.remove(client_socket)


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


def run_socket_server(host='0.0.0.0', port=5002):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((host, port))
        server_socket.listen(10)
        local_ip = get_local_ip()
        print("=" * 50)
        print(f"[*] API Server đã sẵn sàng (WebSocket & HTTP).")
        print(f"[*] Địa chỉ HTTP API: http://{local_ip}:{port}/api/sensors")
        print(f"[*] Địa chỉ WebSocket: ws://{local_ip}:{port}/")
        print("=" * 50)
    except Exception as e:
        print(f"[ERROR] Failed to bind to port {port}: {e}")
        return
        
    while True:
        try:
            client_socket, client_address = server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(client_socket,), daemon=True)
            client_thread.start()
        except Exception:
            time.sleep(0.1)


def serial_api_thread_func():
    if not ENABLE_SERIAL_API:
        return
    
    while True:
        try:
            print(f"[*] Đang khởi tạo cổng Serial API {API_SERIAL_PORT} với baudrate {API_SERIAL_BAUDRATE}...")
            with serial.Serial(API_SERIAL_PORT, API_SERIAL_BAUDRATE, timeout=1) as ser:
                print(f"[*] Cổng Serial API {API_SERIAL_PORT} đã sẵn sàng.")
                while True:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        continue
                    
                    if line == "GET_DATA":
                        with sensor_data_lock:
                            data_copy = latest_sensor_data.copy() if latest_sensor_data else {}
                        
                        response = {"status": "success", "data": data_copy} if data_copy else {"status": "waiting", "message": "Đang chờ dữ liệu..."}
                        ser.write((json.dumps(response, ensure_ascii=False) + "\n").encode('utf-8'))
                    
                    elif line == "GET_STATUS":
                        with sensor_data_lock:
                            presence = latest_sensor_data.get("presence", False) if latest_sensor_data else False
                            targets_count = len(latest_sensor_data.get("targets", [])) if latest_sensor_data else 0
                        status_msg = f"STATUS: OK | PRESENCE: {presence} | TARGETS: {targets_count}\n"
                        ser.write(status_msg.encode('utf-8'))
        except Exception as e:
            print(f"[!] Lỗi Serial API: {e}. Thử lại sau 5 giây...")
            time.sleep(5)


def wait_for_device(port, timeout=30):
    """
    Chờ cho đường dẫn thiết bị USB xuất hiện lại sau khi radar crash và khởi động lại.
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
    print(" IWR6843AOP Auto Radar API Server - Daemon Version")
    print(" Supports: 3D People Tracking + HTTP API + Serial API")
    print("===================================================")

    list_serial_ports()

    # 1. Bật WebSocket & HTTP Server chạy ngầm ở port được cấu hình (mặc định 5002)
    host = HTTP_API_HOST if 'HTTP_API_HOST' in globals() else '0.0.0.0'
    port = HTTP_API_PORT if 'HTTP_API_PORT' in globals() else 5002
    
    http_thread = threading.Thread(target=run_socket_server, args=(host, port), daemon=True)
    http_thread.start()

    # 2. Bật Serial API Server chạy ngầm nếu được kích hoạt
    if ENABLE_SERIAL_API:
        ser_thread = threading.Thread(target=serial_api_thread_func, daemon=True)
        ser_thread.start()

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
    target_height_ema = {}

    # PointCloudLogger initialization removed to disable CSV logging

    last_frame_number = 0
    last_mode = "WAITING"
    last_frame_success_time = time.time()
    parsed_frame_count = 0

    print("[INFO] Reading radar frames...")
    print("[INFO] Press Ctrl+C in terminal to stop.")

    try:
        while True:
            time.sleep(0.001)
            now = time.time()

            try:
                bytes_waiting = data_ser.in_waiting
            except (OSError, serial.SerialException, Exception) as _uart_err:
                print(f"\n[WARNING] UART read error ({_uart_err}). USB may have disconnected. "
                      f"Triggering recovery...")
                bytes_waiting = 0
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
                mode = frame["mode"]

                parsed_frame_count += 1
                last_frame_number = frame_number
                last_mode = mode

                track_history.update(targets)

                # Log point cloud frame data to CSV disabled

                # Format targets for Web API Server
                height_map = {}
                for h_item in target_heights:
                    height_map[h_item["tid"]] = h_item

                # Clean up old target IDs from EMA dictionary to prevent memory leak
                active_tids = {t["tid"] for t in targets}
                for old_tid in list(target_height_ema.keys()):
                    if old_tid not in active_tids:
                        del target_height_ema[old_tid]

                targets_list = []
                for t in targets:
                    tid = t["tid"]
                    h_val = 1.7
                    if tid in height_map:
                        h_val = height_map[tid]["maxZ"] - height_map[tid]["minZ"]
                        if not np.isfinite(h_val) or h_val <= 0:
                            h_val = 1.7

                    # Apply Exponential Moving Average (EMA) to smooth height fluctuations
                    # alpha = 0.05 gives a smooth transition (approx 20 frames / 1 second window)
                    alpha = 0.05
                    if tid not in target_height_ema:
                        target_height_ema[tid] = h_val
                    else:
                        target_height_ema[tid] = alpha * h_val + (1.0 - alpha) * target_height_ema[tid]

                    smoothed_h = target_height_ema[tid]

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
                        "height": round(float(smoothed_h), 2),
                        "posture": t.get("posture", "STANDING"),
                        "fall_status": t.get("fall_status", "NORMAL"),
                        "fall_alert": bool(t.get("fall_alert", False))
                    })

                # Format point cloud list
                point_cloud_list = []
                if display_point_cloud is not None and len(display_point_cloud) > 0:
                    for p in display_point_cloud:
                        point_cloud_list.append([
                            round(float(p[0]), 3), # x
                            round(float(p[1]), 3), # y
                            round(float(p[2]), 3), # z
                            round(float(p[3]), 3), # vel
                            round(float(p[4]), 1)  # snr
                        ])

                # Update the shared global state
                with sensor_data_lock:
                    latest_sensor_data = {
                        "frame_number": int(frame_number),
                        "presence": bool(presence if presence is not None else (len(targets_list) > 0)),
                        "point_cloud_count": len(point_cloud_list),
                        "point_cloud": point_cloud_list,
                        "targets": targets_list,
                        "mode": mode,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }

                # Broadcast to all connected WebSocket clients
                broadcast_to_ws(latest_sensor_data)

                print(
                    f"Frame {frame_number} | "
                    f"Mode: {mode} | "
                    f"Display points: {len(point_cloud_list)} | "
                    f"Targets: {len(targets_list)} | "
                    f"Presence: {presence}"
                )

            # Watchdog auto-recovery
            time_since_last_frame = now - last_frame_success_time
            if parser.total_bytes_received > 0 and time_since_last_frame > 8.0:
                print(
                    f"\n[WARNING] Watchdog triggered! No valid frames for {time_since_last_frame:.1f}s. "
                    f"Reconnecting radar..."
                )
                try:
                    data_ser.close()
                except Exception:
                    pass
                time.sleep(3.0)

                if not SKIP_CONFIG:
                    if not os.path.exists(CFG_PORT):
                        print(f"[INFO] Waiting for {CFG_PORT} to reappear...")
                        wait_for_device(CFG_PORT, timeout=30)
                    try:
                        send_selected_config(skip_hardware_reset=True, response_timeout=2.0)
                    except Exception as e:
                        print(f"[ERROR] Watchdog config send failed: {e}")

                if not os.path.exists(DATA_PORT):
                    print(f"[INFO] Waiting for {DATA_PORT} to reappear...")
                    wait_for_device(DATA_PORT, timeout=30)

                try:
                    data_ser = serial.Serial(DATA_PORT, DATA_BAUDRATE, timeout=0, write_timeout=0)
                    data_ser.reset_input_buffer()
                    print("[INFO] DATA port reopened successfully.")
                except Exception as e:
                    print(f"[ERROR] Watchdog failed to reopen DATA port: {e}")

                parser = AutoRadarUARTParser()
                last_frame_success_time = time.time()
                print("[INFO] Watchdog reset completed.\n")

            # Cold watchdog
            time_since_start = now - last_frame_success_time
            if parser.total_bytes_received == 0 and time_since_start > 15.0:
                print(
                    f"\n[WARNING] Cold watchdog triggered! "
                    f"0 bytes received for {time_since_start:.1f}s. "
                    f"Resending config..."
                )
                try:
                    data_ser.close()
                except Exception:
                    pass
                time.sleep(5.0)

                if not SKIP_CONFIG:
                    if not os.path.exists(CFG_PORT):
                        print(f"[INFO] Waiting for {CFG_PORT} to reappear...")
                        wait_for_device(CFG_PORT, timeout=30)
                    try:
                        send_selected_config(skip_hardware_reset=True, response_timeout=2.0)
                    except Exception as e:
                        print(f"[ERROR] Cold watchdog config send failed: {e}")

                if not os.path.exists(DATA_PORT):
                    print(f"[INFO] Waiting for {DATA_PORT} to reappear...")
                    wait_for_device(DATA_PORT, timeout=30)

                try:
                    data_ser = serial.Serial(DATA_PORT, DATA_BAUDRATE, timeout=0, write_timeout=0)
                    data_ser.reset_input_buffer()
                    print("[INFO] DATA port reopened after cold watchdog.")
                except Exception as e:
                    print(f"[ERROR] Cold watchdog failed to reopen DATA port: {e}")

                parser = AutoRadarUARTParser()
                last_frame_success_time = time.time()
                print("[INFO] Cold watchdog recovery completed.\n")

    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")

    finally:
        # pc_logger cleanup removed

        try:
            data_ser.close()
        except Exception:
            pass
        print("[INFO] DATA port closed.")


if __name__ == "__main__":
    main()
