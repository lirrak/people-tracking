# KẾ HOẠCH TRIỂN KHAI v26.0 - ĐỒNG BỘ KHOẢNG CÁCH TUYỆT ĐỐI & HIỆU CHUẨN TỌA ĐỘ RADAR

Tài liệu này đề xuất phương án cải tiến hệ thống lên **Version 26.0** nhằm khắc phục triệt để lỗi sai lệch khoảng cách (cự ly) và chiều cao của người dùng hiển thị trên giao diện so với thực tế.

---

## 🔍 NGUYÊN NHÂN SAI LỆCH KHOẢNG CÁCH CHẠY THỰC TẾ

Qua phân tích mã nguồn và so sánh hệ tọa độ, chúng ta phát hiện một lỗi đồng bộ tọa độ nghiêm trọng giữa radar chip và xử lý Python:
1. **Lệnh nạp cấu hình cứng**: Trong tệp cấu hình `3d_people_tracking.cfg` hiện tại, lệnh `sensorPosition 0.8 0 0` được gửi cứng lên radar chip. Điều này báo cho thuật toán bám vết trên chip (GTRACK) rằng radar đang được lắp ở độ cao $0.8\text{m}$ không nghiêng.
2. **Cộng bù chiều cao trên chip**: Vì cài đặt này, thuật toán trên chip tự động cộng thêm $+0.8\text{m}$ vào tọa độ $Z$ của các mục tiêu (`raw_targets`) trước khi truyền qua UART.
3. **Phép quay kép và méo tọa độ trong Python**: Trong Python, chúng ta lại thực hiện xoay tọa độ $30^\circ$ và dịch chiều cao $1.15\text{m}$ một lần nữa:
   * Do tọa độ $Z$ đầu vào từ radar đã bị cộng lệch $+0.8\text{m}$ từ trước, khi đi qua ma trận xoay $30^\circ$ trong hàm `transform_target_to_room_coordinates`, sai số này bị "xoay" sang cả trục khoảng cách $Y$ và trục chiều cao $Z$:
     * Sai số khoảng cách ngang $Y$ bị lệch thêm: $\Delta Y = 0.8 \sin(30^\circ) = +0.4\text{m}$ (khiến người dùng luôn bị đẩy ra xa thêm 40cm trên màn hình so với vị trí thực tế!).
     * Sai số chiều cao $Z$ bị lệch thêm: $\Delta Z = 0.8 \cos(30^\circ) = +0.69\text{m}$ (khiến chiều cao tính toán bị đẩy lên quá cao).
4. **Lọc Clutter trên chip kém hiệu quả**: Do chip hiểu sai góc nghiêng thực tế ($0^\circ$ thay vì $30^\circ$), bộ lọc tĩnh vật và lọc sàn của chip hoạt động không đúng góc chéo, dẫn đến việc bỏ sót điểm người hoặc nhận nhầm phản xạ sàn nhà.

---

## 💡 GIẢI PHÁP TRIỂN KHAI TRONG VERSION 26.0

Để giải quyết triệt để vấn đề này, chúng ta sẽ chuyển giao việc xoay tọa độ của mục tiêu cho phần cứng radar xử lý trực tiếp, đồng thời căn chỉnh đồng bộ trong Python:

### 1. Nạp động lệnh `sensorPosition` tương thích thực tế phần cứng
* **Tệp thay đổi**: [config_sender.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/config_sender.py)
* **Giải pháp**: Trong hàm `send_selected_config`, trước khi gửi các dòng lệnh cấu hình, chương trình sẽ tự động đọc `RADAR_MOUNT_HEIGHT_M` và `RADAR_TILT_ANGLE_DEG` từ `settings.py` để thay thế động dòng `sensorPosition` trong bộ đệm cấu hình thành:
  `sensorPosition <RADAR_MOUNT_HEIGHT_M> 0 <RADAR_TILT_ANGLE_DEG>`
  * *Kết quả*: Chip radar sẽ nhận biết chính xác góc lắp đặt và độ cao vật lý để tính toán tọa độ phòng chuẩn xác 100% ngay từ tầng phần cứng, tối ưu hóa bộ lọc sàn và bám vết của chip.

### 2. Triệt tiêu phép quay kép trong Python
* **Tệp thay đổi**: [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* **Giải pháp**: 
  * Điểm mây (Point Cloud) gửi từ radar dạng tọa độ cực raw nên vẫn cần được xoay trong Python qua hàm `transform_to_room_coordinates`.
  * Các mục tiêu (`raw_targets`) đã được chip xoay và dịch chuyển tọa độ hoàn hảo ở tầng phần cứng dựa trên cấu hình động mới. Do đó, trong hàm `transform_target_to_room_coordinates`, chúng ta **loại bỏ hoàn toàn phép xoay và dịch chuyển**, chỉ giữ lại phép đối xứng gương `FLIP_X_PERSPECTIVE` nếu người dùng kích hoạt.
  * *Kết quả*: Triệt tiêu hoàn toàn sai số $+0.4\text{m}$ khoảng cách và $+0.69\text{m}$ chiều cao, đồng bộ khớp 100% giữa mục tiêu và điểm mây thực tế.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### Kiểm tra cú pháp tự động
Chạy kiểm tra cú pháp Python tĩnh sau khi sửa đổi:
```powershell
python -m py_compile config_sender.py pointcloud_processing.py
```

### Xác minh thủ công
1. **Chuẩn bị**: Lắp đặt radar ở độ cao cấu hình trong `settings.py` (ví dụ $1.15\text{m}$) và chĩa nghiêng $30^\circ$.
2. **Kiểm tra cự ly**: Dùng thước dây đo khoảng cách nằm ngang từ mặt phẳng radar đến vị trí đứng im của bạn (ví dụ đứng tại vạch $2.0\text{m}$).
3. **Tiêu chuẩn vượt qua**:
   * Chấm tròn mục tiêu của bạn trên giao diện Radar HUD phải nằm chính xác tại vòng tròn cự ly $2.0\text{m}$ ($\pm 0.1\text{m}$ sai số vật lý).
   * Chiều cao hiển thị kế bên mục tiêu phải phản ánh chính xác chiều cao thật của bạn ($1.7\text{m} \pm 0.15\text{m}$).
   * Mây điểm và chấm mục tiêu phải chồng khít lên nhau, không còn độ lệch lệch tâm 40cm như trước.
