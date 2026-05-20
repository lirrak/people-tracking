"""
Functions for loading and sending mmWave .cfg files to the radar CFG UART.
"""

import os
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


def send_config_lines(cfg_port, config_lines):
    print(f"[INFO] Opening CFG port {cfg_port} at {CFG_BAUDRATE}")

    ser = serial.Serial(cfg_port, CFG_BAUDRATE, timeout=1)
    time.sleep(0.5)

    print("[INFO] Sending config to radar...")

    error_count = 0
    done_count = 0

    for line in config_lines:
        cmd = line + "\n"
        ser.write(cmd.encode("utf-8"))
        time.sleep(0.06)

        responses = []
        start_time = time.time()

        while time.time() - start_time < 0.35:
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

    ser.close()

    print("[INFO] Config send finished.")
    print(f"[INFO] Done responses : {done_count}")
    print(f"[INFO] Error/Skipped  : {error_count}")

    if error_count > 0:
        print("[WARN] Some config commands returned Error/Skipped.")
        print("[WARN] This usually means firmware and .cfg do not match.")


def send_selected_config():
    print("[INFO] Using external config.")
    print(f"[INFO] Config file: {CONFIG_FILE_PATH}")

    config_lines = load_external_config(CONFIG_FILE_PATH)
    send_config_lines(CFG_PORT, config_lines)
