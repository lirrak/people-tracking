import os
import csv
import datetime
import numpy as np
from settings import ENABLE_POINTCLOUD_LOG, POINTCLOUD_LOG_DIR

class PointCloudLogger:
    def __init__(self):
        self.enabled = ENABLE_POINTCLOUD_LOG
        self.log_file = None
        self.writer = None
        self.filepath = ""
        
        if not self.enabled:
            return
            
        try:
            # Tạo thư mục log nếu chưa có
            os.makedirs(POINTCLOUD_LOG_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pointcloud_metrics_{timestamp}.csv"
            self.filepath = os.path.join(POINTCLOUD_LOG_DIR, filename)
            
            self.log_file = open(self.filepath, mode='w', newline='', encoding='utf-8')
            self.writer = csv.writer(self.log_file)
            
            # Ghi tiêu đề cột (Headers) - Thống kê mức độ frame (Version 20.0)
            headers = [
                "frame_number",
                "timestamp",
                "raw_points_count",
                "stable_points_count",
                "display_points_count",
                "raw_min_snr",
                "raw_max_snr",
                "raw_mean_snr",
                "display_min_x",
                "display_max_x",
                "display_mean_x",
                "display_min_y",
                "display_max_y",
                "display_mean_y",
                "display_min_z",
                "display_max_z",
                "display_mean_z",
                "display_min_doppler",
                "display_max_doppler",
                "display_mean_doppler",
                "target_count",
                "active_target_ids",
                "presence"
            ]
            self.writer.writerow(headers)
            print(f"[INFO] Point Cloud logger initialized. Saving to: {self.filepath}")
        except Exception as e:
            print(f"[ERROR] Failed to initialize Point Cloud logger: {e}")
            self.enabled = False

    def log_frame(self, frame_number, raw_pc, stable_pc, display_pc, targets, presence):
        if not self.enabled or self.writer is None:
            return
            
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        try:
            # 1. Đếm số lượng điểm mây
            raw_count = len(raw_pc) if raw_pc is not None else 0
            stable_count = len(stable_pc) if stable_pc is not None else 0
            display_count = len(display_pc) if display_pc is not None else 0
            
            # 2. Tính toán thống kê SNR mây điểm thô (cột index 4)
            if raw_count > 0 and raw_pc is not None:
                # Đảm bảo raw_pc có cột thứ 5 (SNR)
                if raw_pc.ndim == 2 and raw_pc.shape[1] > 4:
                    raw_snr = raw_pc[:, 4]
                else:
                    raw_snr = np.zeros(raw_count)
                raw_min_snr = float(np.min(raw_snr))
                raw_max_snr = float(np.max(raw_snr))
                raw_mean_snr = float(np.mean(raw_snr))
            else:
                raw_min_snr, raw_max_snr, raw_mean_snr = 0.0, 0.0, 0.0
                
            # 3. Tính toán thống kê hình học cho mây điểm hiển thị (display_pc)
            if display_count > 0 and display_pc is not None:
                dx = display_pc[:, 0]
                dy = display_pc[:, 1]
                dz = display_pc[:, 2]
                ddop = display_pc[:, 3] if display_pc.shape[1] > 3 else np.zeros(display_count)
                
                display_min_x = float(np.min(dx))
                display_max_x = float(np.max(dx))
                display_mean_x = float(np.mean(dx))
                
                display_min_y = float(np.min(dy))
                display_max_y = float(np.max(dy))
                display_mean_y = float(np.mean(dy))
                
                display_min_z = float(np.min(dz))
                display_max_z = float(np.max(dz))
                display_mean_z = float(np.mean(dz))
                
                display_min_doppler = float(np.min(ddop))
                display_max_doppler = float(np.max(ddop))
                display_mean_doppler = float(np.mean(ddop))
            else:
                display_min_x, display_max_x, display_mean_x = 0.0, 0.0, 0.0
                display_min_y, display_max_y, display_mean_y = 0.0, 0.0, 0.0
                display_min_z, display_max_z, display_mean_z = 0.0, 0.0, 0.0
                display_min_doppler, display_max_doppler, display_mean_doppler = 0.0, 0.0, 0.0
                
            # 4. Thông tin mục tiêu (Targets)
            target_count = len(targets) if targets is not None else 0
            if targets:
                active_ids = ";".join(str(t.get("tid", t.get("id", ""))) for t in targets)
            else:
                active_ids = ""
                
            presence_val = int(presence) if presence is not None else 0
            
            row = [
                frame_number,
                timestamp_str,
                raw_count,
                stable_count,
                display_count,
                raw_min_snr,
                raw_max_snr,
                raw_mean_snr,
                display_min_x,
                display_max_x,
                display_mean_x,
                display_min_y,
                display_max_y,
                display_mean_y,
                display_min_z,
                display_max_z,
                display_mean_z,
                display_min_doppler,
                display_max_doppler,
                display_mean_doppler,
                target_count,
                active_ids,
                presence_val
            ]
            self.writer.writerow(row)
            self.log_file.flush()
        except Exception as e:
            print(f"[WARNING] Failed to write Point Cloud log: {e}")

    def close(self):
        if self.log_file is not None:
            try:
                self.log_file.close()
                print(f"[INFO] Point Cloud logger stopped and saved successfully to: {self.filepath}")
            except Exception as e:
                print(f"[WARNING] Failed to close Point Cloud logger: {e}")
            finally:
                self.log_file = None
                self.writer = None
