# KẾ HOẠCH TRIỂN KHAI v25.0 - GIAO DIỆN RADAR HUD TRÒN 2D & TỰ ĐỘNG RESET PHẦN CỨNG

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 25.0** nhằm mang lại hai cải tiến quan trọng:
1. **Thiết kế lại toàn bộ giao diện (UI Redesign)**: Thay đổi từ biểu đồ khung dây 3D phức tạp sang giao diện màn hình radar quét tròn 2D (2D Circular Radar HUD) chuẩn quân sự/khoa học viễn tưởng, mô phỏng đúng bức ảnh mẫu.
2. **Tự động Reset phần cứng (Auto Reset)**: Tự động gửi tín hiệu reset phần cứng thông qua các chân điều khiển DTR/RTS trên cổng CP2105 Enhanced COM Port (`COM13`) trước khi gửi tệp cấu hình `.cfg`, giúp loại bỏ hoàn toàn việc phải ấn nút Reset vật lý trên mạch IWR6843AOP.

---

## 🛠️ CHI TIẾT CÁC THAY ĐỔI ĐỀ XUẤT

### 1. Tự động Reset phần cứng qua DTR/RTS
* **Tệp thay đổi**: [config_sender.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/config_sender.py)
* **Giải pháp**:
  * Khi hàm `send_config_lines` bắt đầu thực thi và mở cổng `CFG_PORT` (`COM13`), chúng ta sẽ điều khiển các đường tín hiệu DTR và RTS của đối tượng `serial.Serial`.
  * Trình tự Reset:
    1. Kéo DTR và RTS xuống mức thấp (trong `pySerial` đặt `ser.dtr = True` và `ser.rts = True` để kích hoạt mạch đảo reset tích cực thấp) trong `0.2` giây nhằm giữ chip IWR6843 ở trạng thái Reset.
    2. Giải phóng reset bằng cách đặt `ser.dtr = False` và `ser.rts = False` để chip khởi động lại bình thường.
    3. Đợi `1.0` giây để bootloader khởi động hoàn tất và CLI sẵn sàng tiếp nhận lệnh.
    4. Gọi `ser.reset_input_buffer()` và `ser.reset_output_buffer()` để xóa toàn bộ dữ liệu rác tích tụ trong quá trình khởi động trước khi bắt đầu gửi các dòng cấu hình.

---

### 2. Thiết kế giao diện Radar HUD quét tròn 2D (Retro-Futuristic)
* **Tệp thay đổi**: [visualization.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/visualization.py)
* **Giải pháp**:
  * **Chuyển đổi sang 2D Cartesian Plane**: Thay thế bộ dựng hình 3D bằng giao diện 2D phẳng (`ax.set_aspect('equal')`, tắt hệ trục mặc định `ax.axis('off')`), sử dụng nền đen (`#000000`) và lưới phụ màu xanh lá cực tối (`#002200`).
  * **Vẽ các vòng tròn radar**: Vẽ các đường tròn đồng tâm tại bán kính $2\text{m}, 4\text{m}, 6\text{m}, 8\text{m}, 10\text{m}$ (xanh lá trung bình `#004d00`) kèm các nhãn khoảng cách tương ứng.
  * **Vẽ vạch chia độ**: Vẽ các vạch chia độ ngắn xung quanh đường tròn ngoài cùng ($10\text{m}$) từ $0^\circ$ đến $350^\circ$, đánh nhãn số độ mỗi $30^\circ$.
  * **Đường quét động (Rotating Sweep Line)**:
    * Vận tốc quét: $90^\circ/\text{giây}$ (1 vòng quay mất 4 giây). Góc quét hiện tại được tính tự động từ hàm thời gian hệ thống: `sweep_angle = (time.time() * 90.0) % 360.0`.
    * Vẽ đường quét chính màu xanh neon sáng (`#00ff00`, linewidth=2.5) từ tâm ra biên.
    * Vẽ dải đuôi quét (Wedge Glow): Chia góc từ $\theta_{\text{sweep}} - 45^\circ$ đến $\theta_{\text{sweep}}$ thành 15 phân đoạn nhỏ, vẽ các hình tam giác lấp đầy với độ trong suốt (alpha) giảm dần từ $0.3$ về $0.0$ để tạo hiệu ứng phát sáng phốt-pho mờ dần.
  * **Hiệu ứng mờ dần của Điểm mây & Target (Sweep-based Alpha Decay)**:
    * Tính góc của từng điểm mây và tâm của từng target theo góc hướng $Y$ (hướng thẳng đứng là $0^\circ$): `angle = np.degrees(np.arctan2(x, y)) % 360.0`.
    * Tính độ lệch góc so với đường quét hiện tại: `diff = (sweep_angle - angle) % 360.0`.
    * Điểm/Mục tiêu sẽ sáng nhất khi đường quét vừa đi qua (`diff` nhỏ) và mờ dần khi đường quét đi xa:
      $$\text{alpha} = \begin{cases} \max(0.05, 1.0 - \frac{\text{diff}}{180.0}) & \text{nếu } \text{diff} < 180^\circ \\ 0.05 & \text{nếu } \text{diff} \ge 180^\circ \end{cases}$$
    * Điểm mây hiển thị dưới dạng các chấm xanh nhỏ sáng mờ dần.
    * Target hiển thị dưới dạng chấm tròn neon xanh lục rực rỡ, bao quanh bởi một vòng tròn phát sáng mờ (`alpha * 0.15`), kèm theo nhãn dữ liệu kiểu console (`TID`, `Chiều cao thật`, `Điểm dáng người`) và vectơ vận tốc (quiver).
    * Sensor vẽ thành một tam giác xanh sáng ngay tại tâm $(0,0)$.
  * **Tích hợp các bảng Diagnostics (HUD Widgets)**:
    * **Góc trên bên trái**: Hệ thanh hiển thị trạng thái hệ thống (`SYS STATUS`).
    * **Góc trên bên phải**: Biểu đồ dạng sóng dao động (`SIGNAL WAVE`) cập nhật liên tục theo hàm sine + nhiễu ngẫu nhiên.
    * **Góc dưới bên trái**: Khung lưới tọa độ hình cầu quay 3D dạng wireframe (`GEOMETRIC ANCHOR`).
    * **Góc dưới bên phải**: Hệ cột xung tần phổ dạng equalizer (`SPECTRUM`) nhấp nháy động học.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### Kiểm tra cú pháp tự động
Chạy kiểm tra biên dịch lỗi cú pháp Python trước khi kích hoạt (khi được phép):
```powershell
python -m py_compile config_sender.py visualization.py
```

### Xác minh thủ công
1. **Kiểm tra Auto Reset**: Chạy `python main.py`. Xác minh rằng radar tự khởi động lại và nạp cấu hình thành công mà không cần người dùng nhấn nút Reset vật lý trên phần cứng.
2. **Kiểm tra giao diện tròn & đường quét**: Quan sát cửa sổ hiển thị trực quan:
   * Nền đen hoàn toàn với lưới xanh lá dịu mắt.
   * Đường quét chính xoay đều 4 giây/vòng kéo theo đuôi phốt-pho mờ dần.
   * Điểm mây và target phát sáng rực rỡ khi đường quét đi qua và mờ dần tự nhiên.
   * Các khối đồ họa chẩn đoán ở 4 góc hoạt động đồng bộ, mượt mà.
3. **Kiểm tra ghi hình**: Xác minh tệp video ghi trong thư mục `records` vẫn hoạt động tốt và lưu đúng ảnh giao diện HUD mới ghép đôi với Webcam.
