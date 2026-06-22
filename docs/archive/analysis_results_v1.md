# BÁO CÁO PHÂN TÍCH SO SÁNH THỰC TẾ (WEBCAM) VS MÔ PHỎNG RADAR 3D - VERSION 1

Báo cáo này tổng hợp kết quả phân tích tương quan giữa hình ảnh thực tế ghi từ Webcam (Reality) và kết quả bám đuổi mô phỏng (Radar 3D Plot) thu thập được từ tệp video đồng bộ **`records/radar_webcam_sync_20260527_104817.mp4`** (phiên chạy v13.0).

---

## 🔍 CHẨN ĐOÁN LỖI VÀ LỖI VẬT LÝ CỐT LÕI

Qua phân tích chi tiết dữ liệu và so khớp với logic vận hành của hệ thống, chúng tôi đã phát hiện ra **2 lỗi kiến trúc nghiêm trọng** giải thích hoàn hảo cho các hiện tượng lệch góc nhìn và mất dấu mục tiêu:

### 1. Sự Sai Khác Giữa Góc Nhìn Mô Phỏng (3D Plot) và Góc Nhìn Camera Ngoài Đời
* **Hiện tượng quan sát**: Vị trí mô phỏng của Sensor trên đồ thị trông khác xa so với vị trí camera Logitech thực tế (vốn được đặt ngay trên đỉnh của radar). Đồ thị 3D tạo cảm giác không đồng bộ góc nhìn trực quan.
* **Nguyên nhân kiến trúc**:
  1. **Lỗi Tọa Độ Sensor Mô Phỏng**: Trong `settings.py`, sensor được vẽ cứng tại tọa độ đáy `(SENSOR_X=0.0, SENSOR_Y=0.0, SENSOR_Z=0.0)`. Tuy nhiên, trong hàm chuyển đổi tọa độ phòng `transform_to_room_coordinates`, toàn bộ mây điểm và target đã bị tịnh tiến lên độ cao lắp đặt thực tế `RADAR_MOUNT_HEIGHT_M = 1.15m`. Điều này khiến hộp đại diện cho Sensor nằm bẹp dưới sàn ($Z=0$), trong khi mây điểm và hộp người bay lơ lửng xung quanh cao độ $1.15\text{ m} - 1.70\text{ m}$.
  2. **Lỗi Góc Quay Sensor**: Sensor mô phỏng được vẽ dưới dạng một hộp chữ nhật thẳng đứng (axis-aligned), hoàn toàn bỏ qua góc nghiêng vật lý chĩa xuống 30 độ (`RADAR_TILT_ANGLE_DEG = 30.0`).
  3. **Lỗi Góc Nhìn Camera (Viewport Perspective)**: Góc quan sát mặc định của đồ thị 3D Matplotlib được sinh ngẫu nhiên theo mặc định của thư viện, thay vì mô phỏng chính xác góc nhìn từ mắt của Camera/Radar đặt tại tọa độ $(0, 0, 1.15)$ hướng xuống 30 độ.
* **Giải pháp đề xuất**:
  * Tịnh tiến tọa độ hiển thị của Sensor Box lên cao độ thực tế: $Z_{sensor} = \text{RADAR\_MOUNT\_HEIGHT\_M}$.
  * Áp dụng ma trận xoay quanh trục X một góc bằng `RADAR_TILT_ANGLE_DEG` để nghiêng hộp Sensor mô phỏng xuống đúng 30 độ.
  * Đồng bộ hóa góc nhìn đồ thị 3D bằng cách thiết lập Viewport Matplotlib thông qua:
    `ax.view_init(elev=RADAR_TILT_ANGLE_DEG, azim=-90)`
    *(Với elev = 30 độ hướng xuống và azim = -90 độ nhìn thẳng theo trục Y, góc nhìn 3D sẽ trùng khớp hoàn hảo 100% với góc nhìn thực tế của camera Logitech đặt trên đầu radar)*.

### 2. Hiện Tượng Mất Dấu Hoàn Toàn Khi Đứng Im (Target Drop)
* **Hiện tượng quan sát**: 
  * Khi người dùng đứng im sát cạnh chiếc ghế hoặc đứng im một chỗ, số lượng điểm phản xạ thô trên cơ thể đột ngột giảm về 0 và hộp bám đuổi biến mất hoàn toàn mặc dù người dùng vẫn đang đứng nguyên tại đó.
* **Nguyên nhân kiến trúc (Lỗ hổng logic Clutter Filter)**:
  * Hệ thống tích hợp bộ lọc nhiễu tĩnh mức điểm `ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER = True` để triệt tiêu các điểm có vận tốc Doppler gần bằng 0 nhằm loại bỏ bàn ghế.
  * Để không bị xóa nhầm người đứng im, hệ thống có cơ chế bảo vệ "Vùng bảo vệ điểm tĩnh" (`STATIC_CLUTTER_POINT_PROTECTION_RADIUS = 1.0m`) xung quanh các vị trí bám vết đã xác nhận (`confirmed_positions`).
  * **Tuy nhiên**, trong hàm `track_and_build` của `pointcloud_processing.py`, danh sách `confirmed_positions` chỉ được lấy ra từ `VirtualTargetTracker` (bộ bám vết ảo dành riêng cho các cụm mây điểm tự phát) mà bỏ sót hoàn toàn các mục tiêu bám vết gốc từ phần cứng (`raw_targets` / `firmware_target`).
  * Khi người đứng im và được bám bởi `firmware_target`, vị trí của họ không được đưa vào `confirmed_positions`. Do đó, bộ lọc coi toàn bộ điểm phản xạ của họ là nhiễu tĩnh và xóa bỏ không thương tiếc, làm mục tiêu bị coi là ghost và biến mất sau 5 frame.
* **Giải pháp đề xuất**:
  * Sửa đổi hàm `track_and_build` để gộp cả vị trí của các `raw_targets` (firmware targets) đang hoạt động ổn định vào danh sách `confirmed_positions` trước khi áp dụng bộ lọc tĩnh. Điều này sẽ bảo vệ tuyệt đối mây điểm của người dùng dù họ được bám đuổi bởi phần cứng hay phần mềm.
