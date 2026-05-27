# BÁO CÁO PHÂN TÍCH SO SÁNH THỰC TẾ (WEBCAM) VS MÔ PHỎNG RADAR 3D - VERSION 2 (CHẨN ĐOÁN LỖI v14.0)

Báo cáo này tổng hợp kết quả phân tích tương quan và chẩn đoán lỗi từ phiên chạy **Version 14.0** (tệp record **`records/radar_webcam_sync_20260527_144610.mp4`** với 2.585 frames). Mặc dù Version 14.0 đã giải quyết triệt để lỗi mất dấu khi đứng im, hệ thống vẫn tồn tại 2 hạn chế lớn về mặt trải nghiệm người dùng cần được tối ưu hóa.

---

## 🔍 CHẨN ĐOÁN LỖI PHÁT SINH TRONG PHIÊN RECORD VÀ LÝ DO VẬT LÝ

### 1. Lỗi Lưu Hộp Bounding Box Dù Không Có Người (Ghost Box Retention)
* **Hiện tượng quan sát**: 
  * Khi người dùng đã hoàn toàn rời khỏi phòng hoặc di chuyển sang khu vực khác, trên màn hình mô phỏng 3D vẫn xuất hiện và lưu lại một hộp bám đuổi (`Human Box`) tĩnh tại các tọa độ cố định (ví dụ cạnh bàn, ghế tựa văn phòng).
  * Trong tệp log, hệ thống ghi nhận một cụm điểm ảo ổn định:
    `Cluster 0 | points=17 | score=84.0 | center=(0.59, 1.10, 1.78) m`
    Cụm điểm này liên tục trả về đầy đủ điểm hỗ trợ và đạt điểm số tin cậy rất cao (84.0).
* **Nguyên nhân kiến trúc (Lỗ hổng lọc tĩnh vật cấp mục tiêu)**:
  * Khi người dùng rời đi, các vật thể tĩnh (như chiếc ghế văn phòng kim loại hoặc góc bàn gỗ) vẫn phản xạ sóng radar và tạo ra các cụm mây điểm thưa thớt nhưng cực kỳ ổn định.
  * Bộ lọc nhiễu tĩnh cấp điểm (`ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER`) chỉ lọc các điểm có Doppler bằng 0 khi *không* có target bám đuổi. Tuy nhiên, nếu một cụm điểm tĩnh đủ lớn vượt qua ngưỡng DBSCAN và tạo ra một virtual target, hệ thống sẽ coi các điểm xung quanh nó là "được bảo vệ" hoặc bản thân mục tiêu ảo liên tục tự sinh điểm hỗ trợ.
  * **Đặc biệt**: Hệ thống có cấu hình bộ lọc tĩnh vật cấp mục tiêu `ENABLE_STATIC_CLUTTER_FILTER = True` trong `settings.py`, nhưng **bộ lọc này chưa từng được triển khai trong mã nguồn thực tế** (`pointcloud_processing.py` và `filters.py`). Do đó, không có cơ chế nào tính toán độ lệch chuẩn dịch chuyển của mục tiêu ảo để ẩn nó đi khi nó đứng im tuyệt đối trong thời gian dài.
* **Giải pháp đề xuất**:
  * Triển khai bộ lọc tĩnh vật cấp mục tiêu (`ENABLE_STATIC_CLUTTER_FILTER`) trong `VirtualTargetTracker`.
  * Tích lũy lịch sử vị trí của các virtual tracks trong vòng `STATIC_CLUTTER_MIN_FRAMES = 15` frames.
  * Tính độ lệch chuẩn dịch chuyển XY ($\sigma_{xy} = \sqrt{\sigma_x^2 + \sigma_y^2}$). Nếu $\sigma_{xy} \le \text{STATIC\_CLUTTER\_MAX\_STD} = 0.05\text{ m}$ (đặc trưng của đồ vật đứng im tuyệt đối, không có rung lắc sinh học của cơ thể người), ta đánh dấu và ẩn hộp bám đuổi ảo này đi.

### 2. Chuyển Động Hộp Bám Đuổi Chưa Thực Sự Mượt Mà (Tracking Motion Lag)
* **Hiện tượng quan sát**:
  * Khi người dùng bắt đầu bước đi đột ngột hoặc di chuyển nhanh, hộp Bounding Box tạo cảm giác bị "lết" hoặc giật cục chậm sau cơ thể khoảng vài trăm miligiây trước khi tăng tốc bám kịp.
* **Nguyên nhân kiến trúc (Trễ bộ lọc thích nghi động)**:
  * Trong `filters.py`, hệ thống sử dụng bộ lọc làm mịn động học thích nghi (`ENABLE_DYNAMIC_SMOOTHING = True`), trong đó hệ số làm mịn `alpha` phụ thuộc hoàn toàn vào vận tốc tức thời của mục tiêu (`self.target_speed(target)`):
    $$\alpha = \alpha_{min} + (\alpha_{max} - \alpha_{min}) \times \min\left(1.0, \frac{\text{speed}}{\text{v\_scale}}\right)$$
  * Tuy nhiên, giá trị vận tốc `speed` được tính toán từ bộ lọc Kalman hoặc do radar trả về thường có độ trễ phản hồi tự nhiên (chậm hơn so với dịch chuyển tọa độ thực tế từ 3 đến 5 frame).
  * Khi người dùng đột ngột di chuyển, vận tốc tính toán vẫn ở mức thấp, khiến hệ số `alpha` bị giữ ở mức cực nhỏ ($\alpha_{min} = 0.15$), gây ra hiện tượng Heavy Smoothing làm hộp bám đuổi bị lết chậm.
* **Giải pháp đề xuất**:
  * Nâng cấp thuật toán tính toán vận tốc thích nghi trong `smooth_target`: Ngoài vận tốc Doppler/Kalman, ta tính thêm **vận tốc dịch chuyển thực tế tức thời** từ khoảng cách giữa vị trí hiện tại và vị trí đã làm mịn trước đó (`displacement_speed = jump_distance / dt`, với $dt \approx 0.05\text{ s}$).
  * Sử dụng vận tốc hiệu dụng lớn nhất: `effective_speed = max(doppler_speed, displacement_speed)`.
  * *Kết quả*: Ngay khi người dùng nhích chân di chuyển, khoảng cách dịch chuyển `jump_distance` tăng lên lập tức, đẩy `alpha` lên mức tối đa ($\alpha_{max} = 0.82$) ngay tại frame đầu tiên, triệt tiêu hoàn toàn độ trễ bám đuổi mà vẫn giữ được độ tĩnh tuyệt đối khi đứng im.
