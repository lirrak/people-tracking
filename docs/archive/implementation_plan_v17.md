# KẾ HOẠCH TRIỂN KHAI v17.0 - XUẤT LOG POINT CLOUD VÀ QUAY MÀN HÌNH PHẦN MỀM TỰ ĐỘNG

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 17.0** để tích hợp tính năng xuất log thông số Point Cloud chi tiết ra file CSV (phục vụ phân tích ngoại tuyến) đồng thời khôi phục và tối ưu hóa tính năng quay màn hình giao diện Matplotlib tự động dưới dạng video độc lập 640x480 (không cần webcam).

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ PHƯƠNG ÁN NÂNG CẤP

### 1. Xuất log thông số Point Cloud ra file CSV (`pointcloud_logger.py` [NEW])
* **Mục tiêu**: Lưu giữ và thống kê các thông số mây điểm theo từng frame để phục vụ đánh giá thuật toán.
* **Giải pháp**: Tạo mới module `pointcloud_logger.py` chứa class `PointCloudLogger`.
* **Thông số thống kê mỗi frame**:
  * Số lượng điểm mây: Raw points, Stable points, Display/Filtered points.
  * Tọa độ hình học của mây điểm hiển thị: Min/Max/Mean (X, Y, Z).
  * Vận tốc Doppler: Min/Max/Mean.
  * Cường độ phản xạ SNR: Min/Max/Mean của mây điểm gốc và mây điểm hiển thị.
  * Thông tin mục tiêu: Số lượng target đang bám vết, ID của các mục tiêu hoạt động, trạng thái hiện diện (Presence).
* **Định dạng file**: File CSV lưu tự động vào thư mục `log/pointcloud_metrics_YYYYMMDD_HHMMSS.csv`.

### 2. Quay video màn hình giao diện Matplotlib 640x480 (`sync_recorder.py`)
* **Mục tiêu**: Quay lại luồng video hiển thị 3D của radar mà không cần mở Webcam vật lý (không bị khung hình đen chiếm dụng nửa màn hình).
* **Giải pháp**:
  * Tích hợp cấu hình linh hoạt trong `SyncRecorder`. Nếu tắt webcam (`ENABLE_WEBCAM = False`), kích thước video ghi hình sẽ tự động co về đúng **`640x480`** (chỉ chứa hình ảnh giao diện 3D radar trích xuất trực tiếp từ Matplotlib canvas).
  * Nếu bật webcam (`ENABLE_WEBCAM = True`), hệ thống tự động ghép đôi Side-by-Side thành video `1280x480` như trước đây.

### 3. Tích hợp cấu hình hệ thống (`settings.py`)
* **Giải pháp**: Bổ sung các tham số cấu hình bật/tắt logger và thư mục xuất:
  ```python
  # ============================================================
  # POINT CLOUD LOGGING SETTINGS
  # ============================================================
  ENABLE_POINTCLOUD_LOG = True        # Xuất log thông số point cloud ra file CSV
  POINTCLOUD_LOG_DIR = "log"          # Thư mục lưu log point cloud
  ```
* Bật lại `ENABLE_RECORDING = True` để kích hoạt tính năng quay video màn hình.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Cấu hình lại `ENABLE_RECORDING = True`.
* Thêm mới các tham số `ENABLE_POINTCLOUD_LOG` và `POINTCLOUD_LOG_DIR`.

### 📄 [MODIFY] [sync_recorder.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/sync_recorder.py)
* Cập nhật hàm `__init__` và `start`: tự động thiết lập kích thước video ghi hình là `(640, 480)` khi `webcam_enabled` là `False`, thay vì `(1280, 480)`.
* Cập nhật hàm `write_frame`: Nếu `webcam_enabled` là `False`, chuyển đổi Matplotlib plot trực tiếp từ RGB sang BGR, resize về `(640, 480)` và ghi trực tiếp vào file video mà không ghép nối với ảnh nền đen.

### 📄 [NEW] [pointcloud_logger.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_logger.py)
* Tạo mới file chứa class `PointCloudLogger`:
  * Tự động khởi tạo file CSV với tiêu đề đầy đủ các cột thống kê.
  * Hàm `log_frame(...)` tính toán các giá trị min/max/mean nhanh chóng thông qua thư viện numpy và ghi dòng dữ liệu vào file.
  * Hàm `close()` để giải phóng file an toàn khi kết thúc chương trình.

### 📄 [MODIFY] [main.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/main.py)
* Nhập khẩu `SyncRecorder` và `PointCloudLogger`.
* Khởi tạo `recorder` và `pc_logger` trong hàm `main()`.
* Tích hợp ghi log mây điểm mỗi frame bằng `pc_logger.log_frame(...)` và ghi hình giao diện bằng `recorder.write_frame(...)` trong vòng lặp chính.
* Giải phóng `pc_logger` và `recorder` an toàn trong khối lệnh `finally`.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử tính năng ghi hình màn hình 3D Radar độc lập
* Chạy chương trình `python main.py` với cấu hình `ENABLE_WEBCAM = False` và `ENABLE_RECORDING = True`.
* **Tiêu chuẩn vượt qua**:
  * Chương trình chạy bình thường không báo lỗi OpenCV.
  * Sinh ra file video mới `.mp4` trong thư mục `records/`.
  * Khi mở video lên, video hiển thị duy nhất khung hình Matplotlib 3D di chuyển mượt mà, kích thước chuẩn 640x480, không chứa khung webcam đen bên trái.

### 2. Kiểm thử xuất log thông số Point Cloud
* Kiểm tra thư mục `log/` sau lượt chạy.
* **Tiêu chuẩn vượt qua**:
  * Xuất hiện file CSV mới: `log/pointcloud_metrics_*.csv`.
  * Các cột dữ liệu ghi lại đầy đủ và chính xác số lượng điểm của từng loại mây điểm, các giải tọa độ thực tế hình học, SNR, Doppler và số lượng ID mục tiêu hoạt động tương ứng qua mỗi frame.
