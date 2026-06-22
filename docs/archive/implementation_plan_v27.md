# KẾ HOẠCH TRIỂN KHAI v27.0 - TÍCH HỢP SERIAL API TRÊN THIẾT BỊ IQ9 LINUX

Tài liệu này đề xuất phương án cải tiến hệ thống lên **Version 27.0** nhằm tích hợp giao diện **Serial API** chạy cục bộ trên thiết bị IQ9 Linux. Giao diện này sẽ phản hồi chuỗi JSON chứa toàn bộ dữ liệu hiển thị HUD (mây điểm, mục tiêu, độ hiện diện) khi nhận được lệnh `"GET_DATA"` qua cổng Serial kết nối với máy tính/PLC hoặc các bộ điều khiển khác.

---

## 🔍 PHÂN TÍCH YÊU CẦU SERIAL API CỦA NGƯỜI DÙNG

### 1. Kiến trúc luồng hoạt động
* Thiết bị IQ9 Linux đóng vai trò là "Bộ điều khiển trung tâm" (Host):
  * **Đầu vào (Input)**: Đọc và giải mã dữ liệu radar IWR6843AOP qua 2 cổng nối tiếp (CFG và DATA UART) bằng luồng chạy ngầm.
  * **Đầu ra API (Output API)**: Mở một cổng Serial thứ 3 (cổng API, ví dụ `/dev/ttyUSB2` trên Linux hoặc `COM15` trên Windows) ở tốc độ `115200`.
  * **Giao thức phản hồi (Request-Response Protocol)**:
    1. Thiết bị hoặc phần mềm khác gửi lệnh dạng text `"GET_DATA\n"` vào cổng API của IQ9.
    2. IQ9 nhận lệnh, đóng gói khung hình radar mới nhất thành chuỗi JSON và gửi trả lại qua chính cổng Serial đó dưới dạng 1 dòng văn bản (kết thúc bằng `\n`).

### 2. Ưu điểm của giải pháp này
* Khớp hoàn toàn với cơ chế gọi dữ liệu của hệ sinh thái Arduino/C++ hiện tại của bạn.
* Cực kỳ nhẹ, không cần giao thức mạng TCP/IP, tránh được các vấn đề về cấu hình IP/Wifi trên thiết bị nhúng IQ9 Linux.

---

## 💡 CÁC SỬ ĐỔI ĐỀ XUẤT TRONG VERSION 27.0

Chúng ta sẽ tạo một tập lệnh chạy ngầm có tên [api_server.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/api_server.py) độc lập hoàn toàn với Matplotlib UI:

### 1. Cấu hình cổng Serial và API mới trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
Bổ sung các tham số cấu hình mà không làm ảnh hưởng đến các cài đặt cũ:
```python
# ============================================================
# SERIAL API SETTINGS (Version 27.0)
# ============================================================
# Cấu hình cổng kết nối Radar trên Linux IQ9 (khớp với hình ảnh phần cứng)
CFG_PORT = "/dev/ttyUSB0"        # Cổng CLI / Config (Baud 115200)
DATA_PORT = "/dev/ttyUSB1"       # Cổng Data (Baud 921600)

# Cấu hình cổng truyền xuất dữ liệu Serial API
ENABLE_SERIAL_API = True
API_SERIAL_PORT = "/dev/ttyUSB2" # Cổng Serial API xuất dữ liệu JSON (hoặc cổng bất kỳ tùy chọn kết nối sang PC/PLC)
API_SERIAL_BAUDRATE = 115200
```


### 2. Thiết kế Threading trong [api_server.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/api_server.py)
* **Thread 1 (Radar Driver)**:
  * Khởi tạo và nạp tham số cấu hình thích nghi (`sensorPosition`) lên radar.
  * Đọc liên tục và giải mã các gói TLV từ cổng DATA UART.
  * Lọc nhiễu động học, xác thực mục tiêu ảo, loại bỏ hộp ma tĩnh vật bằng các lớp xử lý sẵn có.
  * Cập nhật đối tượng trạng thái khung hình radar mới nhất vào một bộ đệm dùng chung.
* **Thread 2 (Serial API Handler)**:
  * Mở cổng nối tiếp kết nối API (`API_SERIAL_PORT`).
  * Liên tục lắng nghe lệnh gửi tới bằng hàm `readline()`.
  * Khi nhận được dòng lệnh `"GET_DATA"`, chuyển đổi dữ liệu bộ đệm mới nhất sang định dạng JSON và viết lại cổng serial.

### 3. Định dạng dữ liệu JSON xuất ra
Chuỗi JSON trả về sẽ bao gồm đầy đủ dữ liệu mây điểm và mục tiêu phục vụ việc dựng UI:
```json
{
  "frame_number": 3089,
  "presence": true,
  "mode": "PEOPLE_TRACKING",
  "point_cloud": [
    [0.91, 1.23, -0.02, 0.05, 12.5],
    [-0.45, 2.10, 0.15, -0.12, 18.2]
  ],
  "targets": [
    {
      "tid": 8,
      "posX": 1.15,
      "posY": 1.24,
      "posZ": 0.50,
      "velX": -0.01,
      "velY": 0.02,
      "velZ": 0.00,
      "humanScore": 85.0,
      "height": 1.70,
      "isVirtual": false
    }
  ]
}
```

---

## 🛠️ CẤU HÌNH DAEMON KHỞI ĐỘNG CÙNG IQ9 LINUX
Khi chuyển giao sang IQ9, chúng ta sẽ lưu tập lệnh này chạy ngầm dưới dạng một systemd daemon thông qua tệp cấu hình [radar_api.service](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/radar_api.service).

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### Kiểm tra cú pháp tĩnh
```powershell
python -m py_compile api_server.py
```

### Xác minh thủ công qua Serial Terminal
1. Sử dụng một phần mềm giả lập cổng Serial ảo (ví dụ: *com0com* trên Windows hoặc *socat* trên Linux) để tạo cặp cổng ảo (ví dụ `COM15` <-> `COM16`) để kiểm tra nếu không có phần cứng vật lý thứ 3.
2. Khởi chạy `python api_server.py`.
3. Dùng một Serial Terminal (như TeraTerm, Hercules, hoặc tập lệnh Python kiểm thử) mở cổng đối diện (`COM16` / 115200).
4. Gửi chuỗi `"GET_DATA\n"`.
5. **Tiêu chuẩn vượt qua**:
   * Nhận lại ngay lập tức một chuỗi JSON hợp lệ kết thúc bằng ký tự xuống dòng.
   * Định dạng JSON hoàn toàn đúng cú pháp, chứa đầy đủ các trường `point_cloud`, `targets`, và `presence`.
