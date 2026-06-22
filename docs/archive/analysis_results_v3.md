# BÁO CÁO PHÂN TÍCH SO SÁNH THỰC TẾ (WEBCAM) VS MÔ PHỎNG RADAR 3D - VERSION 3 (CHẨN ĐOÁN LỖI v15.0)

Báo cáo này tổng hợp kết quả phân tích và chẩn đoán lỗi chuyên sâu từ phiên chạy **Version 15.0** (tệp record **`records/radar_webcam_sync_20260527_154033.mp4`** với 2.914 frames). Phiên bản này đánh dấu bước tiến lớn khi bộ lọc tĩnh vật hoạt động tốt trong nền, nhưng vẫn còn 3 lỗi hệ thống quan trọng làm lệch tọa độ so với camera Logitech và khiến chuyển động chưa hoàn hảo.

---

## 🔍 CHẨN ĐOÁN LỖI KIẾN TRÚC & LÝ DO VẬT LÝ CHI TIẾT

Chúng tôi đã phát hiện ra **3 lỗi kiến trúc cốt lõi** giải thích hoàn hảo cho các hiện tượng bạn đã quan sát được:

### 1. Sai lệch vị trí người trong Camera so với Radar (Lỗi sai dấu Ma trận quay)
* **Hiện tượng quan sát**: Vị trí của người trong camera ngoài đời và vị trí vẽ hộp trên đồ thị 3D Matplotlib lệch nhau rất rõ rệt về mặt phối cảnh không gian, mặc dù camera Logitech đã được đặt ngay trên đầu radar. Khi đi ra xa, người dùng có cảm giác hộp bám đuổi bị đẩy lên cao hoặc sai lệch cự ly nghiêm trọng.
* **Nguyên nhân toán học (Sai dấu góc quay Pitch)**:
  * Trong `pointcloud_processing.py`, hai hàm chuyển đổi tọa độ phòng là `transform_to_room_coordinates` và `transform_target_to_room_coordinates` đang áp dụng ma trận quay quanh trục X (góc nghiêng của radar) như sau:
    $$\text{posY}_{room} = y \times \cos(\theta) - z \times \sin(\theta)$$
    $$\text{posZ}_{room} = y \times \sin(\theta) + z \times \cos(\theta) + h$$
  * **Lỗi nghiêm trọng**: Đây là ma trận xoay một góc chéo **hướng lên (Pitch UP)** $+\theta$ (30 độ chĩa lên trần nhà). Trong khi thực tế radar được lắp đặt chĩa **hướng xuống (Pitch DOWN)** $-\theta$ (30 độ chĩa xuống sàn).
  * Do sai dấu toán học này, khi người dùng đi ra xa cảm biến (tức là $y_{radar}$ tăng), độ cao của họ $Z_{room}$ bị tính toán **tăng vọt lên trời** thay vì giảm xuống sàn:
    $$\text{posZ}_{room} = h + y_{radar} \times \sin(30^\circ)$$
    *(Ví dụ đứng cách 2m, người dùng bị tính là đang bay lơ lửng ở độ cao $1.15 + 2 \times 0.5 = 2.15\text{ m}$!)*. Điều này gây méo mó tọa độ cực lớn, sai lệch hoàn toàn so với hình ảnh thực tế từ camera Logitech đặt trên đầu radar chĩa xuống.
* **Giải pháp sửa đổi**:
  * Sửa lại ma trận xoay đúng hướng Pitch DOWN ($-\theta$) cho cả mây điểm và target:
    $$\text{posY}_{room} = y \times \cos(\theta) + z \times \sin(\theta)$$
    $$\text{posZ}_{room} = -y \times \sin(\theta) + z \times \cos(\theta) + h$$
    *(Khi đứng cách 2m, độ cao của điểm phản xạ dọc boresight sẽ giảm chuẩn xác về: $1.15 - 2 \times 0.5 = 0.15\text{ m}$ sát mặt sàn)*.

### 2. Vẫn xảy ra lỗi lưu Bounding Box khi không có người (Ghost Box của Target phần cứng)
* **Hiện tượng quan sát**: Hộp ma tĩnh vật vẫn đôi lúc xuất hiện cố định tại bàn/ghế khi không có người trong phòng.
* **Nguyên nhân kiến trúc (Bỏ sót lọc tĩnh vật ở target phần cứng)**:
  * Tại Version 15.0, chúng ta đã triển khai bộ lọc tĩnh vật bằng cách tính độ lệch chuẩn vị trí đo đạc $\sigma_{xy} \le 0.05\text{ m}$ trên 15 frame.
  * **Tuy nhiên**, bộ lọc này mới chỉ được tích hợp vào `VirtualTargetTracker` để lọc các virtual targets (do phần mềm tự tạo). Nó **bỏ sót hoàn toàn** các targets được bám vết bởi chip phần cứng (`raw_targets` / `firmware_target`).
  * Khi chip radar khóa cứng một chiếc ghế (do phản xạ kim loại mạnh), nó báo về một firmware target. Target này liên tục có support_points cao và missing_count = 0, hoàn toàn bypass qua bộ lọc của tracker phần mềm và hiển thị vĩnh viễn trên màn hình thành hộp ma.
* **Giải pháp sửa đổi**:
  * Di chuyển toàn bộ lịch sử vị trí và bộ lọc tĩnh vật $\sigma_{xy} \le 0.05\text{ m}$ lên **`GhostTargetFilter`** trong `filters.py`. Vì đây là bộ lọc chung cuối cùng trước khi vẽ hộp, nó xử lý cả virtual targets và firmware targets, đảm bảo triệt tiêu hộp ma 100% cho mọi nguồn dữ liệu.

### 3. Chuyển động bám đuổi (Tracking) chưa thực sự mượt mà (Sudden Step-Change Jitter)
* **Hiện tượng quan sát**: Hộp bám vết đôi lúc bị giật cục hoặc tăng tốc đột ngột khi người dùng di chuyển nhanh.
* **Nguyên nhân kiến trúc (Nhảy bước hệ số alpha)**:
  * Hệ số làm mịn thích nghi động `alpha` thay đổi tức thời từ `0.15` lên `0.82` khi `effective_speed` thay đổi nhanh.
  * Việc thay đổi đột ngột hệ số lọc giữa các khung hình kề nhau tạo ra sự biến thiên vị trí dạng bước (step change), khiến mắt người nhìn thấy hộp bị khựng hoặc giật nhẹ.
* **Giải pháp sửa đổi**:
  * Làm mịn chính sự biến thiên của hệ số `alpha` qua các frame bằng bộ lọc thông thấp (EMA):
    $$\alpha_{smoothed} = 0.80 \times \alpha_{previous} + 0.20 \times \alpha_{current}$$
  * Điều này giúp hệ số alpha tăng tốc và giảm tốc mềm mại, mang lại chuyển động bám đuổi cực kỳ mượt mà, tự nhiên và trơn tru.

---

## 💡 ĐỀ XUẤT CẤU TRÚC KẾ HOẠCH TRIỂN KHAI CHO VERSION 16.0

Chúng tôi đề xuất triển khai các nâng cấp toán học và bộ lọc này trong Version 16.0 để đạt độ chính xác không gian tuyệt đối:

### 1. Sửa đổi toán học ma trận quay (`pointcloud_processing.py`)
* Đảo ngược dấu ma trận quay trong `transform_to_room_coordinates` và `transform_target_to_room_coordinates` theo đúng góc Pitch DOWN ($-\theta$).

### 2. Tích hợp Lọc Tĩnh Vật Toàn Diện (`filters.py`)
* Triển khai tích lũy lịch sử vị trí và bộ lọc $\sigma_{xy} \le 0.05\text{ m}$ cho toàn bộ mục tiêu (firmware + virtual) ngay trong `GhostTargetFilter`.

### 3. Làm mịn hệ số lọc thích nghi (`filters.py`)
* Sử dụng EMA để làm mịn hệ số `alpha` của từng target qua các khung hình.

---
*Báo cáo này đã sẵn sàng để trình duyệt. Xin vui lòng cho ý kiến chỉ đạo trước khi chúng tôi tiến hành cập nhật Kế hoạch triển khai Version 16.0.*
