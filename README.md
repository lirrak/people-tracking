# IWR6843AOP 3D People Tracking, Human Box & API Server

Phiên bản này kế thừa cấu trúc phân tách gói tin UART gốc và bổ sung quy trình xử lý dữ liệu đám mây điểm (point-cloud pipeline) nâng cao kết hợp với HTTP Web API Server, Serial API & Systemd Service để chạy ngầm trên thiết bị nhúng IQ9 Linux.

---

## 🌟 Các tính năng & Thuật toán cốt lõi (Version 1.0 - Version 28.0)

Hệ thống đã trải qua quá trình tối ưu hóa liên tục để giải quyết các vấn đề nhiễu sàn, bóng ma tĩnh, tráo đổi ID mục tiêu, và đồng bộ tọa độ không gian:

1. **Bộ lọc ROI (Region of Interest)**: Lọc chiều cao và không gian hoạt động thực tế của con người theo cả 3 trục X, Y, Z (`PC_ROI_X`, `PC_ROI_Y`, `PC_ROI_Z`).
2. **Bộ lọc chất lượng điểm mây (Point Quality & Doppler Outlier)**: Lọc các điểm phản xạ nhiễu dựa trên cường độ tín hiệu phản hồi SNR (`MIN_POINT_SNR`) và loại bỏ các điểm có vận tốc Doppler bất thường không thuộc về chuyển động của người.
3. **Bộ ổn định đám mây điểm theo thời gian (Temporal Point Cloud Stabilizer)**: Gom tích lũy điểm mây qua cấu trúc Voxel 3D liên frame để giảm nhấp nháy, tăng mật độ điểm của cơ thể khi đứng im lâu.
4. **Phân cụm thích nghi (Adaptive DBSCAN)**: Tự động điều chỉnh bán kính gộp cụm `eps` tăng dần theo khoảng cách $R$ tới radar (`eps = base_eps + k * R`) giúp nhận diện và khoanh vùng mục tiêu chính xác ở cả cự ly gần và xa.
5. **Bộ lọc IMM (Interacting Multiple Model) 3D**: Chạy song song hai mô hình động học **Constant Velocity (CV)** (di chuyển tích cực) và **Stationary (STOP)** (đứng yên) giúp bám vết mượt mà, ngăn chặn hiện tượng trôi hộp hay mất dấu khi người đứng im.
6. **Thuật toán gán cặp Hungarian (Kuhn-Munkres)**: Sử dụng ma trận chi phí tối ưu hóa toàn cục (khoảng cách 3D Euclidean, độ lệch vận tốc Doppler, và khoảng cách Mahalanobis) để gán cụm điểm vào ID vết bám, chống nhảy ID hoặc tráo ID khi hai người đi giao cắt nhau.
7. **Khóa trạng thái động & Cổng bảo vệ thích nghi (Dynamic State Locking & Adaptive Spatial Gate)**: Khắc phục triệt để lỗi "Khóa cứng bóng ma tĩnh (Lock-on Trap)". Khi người di chuyển, mở rộng vùng bảo vệ điểm tĩnh (`r_prot = 0.85m`); khi đứng im, thu hẹp (`r_prot = 0.45m`); khi là vật tĩnh hoàn toàn, đóng hẳn (`r_prot = 0.0m`) để bộ lọc Doppler thô tự động xóa sạch điểm phản xạ.
8. **Phân loại tư thế (Posture Classification)**: Nhận diện tư thế (`STANDING`, `SITTING`, `LYING/FALLEN`) dựa trên phân bố hình học đám mây điểm theo trục đứng Z.
9. **Nhận diện té ngã Deep Learning (ONNX)**: Tích hợp mô hình Deep Learning ONNX (`models/radar_fall_detection.onnx`) phân tích chuỗi 30 khung hình gần nhất kết hợp resampling 32 điểm cố định để nhận diện trạng thái ngã (`NORMAL`, `FALLING`, `FALLEN`).
10. **Bù hao hụt độ lợi anten biên (Antenna Edge Compensation)**: Tự động tính toán nhân bù cường độ SNR ở rìa quét biên ngoài 40 độ Azimuth để bù đắp sự suy hao vật lý tự nhiên của anten patch.
11. **Đồng bộ Camera & Ghi hình**: Hỗ trợ ghi song song side-by-side Webcam và đồ thị Radar 3D. Tự động khóa góc nhìn đồ họa Matplotlib viewport trùng khớp với góc camera Logitech đặt trên đầu radar chĩa xuống.
12. **Dịch vụ Headless Dual-API Server**: Cho phép chạy ngầm không cần đồ họa, truyền luồng JSON thời gian thực qua HTTP & WebSocket cổng `5002` hoặc qua cổng Serial phụ (`COM15` / `/dev/ttyUSB2`) cho vi điều khiển ngoại vi.
13. **Watchdog khép kín hai tầng (Hot & Cold Watchdog)**: Tự động phát hiện mất dữ liệu hoặc ngắt kết nối cổng USB UART để reset cổng, nạp lại cấu hình động xuống radar chip mà không làm sập server API.

---

## 📁 Cấu trúc thư mục dự án

```text
├── api_server.py             # Entry point cho dịch vụ chạy ngầm Headless API Server
├── main.py                   # Entry point cho giao diện kiểm thử trực quan (Matplotlib 3D GUI)
├── settings.py               # Tệp cấu hình tham số toàn cục (Người dùng chỉnh sửa)
├── radar_api.service         # File cấu hình dịch vụ Systemd chạy ngầm trên Linux IQ9
├── src/                      # Thư mục mã nguồn lõi
│   ├── config_sender.py      # Gửi cấu hình .cfg xuống cổng UART CFG của radar
│   ├── constants.py          # Định nghĩa hằng số hệ thống
│   ├── fall_detector.py      # Bộ nhận diện ngã bằng hình học & mô hình Deep Learning ONNX
│   ├── filters.py            # Lọc bám vết nâng cao, GhostTargetFilter, IMM, Hungarian
│   ├── parsers.py            # Giải mã các gói tin UART thô từ radar
│   ├── pointcloud_logger.py  # Ghi dữ liệu point cloud ra CSV
│   ├── pointcloud_processing.py # Quản lý luồng xử lý mây điểm, Adaptive DBSCAN, VirtualTracker
│   ├── serial_utils.py       # Tiện ích quét cổng Serial tự động
│   ├── sync_recorder.py      # Ghi hình đồng bộ webcam và giao diện
│   ├── uart_parser.py        # Tự động hóa kết nối và phân tách gói tin UART
│   └── visualization.py      # Bản vẽ giao diện Matplotlib 3D, viewport và HUD
├── docs/                     # Báo cáo phân tích và tài liệu kỹ thuật
│   ├── Root_Cause_Analysis.md # Phân tích chi tiết các lỗi cốt lõi (Lock-on, Lệch tọa độ...)
│   └── walkthrough.md        # Báo cáo kết quả thử nghiệm thực tế các phiên bản
├── models/                   # Thư mục chứa model Deep Learning ONNX
│   └── radar_fall_detection.onnx
├── log/                      # Thư mục lưu file log CSV point cloud
└── records/                  # Thư mục lưu các video ghi hình phân tích thực tế
```

---

## 🚀 Hướng dẫn khởi chạy

### Chạy giao diện kiểm thử trực quan (GUI 3D)
```bash
python main.py
```

### Chạy độc lập ngầm (Headless API Daemon)
```bash
python api_server.py
```

---

## ⚙️ Cài đặt chạy tự động (Systemd Service) trên IQ9 Linux

Để dịch vụ tự chạy mỗi khi **khởi động lại máy (reboot)**, **bật nguồn**, hoặc **tự động phục hồi khi cắm lại cáp radar**, thực hiện đăng ký Systemd Service:

1. Copy tệp dịch vụ hệ thống vào thư mục quản lý:
   ```bash
   sudo cp "/home/ubuntu/sensor/People Tracking/radar_api.service" /etc/systemd/system/
   ```
2. Nạp lại cấu hình dịch vụ:
   ```bash
   sudo systemctl daemon-reload
   ```
3. Bật dịch vụ tự khởi động cùng hệ thống:
   ```bash
   sudo systemctl enable radar_api.service
   ```
4. Khởi chạy dịch vụ ngay lập tức:
   ```bash
   sudo systemctl start radar_api.service
   ```
5. Xem nhật ký log thời gian thực:
   ```bash
   journalctl -u radar_api.service -f -n 100
   ```

---

## 🌐 API Endpoints (WebSocket & HTTP)

Cổng API `5002` hỗ trợ song song hai giao thức (Dual-protocol):

### 1. Luồng truyền dữ liệu thời gian thực (WebSocket - KHUYÊN DÙNG)
Kết nối tới địa chỉ sau bằng thư viện WebSocket của bất kỳ ngôn ngữ lập trình nào (Javascript, C++, C#, Python, v.v.):
* **Địa chỉ WebSocket**: `ws://<local_ip>:5002/`

**Hoạt động**: Ngay khi kết nối được thiết lập (handshake thành công), mỗi khi radar xử lý xong một khung hình mới (15-30 FPS), Server sẽ **tự động đẩy (push)** một chuỗi JSON chứa đầy đủ mây điểm và danh sách người bám vết đến client mà không cần gọi polling.

### 2. Giao thức tương thích ngược HTTP API

#### Lấy thông tin cảm biến (`GET /api/sensors`)
Phản hồi dữ liệu thời gian thực của radar gồm mây điểm phản xạ 3D và các mục tiêu người đang bám vết.

**Cổng kết nối**: `5002` (cấu hình trong `settings.py`)

#### Ví dụ JSON kết quả trả ra:
```json
{
  "status": "success",
  "data": {
    "frame_number": 1986,
    "presence": true,
    "point_cloud_count": 119,
    "point_cloud": [
      [0.1, 0.431, 1.142, -0.139, 15.2],
      [0.24, 1.039, 1.281, -0.209, 13.8],
      [0.095, 0.496, 1.118, -0.139, 16.2]
    ],
    "targets": [
      {
        "tid": 4,
        "posX": 0.074,
        "posY": 0.655,
        "posZ": 0.133,
        "velX": 0.433,
        "velY": 0.171,
        "velZ": 0.063,
        "humanScore": 34.6,
        "isVirtual": false,
        "height": 0.56,
        "posture": "STANDING",
        "fall_status": "NORMAL",
        "fall_alert": false
      }
    ],
    "mode": "PEOPLE_TRACKING",
    "timestamp": "2026-06-09 07:21:09"
  }
}
```

#### Giải thích ý nghĩa các trường dữ liệu:

* **`status`**: Trạng thái yêu cầu (`"success"` khi có dữ liệu ổn định, hoặc `"waiting"` khi radar đang khởi động).
* **`data`**: Chứa toàn bộ nội dung cảm biến giải mã được.
  * **`frame_number`**: Số thứ tự khung hình gửi từ radar (tăng dần liên tục).
  * **`presence`**: Xác định có người trong vùng quét hay không (`true`/`false`).
  * **`point_cloud_count`**: Tổng số lượng điểm mây phản xạ 3D quét được ở khung hình hiện tại.
  * **`point_cloud`**: Mảng 2 chiều chứa danh sách các điểm phản xạ, mỗi điểm là một mảng 5 phần tử: `[X, Y, Z, Vận tốc, SNR]`
    * **`X`**: Tọa độ ngang (trái/phải) của điểm so với radar (mét).
    * **`Y`**: Tọa độ khoảng cách (trước mặt) từ điểm tới radar (mét).
    * **`Z`**: Tọa độ chiều cao (trên/dưới) của điểm so với radar (mét).
    * **`Vận tốc`**: Vận tốc hướng tâm Doppler của điểm (m/s), giá trị âm là đang tiến lại gần, dương là đi ra xa.
    * **`SNR`**: Cường độ phản tín hiệu (Signal-to-Noise Ratio), càng cao tức là điểm phản xạ từ vật thể đặc/rõ nét (như cơ thể người).
  * **`targets`**: Danh sách các mục tiêu người (hộp bám vết) đang hoạt động:
    * **`tid`**: Mã định danh (ID) duy nhất của mục tiêu người đó.
    * **`posX`, `posY`, `posZ`**: Tọa độ tâm khối 3D của người (mét).
    * **`velX`, `velY`, `velZ`**: Vectơ vận tốc di chuyển thực tế theo 3 hướng X, Y, Z (m/s).
    * **`humanScore`**: Điểm số đánh giá hình thể (độ tin cậy cụm điểm này có phải là con người thực tế không).
    * **`isVirtual`**: Xác định mục tiêu ảo tự gộp (`true` nếu tự nội suy từ cụm điểm mây khi phần cứng chưa lock, `false` nếu nhận trực tiếp từ tracking phần cứng).
    * **`height`**: Chiều cao ước tính của hộp người quét được (mét).
    * **`posture`**: Tư thế nhận diện hiện tại (`"STANDING"`: Đứng, `"SITTING"`: Ngồi, `"LYING/FALLEN"`: Nằm sàn/Ngã).
    * **`fall_status`**: Trạng thái té ngã (`"NORMAL"`: Bình thường, `"FALLING"`: Đang ngã xuống, `"FALLEN"`: Đã ngã hẳn dưới sàn).
    * **`fall_alert`**: Cảnh báo nguy hiểm khi ngã (`true` nếu trạng thái là `"FALLEN"`, ngược lại là `false`).
  * **`mode`**: Chế độ hoạt động của radar (`"PEOPLE_TRACKING"`).
  * **`timestamp`**: Thời gian hệ thống ghi nhận khung hình (`YYYY-MM-DD HH:MM:SS`).

### 2. Trạng thái cảnh báo hiện diện & té ngã (`GET /api/vitals/alert`)
Phản hồi trạng thái nhanh nhằm kích hoạt hệ thống báo động / tích hợp nhà thông minh.

* **Khi phát hiện có bất kỳ ai bị ngã trong phòng (`fall_alert` = true)**:
  Trả về trạng thái nguy hiểm `"status": "fall"`.
  ```json
  {
    "status": "fall",
    "message": "CẢNH BÁO: Phát hiện người bị ngã trong phòng!",
    "data": {
      "presence": true,
      "target_count": 1,
      "targets": [
        {
          "tid": 4,
          "posX": 0.074,
          "posY": 0.655,
          "posZ": 0.133,
          "velX": 0.433,
          "velY": 0.171,
          "velZ": 0.063,
          "humanScore": 84.5,
          "isVirtual": false,
          "height": 0.56,
          "posture": "LYING/FALLEN",
          "fall_status": "FALLEN",
          "fall_alert": true
        }
      ]
    }
  }
  ```
* **Khi có người hoạt động bình thường**:
  Trả về trạng thái an toàn `"status": "normal"`.
  ```json
  {
    "status": "normal",
    "message": "Phát hiện có người hoạt động bình thường",
    "data": {
      "presence": true,
      "target_count": 1,
      "targets": [...]
    }
  }
  ```
* **Khi phòng trống hoàn toàn**:
  Trả về trạng thái phòng trống `"status": "alert"`.
  ```json
  {
    "status": "alert",
    "message": "Cảnh báo: Không phát hiện người trong khu vực",
    "data": {
      "presence": false,
      "target_count": 0
    }
  }
  ```

---

## 📟 Giao thức Serial API (Truy vấn qua cổng UART vật lý)

Khi kích hoạt `ENABLE_SERIAL_API = True` trong [settings.py](file:///home/ubuntu/sensor/People%20Tracking/settings.py), API Server sẽ lắng nghe các lệnh gửi tới qua cổng Serial được chỉ định với Baudrate mặc định là `115200`.

### Danh sách các tập lệnh Serial hỗ trợ:

1. **Lệnh `GET_DATA`**:
   * **Mô tả**: Yêu cầu lấy thông tin cảm biến chi tiết.
   * **Phản hồi**: Trả về một dòng chuỗi JSON chứa toàn bộ dữ liệu cảm biến thời gian thực (giống định dạng HTTP API) kết thúc bằng ký tự xuống dòng `\n`.
   * **Ví dụ kết quả**: `{"status": "success", "data": {"frame_number": 1986, "presence": true, ...}}\n`

2. **Lệnh `GET_STATUS`**:
   * **Mô tả**: Yêu cầu lấy trạng thái tóm tắt nhanh để tiết kiệm dung lượng truyền dẫn và xử lý trên MCU.
   * **Phản hồi**: Trả về một dòng văn bản thô (plain-text) chứa trạng thái hiện diện và số lượng đối tượng hoạt động, kết thúc bằng ký tự `\n`.
   * **Ví dụ kết quả**: `STATUS: OK | PRESENCE: True | TARGETS: 1\n`

---

## 🛠️ Tùy chỉnh tham số hệ thống trong settings.py

Mọi cấu hình nâng cao đều có thể tùy chỉnh trực tiếp trong file [settings.py](file:///home/ubuntu/sensor/People%20Tracking/settings.py):

### 1. Cấu hình Cổng Kết Nối Radar
* `CFG_PORT` & `DATA_PORT`: Cổng Serial nạp cấu hình và đọc gói tin dữ liệu (ví dụ: `/dev/ttyUSB0` & `/dev/ttyUSB1`).
* `SKIP_CONFIG`: Nếu đặt là `True`, hệ thống bỏ qua việc nạp config, chỉ đọc luồng UART DATA (dành cho radar đã được flash cấu hình cứng tự khởi chạy).

### 2. Cấu hình Lọc Không Gian & Biến Đổi Tọa Độ
* `PC_ROI_X`, `PC_ROI_Y`, `PC_ROI_Z`: Giới hạn vùng không gian quan tâm (ROI) của mây điểm (m).
* `ENABLE_COORD_TRANSFORM`: Bật biến đổi tọa độ phòng dựa trên góc nghiêng lắp đặt.
* `RADAR_TILT_ANGLE_DEG`: Góc nghiêng vật lý chĩa xuống của radar (độ).
* `RADAR_MOUNT_HEIGHT_M`: Chiều cao lắp đặt thực tế của radar so với mặt đất (mét).

### 3. Cấu hình IMM & Hungarian Association
* `ENABLE_IMM_FILTER`: Bật bộ lọc IMM cao cấp (Stop & CV model) thay thế cho Kalman 3D đơn.
* `IMM_TRANSITION_MATRIX`: Ma trận chuyển đổi xác suất giữa mô hình CV và Stop.
* `ENABLE_HUNGARIAN_ASSOCIATION`: Bật bộ gán cặp Kuhn-Munkres để liên kết ID tối ưu toàn cục.

### 4. Cấu hình Bộ Lọc Tĩnh Vật (Clutter Filtering)
* `ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER`: Bật lọc nhiễu tĩnh vật mức độ điểm mây.
* `STATIC_CLUTTER_POINT_PROTECTION_RADIUS`: Bán kính bảo vệ điểm tĩnh quanh vết bám thực tế để không bị xóa nhầm người đứng im.

### 5. Cấu hình Webcam & Video Recording
* `ENABLE_WEBCAM`: Bật camera ghi hình side-by-side.
* `ENABLE_RECORDING`: Tự động xuất file video MP4 ghi nhận thử nghiệm vào thư mục `records`.

### 6. Nhận Diện Té Ngã Deep Learning
* `ENABLE_DEEP_FALL_DETECTION`: Bật mô hình Deep Learning ONNX.
* `DEEP_FALL_MODEL_PATH`: Đường dẫn tới tệp model ONNX.
* `DEEP_FALL_SEQ_LEN`: Độ dài chuỗi quan sát (mặc định 30 frame = 1.5 giây).

---

## 🔌 Hướng dẫn tích hợp & Lập trình WebSocket

### 1. So sánh WebSocket vs HTTP API truyền thống

| Đặc điểm | HTTP API (Cách cũ) | WebSocket API (Cách mới) |
| :--- | :--- | :--- |
| **Cơ chế** | **Yêu cầu - Phản hồi (Request-Response)**<br>Client hỏi thì Server mới trả lời. | **Hai chiều liên tục (Bi-directional)**<br>Server chủ động đẩy dữ liệu ngay khi có. |
| **Trạng thái** | **Stateless**: Đóng kết nối ngay sau khi phản hồi. | **Persistent**: Kết nối luôn mở trong suốt phiên làm việc. |
| **Độ trễ (Latency)**| **Cao** (do tạo kết nối TCP mới và gửi gói HTTP Header nặng ~1KB mỗi lần gọi). | **Cực thấp** (Header chỉ nặng 2 - 10 bytes, đẩy dữ liệu đi ngay lập tức). |

### 2. Đường link kết nối WebSocket:
* **Kết nối cục bộ (trên cùng máy IQ9)**: `ws://127.0.0.1:5002/`
* **Kết nối mạng LAN (từ thiết bị khác)**: `ws://<IP_MÁY_IQ9>:5002/` (Ví dụ: `ws://192.168.1.37:5002/`)

---

### 3. Code mẫu lập trình phía Client

#### 🔹 Ví dụ 1: HTML & Javascript (Dành cho Web Frontend / Dashboard)
Trình duyệt web hỗ trợ WebSocket mặc định mà không cần cài thêm bất kỳ thư viện nào:

```html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Radar Real-time Dashboard</title>
</head>
<body>
    <h2>Dữ liệu Radar thời gian thực</h2>
    <div id="status">Đang kết nối...</div>
    <pre id="data-output">Đang chờ dữ liệu...</pre>

    <script>
        const wsUrl = "ws://127.0.0.1:5002/"; 
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            document.getElementById("status").innerText = "Trạng thái: ĐÃ KẾT NỐI";
            document.getElementById("status").style.color = "green";
        };

        ws.onmessage = (event) => {
            const radarFrame = JSON.parse(event.data);
            document.getElementById("data-output").innerText = JSON.stringify(radarFrame, null, 2);
            if (radarFrame.presence) {
                console.log(`Phát hiện có ${radarFrame.targets.length} người!`);
            }
        };

        ws.onclose = () => {
            document.getElementById("status").innerText = "Trạng thái: MẤT KẾT NỐI";
            document.getElementById("status").style.color = "red";
        };
    </script>
</body>
</html>
```

#### 🔹 Ví dụ 2: Python Client (Dành cho phần mềm Backend / Lưu Database)
1. Cài đặt thư viện: `pip install websockets`
2. Viết file client:
```python
import asyncio
import websockets
import json

async def read_radar_stream():
    uri = "ws://127.0.0.1:5002"
    async with websockets.connect(uri) as websocket:
        print("[*] Đã kết nối tới Radar WebSocket Server.")
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"Frame: {data['frame_number']} | Presence: {data['presence']} | Points: {data['point_cloud_count']}")
            except websockets.ConnectionClosed:
                print("[!] Kết nối bị đóng.")
                break

asyncio.run(read_radar_stream())
```

#### 🔹 Ví dụ 3: ESP32 / Arduino / C++ (Dành cho vi điều khiển bật tắt thiết bị ngoại vi)
* Sử dụng thư viện **`arduinoWebSockets`** của tác giả Markus Sattler:
```cpp
#include <WiFi.h>
#include <WebSocketsClient.h>

WebSocketsClient webSocket;

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            Serial.printf("[WSc] Disconnected!\n");
            break;
        case WStype_CONNECTED:
            Serial.printf("[WSc] Connected to: %s\n", payload);
            break;
        case WStype_TEXT:
            Serial.printf("[WSc] Nhận JSON: %s\n", payload);
            // Sử dụng ArduinoJson để parse và điều khiển thiết bị ngoại vi ở đây
            break;
    }
}

void setup() {
    Serial.begin(115200);
    WiFi.begin("Tên_Wifi", "Mật_khẩu");
    
    webSocket.begin("192.168.1.37", 5002, "/"); // IP của máy IQ9
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
}

void loop() {
    webSocket.loop();
}
```
