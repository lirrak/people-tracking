# BÁO CÁO CẬP NHẬT VERSION 25.0 - GIAO DIỆN RADAR HUD TRÒN 2D & TỰ ĐỘNG HARDWARE RESET

Hệ thống bám vết người 3D bằng mmWave Radar đã được nâng cấp thành công lên **Version 25.0** nhằm mang lại giao diện radar HUD quét tròn 2D chuẩn khoa học viễn tưởng và cơ chế tự động nạp cấu hình không cần nhấn nút Reset vật lý.

Mọi sửa đổi mã nguồn đã tuân thủ nghiêm ngặt chỉ thị của bạn: **Tuyệt đối không tự ý chạy thử chương trình chính.**

---

## 🛠️ CHI TIẾT CÁC THAY ĐỔI ĐÃ TRIỂN KHAI

### 1. Tự động Reset phần cứng qua DTR/RTS (`config_sender.py`)
* **Tệp sửa đổi**: [config_sender.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/config_sender.py)
* **Chi tiết**:
  * Thêm đoạn mã điều khiển đường truyền `dtr` và `rts` trực tiếp trong `send_config_lines` sau khi khởi tạo đối tượng `serial.Serial` với cổng `COM13`.
  * Giữ tín hiệu Reset ở mức thấp (tương đương `ser.dtr = True` và `ser.rts = True` trên cổng nối tiếp) trong `0.2` giây.
  * Thả tín hiệu Reset về mức cao (tương đương `ser.dtr = False` và `ser.rts = False`).
  * Đợi `1.0` giây để chip hoàn tất quá trình khởi động lại mềm và CLI sẵn sàng.
  * Gọi `ser.reset_input_buffer()` và `ser.reset_output_buffer()` để dọn sạch bộ đệm trước khi gửi các câu lệnh cấu hình.

### 2. Giao diện Radar HUD quét tròn 2D Retro-Futuristic (`visualization.py`)
* **Tệp sửa đổi**: [visualization.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/visualization.py)
* **Chi tiết**:
  * Chuyển đổi hoàn toàn hệ trục Matplotlib sang 2D Cartesian phẳng, giữ nguyên tên các hàm `setup_3d_plot` và `update_3d_plot` để đảm bảo độ tương thích 100% với tệp `main.py`.
  * Vẽ lưới nền xanh lá tối (`#002200`), 5 vòng tròn khoảng cách đồng tâm từ $2\text{m}$ đến $10\text{m}$ và các tia góc cách nhau mỗi $30^\circ$.
  * Vẽ vạch chia độ ngoài cùng kèm số hiển thị góc từ $0^\circ$ đến $350^\circ$ theo chiều kim đồng hồ.
  * Thiết lập đường quét xoay tròn $90^\circ/\text{giây}$ chạy theo thời gian thực hệ thống cùng một đuôi quét mờ dần (phosphor tail) gồm 15 lớp đa giác với độ mờ (alpha) giảm dần.
  * **Cơ chế mờ dần theo đường quét (Sweep Fade)**: 
    * Tính toán góc lệch giữa đường quét hiện tại và tọa độ cực của từng điểm mây / target.
    * Khi đường quét đi qua, điểm mây và target phát sáng rực rỡ (alpha = 1.0) rồi mờ dần theo hình tuyến tính/mũ khi đường quét đi xa (đạt mức tối thiểu alpha = 0.05).
    * Target vẽ dưới dạng chấm tròn neon rực rỡ, vòng hào quang lan tỏa (`alpha * 0.15`), nhãn văn bản biểu diễn thông số `TID`, `Height`, `Score` và vectơ chỉ hướng vận tốc.
  * **Tích hợp 4 Widget chẩn đoán châm ngòi thẩm mỹ**:
    * **SYS STATUS (Top-Left)**: Thể hiện các thanh mức chẩn đoán hệ thống và thông tin trạng thái.
    * **SIGNAL WAVE (Top-Right)**: Mô phỏng dải sóng dao động thực tế theo thời gian thực.
    * **GEOMETRIC ANCHOR (Bottom-Left)**: Khung lưới quả cầu xoay chậm mô tả hướng tọa độ.
    * **SPECTRUM (Bottom-Right)**: Hệ cột equalizer nhấp nháy động học theo tần số ngẫu nhiên.

---

## 🔬 KẾ HOẠCH BÀN GIAO & MANUAL VERIFICATION
Hệ thống đã được kiểm tra biên dịch cú pháp tĩnh thành công 100% bằng câu lệnh:
```powershell
python -m py_compile config_sender.py visualization.py
```
*Kết quả biên dịch: Hoàn thành không phát hiện bất kỳ lỗi cú pháp nào.*

Khi bạn đã sẵn sàng chạy thử, dưới đây là quy trình kiểm tra trực quan:
1. **Reset tự động**: Khởi chạy `python main.py`. Đèn trên IWR6843AOP sẽ nháy và chương trình sẽ tự động cấu hình thành công mà không cần bạn phải bấm nút Reset vật lý trên thiết bị.
2. **Giao diện quét**: Màn hình hiển thị cửa sổ Matplotlib nền đen rực rỡ với các hình ảnh chuyển động đồng bộ: đường quét quay tròn kéo theo điểm mây và các box phát sáng mờ dần đẹp mắt.
3. **Các bảng góc**: Xác nhận các khối dao động ký ở các góc hoạt động nhấp nháy trơn tru.
