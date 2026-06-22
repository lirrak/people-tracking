"""
Functions for loading and sending mmWave .cfg files to the radar CFG UART.
"""

import os
import subprocess
import time
import serial

from settings import CFG_BAUDRATE, CFG_PORT, CONFIG_FILE_PATH


# ============================================================
# CONFIG FUNCTIONS
# ============================================================

def clean_config_lines(lines):
    clean_lines = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("%"):
            continue

        clean_lines.append(line)

    return clean_lines


def check_config_type(config_lines):
    tracking_keywords = [
        "trackingCfg",
        "boundaryBox",
        "staticBoundaryBox",
        "gatingParam",
        "allocationParam",
        "stateParam",
        "presenceBoundaryBox",
        "sensorPosition",
        "dynamicRACfarCfg",
        "dynamicRangeAngleCfg",
        "staticRACfarCfg",
    ]

    found_tracking_keywords = []

    for line in config_lines:
        parts = line.split()

        if not parts:
            continue

        first_word = parts[0]

        if first_word in tracking_keywords:
            found_tracking_keywords.append(first_word)

    if found_tracking_keywords:
        print("[INFO] Config looks like 3D People Tracking config.")
        print(f"[INFO] Tracking commands found: {sorted(set(found_tracking_keywords))}")
    else:
        print("[WARN] Config does NOT look like 3D People Tracking config.")
        print("[WARN] It may be an Out-of-Box config.")


def check_frame_cfg(config_lines):
    for line in config_lines:
        if line.startswith("frameCfg"):
            parts = line.split()

            if len(parts) >= 5:
                try:
                    num_frames = int(parts[4])
                    print(f"[INFO] Found frameCfg: {line}")
                    print(f"[INFO] numFrames = {num_frames}")

                    if num_frames != 0:
                        print("[WARN] numFrames is not 0.")
                        print("[WARN] Radar may stop after this number of frames.")
                        print("[WARN] For continuous run, set numFrames = 0.")

                except ValueError:
                    print("[WARN] Cannot parse numFrames in frameCfg.")

            return

    print("[WARN] No frameCfg found in config.")


def load_external_config(config_file_path):
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(
            f"Config file not found:\n{config_file_path}\n\n"
            f"Please put the .cfg file in example_configs "
            f"or update CONFIG_FILE_PATH."
        )

    with open(config_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    config_lines = clean_config_lines(lines)

    check_frame_cfg(config_lines)
    check_config_type(config_lines)

    return config_lines


def send_config_lines(cfg_port, config_lines, skip_hardware_reset=False, response_timeout=0.35):
    print(f"[INFO] Opening CFG port {cfg_port} at {CFG_BAUDRATE}")

    # Mở cổng với các đường bắt tay tắt để tự kiểm soát
    ser = serial.Serial(cfg_port, CFG_BAUDRATE, timeout=1, dsrdtr=False, rtscts=False)

    if not skip_hardware_reset:
        # Thực hiện reset phần cứng qua DTR/RTS (chỉ dùng khi khởi động lần đầu).
        # Khi gọi để phục hồi sau crash (skip_hardware_reset=True), bỏ qua bước này
        # vì chip đã tự khởi động lại từ crash và việc tác động DTR/RTS có thể
        # làm gián đoạn quá trình phục hồi nội bộ của chip.
        print("[INFO] Triggering hardware reset (DTR/RTS toggling)...")
        try:
            # Kéo reset xuống thấp (DTR & RTS = True làm đầu ra pin vật lý xuống 0V)
            ser.dtr = True
            ser.rts = True
            time.sleep(0.25)
            
            ser.rts = False
            time.sleep(1.0)
            
            ser.dtr = False
            time.sleep(0.5)

            # Dọn sạch các bộ đệm cổng nối tiếp
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            print("[INFO] Hardware reset completed successfully.")
        except Exception as e:
            print(f"[WARNING] Hardware reset failed: {e}")
    else:
        print("[INFO] Skipping hardware reset (recovery mode — chip is self-rebooting).")

    print("[INFO] Waiting for radar boot (listening for mmwDemo:/>)...")
    boot_start = time.time()
    banner_found = False
    while time.time() - boot_start < 4.0:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting)
            try:
                decoded = chunk.decode("utf-8", errors="ignore")
                print(decoded, end="", flush=True)
                if "mmwDemo:/>" in decoded:
                    banner_found = True
                    break
            except Exception:
                pass
        time.sleep(0.1)
    
    if banner_found:
        print("\n[INFO] Radar boot banner detected. Ready for commands.")
    else:
        print("\n[WARNING] Did not see mmwDemo:/> banner. Radar might still be hung or already booted.")
    
    # Dọn sạch các bộ đệm cổng nối tiếp
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    print("[INFO] Sending config to radar...")

    error_count = 0
    done_count = 0

    for i, line in enumerate(config_lines):
        cmd = line + "\n"
        try:
            ser.write(cmd.encode("utf-8"))
        except Exception as write_err:
            print(f"[WARNING] Write error on '{line}': {write_err}")
            continue
        time.sleep(0.06)

        responses = []
        start_time = time.time()
        # sensorStart được gửi cuối cùng. Khi ở chế độ phục hồi, cần thường
        # nhiều thời gian hơn để lấy phản hồi Done (firmware khởi động chậm hơn).
        timeout = response_timeout * 10 if line.startswith("sensorStart") and skip_hardware_reset else response_timeout

        while time.time() - start_time < timeout:
            if ser.in_waiting:
                try:
                    response = ser.readline().decode(errors="ignore").strip()
                    if response:
                        responses.append(response)
                except Exception:
                    pass
            else:
                time.sleep(0.005)

        print(f"> {line}")

        if not responses:
            print("< [NO RESPONSE]")
        else:
            for response in responses:
                print(f"< {response}")

                if "Done" in response:
                    done_count += 1

                if "Error" in response or "Skipped" in response:
                    error_count += 1

    # Giải phóng DTR/RTS về mức an toàn TRƯỚC KHI đóng cổng.
    # Nếu HUPCL vẫn còn hoạt động ở kernel cũ, bước này đảm bảo
    # đường RESET của radar không bị kéo xuống khi close().
    try:
        ser.dtr = False
        ser.rts = False
        time.sleep(0.05)
    except Exception:
        pass

    ser.close()

    # Đợi radar ổn định hoàn toàn sau khi nhận cấu hình và khởi động sensor
    # 2.0s là đủ để firmware IWR6843 xử lý sensorStart và bắt đầu stream data.
    print("[INFO] Waiting 2.0s for radar to fully start streaming...")
    time.sleep(2.0)

    print("[INFO] Config send finished.")
    print(f"[INFO] Done responses : {done_count}")
    print(f"[INFO] Error/Skipped  : {error_count}")

    if error_count > 0:
        print("[WARN] Some config commands returned Error/Skipped.")
        print("[WARN] This usually means firmware and .cfg do not match.")


def send_selected_config(skip_hardware_reset=False, response_timeout=0.35):
    print("[INFO] Using external config.")
    print(f"[INFO] Config file: {CONFIG_FILE_PATH}")

    config_lines = load_external_config(CONFIG_FILE_PATH)
    
    # Tự động ghi đè hoặc chèn câu lệnh sensorPosition động (Version 26.0)
    # Lấy thông số độ cao lắp đặt và góc nghiêng từ settings.py
    from settings import RADAR_MOUNT_HEIGHT_M, RADAR_TILT_ANGLE_DEG
    updated_sensor_pos = False
    
    for idx, line in enumerate(config_lines):
        if line.startswith("sensorPosition"):
            # Cấu trúc: sensorPosition <height> <azimuthTilt> <elevationTilt>
            config_lines[idx] = f"sensorPosition {RADAR_MOUNT_HEIGHT_M} 0 {RADAR_TILT_ANGLE_DEG}"
            print(f"[INFO] Dynamically updated config line to: {config_lines[idx]}")
            updated_sensor_pos = True
            break
            
    if not updated_sensor_pos:
        # Nếu chưa có trong tệp cấu hình, chèn vào trước dòng sensorStart
        insert_idx = len(config_lines) - 1
        for idx, line in enumerate(config_lines):
            if line.startswith("sensorStart"):
                insert_idx = idx
                break
        config_lines.insert(insert_idx, f"sensorPosition {RADAR_MOUNT_HEIGHT_M} 0 {RADAR_TILT_ANGLE_DEG}")
        print(f"[INFO] Dynamically inserted config line: {config_lines[insert_idx]}")

    send_config_lines(CFG_PORT, config_lines,
                      skip_hardware_reset=skip_hardware_reset,
                      response_timeout=response_timeout)
