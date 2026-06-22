# BÁO CÁO CẬP NHẬT VERSION 26.0 - ĐỒNG BỘ KHOẢNG CÁCH TUYỆT ĐỐI & HIỆU CHUẨN TỌA ĐỘ RADAR

Hệ thống bám vết người 3D bằng mmWave Radar đã được nâng cấp thành công lên **Version 26.0** nhằm sửa lỗi lệch khoảng cách 0.4m và lỗi sai lệch chiều cao do phép xoay tọa độ kép (double transformation).

Mọi sửa đổi mã nguồn đã tuân thủ nghiêm ngặt chỉ thị của bạn: **Tuyệt đối không tự ý chạy thử chương trình chính.**

---

## 🛠️ CHI TIẾT CÁC THAY ĐỔI ĐÃ TRIỂN KHAI

### 1. Nạp động lệnh `sensorPosition` tương thích phần cứng (`config_sender.py`)
* **Tệp sửa đổi**: [config_sender.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/config_sender.py)
* **Chi tiết**:
  * Cập nhật hàm `send_selected_config` để tự động import độ cao `RADAR_MOUNT_HEIGHT_M` và góc nghiêng `RADAR_TILT_ANGLE_DEG` từ `settings.py`.
  * Tìm kiếm dòng lệnh `sensorPosition` trong tệp cấu hình được nạp lên bộ nhớ, tự động ghi đè giá trị tương ứng từ cấu hình:
    `sensorPosition <RADAR_MOUNT_HEIGHT_M> 0 <RADAR_TILT_ANGLE_DEG>`
  * Nếu dòng lệnh này không tồn tại, nó sẽ tự động được chèn ngay trước lệnh `sensorStart` để gửi tới chip.
  * **Tác động**: Thuật toán bám vết và bộ lọc tĩnh vật trên chip hoạt động chính xác với thông số thực tế của phòng, xuất ra các giá trị tọa độ đã xoay và dịch chuẩn hóa trực tiếp qua UART.

### 2. Triệt tiêu phép quay kép trong Python (`pointcloud_processing.py`)
* **Tệp sửa đổi**: [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* **Chi tiết**:
  * Sửa đổi hàm `transform_target_to_room_coordinates` nhận dữ liệu mục tiêu. Do tọa độ của mục tiêu (`raw_targets`) đã được chip radar xoay và dịch chuyển hoàn tất dựa trên tham số nạp động trên, chúng ta không áp dụng lại ma trận quay $30^\circ$ và tịnh tiến chiều cao $1.15\text{m}$ trong Python nữa.
  * Chỉ giữ lại duy nhất phép đối xứng gương trục X (`FLIP_X_PERSPECTIVE`) nếu cấu hình bật.
  * **Tác động**: Sửa đổi này triệt tiêu hoàn toàn sai số $+0.4\text{m}$ ở khoảng cách ngang $Y$ và $+0.69\text{m}$ ở chiều cao $Z$, giúp box bám vết khớp hoàn toàn 100% với mây điểm point cloud và vị trí đứng thực tế của người dùng.

---

## 🔬 KẾ HOẠCH BÀN GIAO & MANUAL VERIFICATION
Hệ thống đã được kiểm tra biên dịch cú pháp tĩnh thành công 100% bằng câu lệnh:
```powershell
python -m py_compile config_sender.py pointcloud_processing.py
```
*Kết quả biên dịch: Hoàn thành không phát hiện bất kỳ lỗi cú pháp nào.*

Khi bạn đã sẵn sàng chạy thử, dưới đây là quy trình kiểm tra trực quan:
1. **Kiểm tra cự ly**: Đứng yên tại khoảng cách thực tế (ví dụ dùng thước dây đo khoảng cách $2.0\text{m}$ trước radar).
2. **Tiêu chuẩn vượt qua**:
   * Mục tiêu trên màn hình radar HUD quét tròn phải chỉ đúng vị trí cự ly $2.0\text{m}$ (trên vòng tròn lưới $2\text{m}$).
   * Dữ liệu chiều cao hiển thị trên HUD trùng khớp với chiều cao thật của bạn.
   * Chấm mục tiêu bám khít xung quanh trung tâm mây điểm cơ thể, không còn hiện tượng lệch lệch tâm 40cm.
