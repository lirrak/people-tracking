import os
import time
import datetime
import threading
import numpy as np
from settings import *

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from pygrabber.dshow_graph import FilterGraph
    HAS_PYGRABBER = True
except ImportError:
    HAS_PYGRABBER = False

class SyncRecorder:
    def __init__(self):
        self.enabled = ENABLE_RECORDING and HAS_OPENCV
        self.webcam_enabled = ENABLE_WEBCAM and HAS_OPENCV
        self.cap = None
        self.writer = None
        self.webcam_frame = None
        self.running = False
        self.thread = None
        self.output_path = ""

    def start(self):
        if not HAS_OPENCV:
            print("[WARNING] OpenCV (cv2) is not installed! Webcam & Recording features are disabled.")
            print("[WARNING] Please run: pip install opencv-python")
            return

        if self.webcam_enabled:
            # Tự động dò tìm camera ngoài (Logitech USB) bằng pygrabber nếu có
            target_index = WEBCAM_INDEX
            if HAS_PYGRABBER:
                try:
                    graph = FilterGraph()
                    devices = graph.get_input_devices()
                    for idx, name in enumerate(devices):
                        name_lower = name.lower()
                        if "logi" in name_lower or "logitech" in name_lower or "c270" in name_lower or "usb camera" in name_lower:
                            target_index = idx
                            print(f"[INFO] Auto-detected external USB camera '{name}' at index {idx} using pygrabber.")
                            break
                except Exception as e:
                    print(f"[WARNING] Error scanning cameras with pygrabber: {e}")

            # Thử mở camera theo chỉ số đã cấu hình/dò tìm trước
            self.cap = cv2.VideoCapture(target_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(target_index)
                
            # Bộ tự động quét dò cổng nếu cổng cấu hình bị lỗi
            active_index = target_index
            if not self.cap.isOpened():
                print(f"[INFO] Configured/detected webcam index {target_index} failed. Auto-scanning active ports...")
                for test_idx in [1, 2, 0, 3]:
                    if test_idx == target_index:
                        continue
                    self.cap = cv2.VideoCapture(test_idx, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        self.cap = cv2.VideoCapture(test_idx)
                    if self.cap.isOpened():
                        active_index = test_idx
                        print(f"[INFO] Successfully auto-detected and connected to active webcam at index {test_idx}!")
                        break
                
            if not self.cap.isOpened():
                print(f"[WARNING] Cannot open webcam index or any fallback index. Disabling webcam.")
                self.webcam_enabled = False
            else:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WEBCAM_RESOLUTION[0])
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_RESOLUTION[1])
                
                # Khởi động warmup camera (đọc bỏ 15 frame đầu để cân bằng sáng và ổn định luồng)
                print("[INFO] Warming up camera sensor...")
                for _ in range(15):
                    self.cap.read()
                    time.sleep(0.02)
                    
                self.running = True
                self.thread = threading.Thread(target=self._webcam_loop, daemon=True)
                self.thread.start()
                print(f"[INFO] Webcam thread started successfully on camera index {active_index}.")

        if self.enabled:
            # Tạo thư mục records nếu chưa có
            os.makedirs(RECORD_OUTPUT_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_path = os.path.join(RECORD_OUTPUT_DIR, f"radar_webcam_sync_{timestamp}.mp4")
            
            # Kích thước khung hình Side-by-Side:
            # Webcam: 640 x 480
            # 3D Matplotlib: Resize về 640 x 480 để cân đối
            # Tổng chiều rộng = 640 + 640 = 1280, Chiều cao = 480
            # Sử dụng codec 'mp4v' cho file MP4
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.writer = cv2.VideoWriter(self.output_path, fourcc, RECORD_FPS, (1280, 480))
            print(f"[INFO] Video recording initialized. Saving to: {self.output_path}")

    def _webcam_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.webcam_frame = frame
            # Tốc độ đọc khoảng 30fps
            time.sleep(0.03)

    def write_frame(self, plot_img, frame_number=0):
        if not self.enabled or self.writer is None:
            return

        # 1. Chuẩn bị ảnh Webcam (Trái)
        if self.webcam_enabled and self.webcam_frame is not None:
            webcam_part = self.webcam_frame.copy()
        else:
            # Nếu không có webcam, tạo khung nền đen
            webcam_part = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(webcam_part, "Webcam Disabled/Unavailable", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Đảm bảo ảnh webcam đúng kích thước 640x480
        webcam_part = cv2.resize(webcam_part, (640, 480))

        # 2. Chuẩn bị ảnh Matplotlib 3D Plot (Phải)
        # plot_img nhận vào là RGB từ matplotlib buffer
        # Đổi định dạng từ RGB sang BGR để OpenCV ghi chính xác
        plot_bgr = cv2.cvtColor(plot_img, cv2.COLOR_RGB2BGR)
        plot_part = cv2.resize(plot_bgr, (640, 480))

        # 3. Ghép Side-by-Side
        combined_frame = np.hstack((webcam_part, plot_part))

        # 4. Vẽ Header/Thông tin đồng bộ lên Video
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        cv2.putText(combined_frame, f"REALITY (WEBCAM) | {timestamp_str}", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(combined_frame, f"RADAR 3D PLOT | Frame: {frame_number}", (655, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # 5. Ghi vào video
        self.writer.write(combined_frame)

        # Hiển thị cửa sổ webcam nhỏ chạy song song nếu muốn
        if self.webcam_enabled and self.webcam_frame is not None:
            cv2.imshow("Webcam Live Feed (Radar Sync)", self.webcam_frame)
            cv2.waitKey(1)

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)

        if self.cap is not None:
            self.cap.release()

        if self.writer is not None:
            self.writer.release()
            print(f"[INFO] Video recording stopped and saved successfully to: {self.output_path}")

        if HAS_OPENCV:
            cv2.destroyAllWindows()
