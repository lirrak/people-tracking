# BÁO CÁO CẬP NHẬT VERSION 27.0 - TÍCH HỢP HEADLESS DAEMON & SERIAL API CHO IQ9 LINUX

Hệ thống bám vết người 3D bằng mmWave Radar đã được nâng cấp thành công lên **Version 27.0** nhằm phục vụ việc thu thập dữ liệu và tích hợp trên thiết bị nhúng IQ9 Linux không đầu (headless) qua giao diện **Serial API**.

Mọi sửa đổi mã nguồn đã tuân thủ nghiêm ngặt chỉ thị của bạn: **Tuyệt đối không khởi chạy thử chương trình chính.**

---

## 🛠️ CHI TIẾT CÁC THAY ĐỔI ĐÃ TRIỂN KHAI

### 1. Cấu hình Serial API (`settings.py`)
* **Tệp sửa đổi**: [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* **Chi tiết**: Bổ sung phân đoạn cấu hình Serial API ở cuối file:
  * `ENABLE_SERIAL_API = True` (Bật cổng API)
  * `API_SERIAL_PORT = "COM15"` (Cổng Serial API truyền thông, người dùng có thể đổi thành `/dev/ttyUSB2` hoặc `/dev/ttyAMA0` trên IQ9 Linux).
  * `API_SERIAL_BAUDRATE = 115200` (Tốc độ truyền dữ liệu).

### 2. Xây dựng Trình chạy ngầm API (`api_server.py`)
* **Tệp khởi tạo mới**: [api_server.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/api_server.py)
* **Hoạt động**: Chạy đa luồng song song (Multi-threaded):
  * **Radar Collector (Thread 1)**: Thực thi cơ chế nạp cấu hình động (`sensorPosition`), đọc dữ liệu thô từ DATA UART (`DATA_PORT`), lọc mây điểm tĩnh, chạy DBSCAN gộp cụm, bám vết mục tiêu ảo và cập nhật biến luồng an toàn (`latest_frame_data`).
  * **Serial API Handler (Thread 2)**: Mở cổng API nối tiếp (`API_SERIAL_PORT`). Khi nhận lệnh `"GET_DATA\n"`, luồng này lập tức trích xuất dữ liệu khung hình mới nhất, định dạng thành chuỗi JSON trên 1 dòng duy nhất và phản hồi lại qua cổng. Bổ sung lệnh phụ `"GET_STATUS\n"` để truy xuất nhanh thông số chẩn đoán hệ thống.
  * **Main Thread**: In log chẩn đoán tiến trình định kỳ mỗi 10 giây lên màn hình console để quản trị viên giám sát trạng thái daemon.

### 3. Cấu hình Daemon chạy khởi động cùng IQ9 Linux (`radar_api.service`)
* **Tệp khởi tạo mới**: [radar_api.service](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/radar_api.service)
* **Chi tiết**: Tệp dịch vụ systemd mẫu để tự động khởi chạy và khởi động lại script `api_server.py` khi gặp lỗi sập nguồn trên thiết bị IQ9 Linux.

---

## 🔬 KẾ HOẠCH BÀN GIAO & MANUAL VERIFICATION

Hệ thống đã được kiểm tra biên dịch cú pháp tĩnh thành công 100% bằng câu lệnh:
```powershell
python -m py_compile settings.py api_server.py
```
*Kết quả biên dịch: Hoàn thành không phát hiện bất kỳ lỗi cú pháp nào.*

Khi bạn đã sẵn sàng chạy thử nghiệm thực tế (sau khi lắp phần cứng hoặc giả lập cổng serial kết nối), đây là quy trình kiểm tra:
1. **Khởi chạy Daemon**:
   ```powershell
   python api_server.py
   ```
2. **Gửi lệnh lấy dữ liệu**: Dùng Terminal nối tiếp kết nối vào cổng `API_SERIAL_PORT` gửi lệnh `GET_DATA`.
3. **Tiêu chuẩn đạt**: Nhận về chuỗi JSON chứa tọa độ người dùng `targets` và danh sách mây điểm phản xạ `point_cloud` đầy đủ.
