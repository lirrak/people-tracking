# KẾ HOẠCH TRIỂN KHAI v19.0 - PHÂN LOẠI TƯ THẾ DỌC TRỤC Z (ĐỨNG, NGỒI, NẰM) VÀ XUẤT LOG MÂY ĐIỂM DẠNG TOẠ ĐỘ (X, Y, Z, DOPPLER, SNR)

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 19.0** để tích hợp tính năng **Phân mảnh mây điểm và Phân loại tư thế cơ thể dọc trục Z (Posture Recognition)** trên giao diện đồ họa Matplotlib, đồng thời tái cấu trúc bộ ghi log CSV thành dạng **Point-level Logger** để lưu trữ trực tiếp từng điểm mây với tiêu đề tọa độ cơ bản (X, Y, Z, Doppler, SNR).

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ PHƯƠNG ÁN NÂNG CẤP

### 1. Xuất log mây điểm dạng tọa độ điểm chi tiết (`pointcloud_logger.py`)
* **Mục tiêu**: Tái cấu trúc bộ ghi log từ ghi thông số thống kê gộp mức độ frame sang ghi chép chi tiết tọa độ từng điểm mây đơn lẻ (`x`, `y`, `z`, `doppler`, `snr`) để phục vụ nghiên cứu và xử lý ngoại tuyến (offline).
* **Giải pháp**: 
  * Cài đặt định dạng tiêu đề (Headers) mới:
    `frame_number,timestamp,x,y,z,doppler,snr`
  * Với mỗi frame radar nhận được, duyệt qua toàn bộ các điểm thuộc mây điểm hiển thị (`display_pc`) và ghi một dòng tương ứng cho mỗi điểm mây đơn lẻ.
  * Các thông số thử nghiệm tư thế (Đứng, Ngồi, Nằm) sẽ **không** ghi vào file log để giữ dữ liệu thô sạch sẽ, không bị trộn lẫn thông tin thử nghiệm.

### 2. Phân loại tư thế dọc trục Z của con người (Thử nghiệm hiển thị đồ họa Matplotlib)
* **Mục tiêu**: Giải quyết vấn đề mây điểm chỉ tập trung thành một cụm thô, giúp phân biệt được khi nào người đang đứng thẳng (Vertical distribution), ngồi (Medium spread) hay nằm/ngã sàn (Horizontal distribution sát mặt đất).
* **Giải pháp**: Triển khai cơ chế **Phân mảnh chiều cao Z (Z-Axis Height Slicing)** và bộ phân tích tư thế **Posture Profiler** (Chỉ hiển thị thử nghiệm trên đồ thị 3D Matplotlib, không xuất ra file log):
  * **Z-Axis Height Slicing**: Phân mảnh cụm điểm của mỗi người thành 3 phân vùng độ cao thực tế dọc trục Z:
    1. **Lower Zone (Phân vùng Thấp - Chân/Sàn)**: $Z \in [0.15, 0.60]\text{ m}$.
    2. **Middle Zone (Phân vùng Giữa - Thân/Bụng)**: $Z \in [0.60, 1.20]\text{ m}$.
    3. **Upper Zone (Phân vùng Cao - Đầu/Ngực)**: $Z \in [1.20, 2.20]\text{ m}$.
  * **Posture Profiler Algorithm**: Tính toán số lượng điểm, độ cao cực đại ($Z_{max}$), và độ rộng phân tán ngang của các phân vùng để ước lượng tư thế:
    * **STANDING (Đứng)**: Điểm mây trải đều trên cả 3 phân vùng, độ cao $Z_{max} \ge 1.30\text{ m}$, và tâm của các phân vùng thẳng hàng đứng rất chặt chẽ (độ lệch tâm XY $< 0.30\text{ m}$).
    * **SITTING (Ngồi)**: Điểm mây tập trung chủ yếu ở phân vùng Thấp và Giữa, rất ít hoặc không có điểm ở phân vùng Cao. Chiều cao tối đa ở mức trung bình ($0.65\text{ m} \le Z_{max} < 1.30\text{ m}$).
    * **LYING/FALLEN (Nằm/Ngã sàn)**: Điểm mây bẹt tập trung gần như 100% ở phân vùng Thấp ($Z < 0.60\text{ m}$), đồng thời phân bố rộng ra theo phương ngang (X hoặc Y spread $> 0.85\text{ m}$).
  * **Hiển thị giao diện**: Bổ sung nhãn trạng thái tư thế lên hộp Bounding Box 3D của Matplotlib (Ví dụ: `ID 1000 | STANDING` hoặc `ID 1001 | LYING/FALLEN` màu đỏ cảnh báo).

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [pointcloud_logger.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_logger.py)
* **Khởi tạo Header**: Thiết lập danh sách cột đơn giản, cơ bản của mây điểm:
  `frame_number,timestamp,x,y,z,doppler,snr`
* **Ghi dữ liệu**: Hàm `log_frame` nhận mây điểm hiển thị (`display_pc`), duyệt qua từng điểm đơn lẻ và ghi dòng dữ liệu tọa độ tương ứng.

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* Triển khai hàm phân tích tư thế **`profile_target_posture(cluster_points)`**:
  * Nhận mây điểm của cluster và phân tách thành 3 mảng con dựa trên tọa độ Z.
  * Đánh giá mật độ, chiều cao tối đa, và độ rộng phân tán ngang để trả về nhãn tư thế phù hợp (`STANDING`, `SITTING`, `LYING/FALLEN`).
* Cập nhật hàm **`cluster_to_virtual_target`** và lớp **`VirtualTargetTracker`**:
  * Tích hợp nhãn tư thế thử nghiệm vào dictionary của target ảo (`virtual_target["posture"] = posture`).

### 📄 [MODIFY] [visualization.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/visualization.py)
* Cập nhật hàm **`update_3d_plot`**:
  * Trích xuất thuộc tính `posture` của mục tiêu để in trực tiếp lên nhãn hiển thị 3D trên màn hình.
  * Tự động chuyển đổi màu sắc của hộp bám vết sang **Màu Đỏ Cảnh Báo (Red)** nếu phát hiện tư thế `LYING/FALLEN` (Nằm/Ngã) để thu hút chú ý tức thời!

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Xác minh dữ liệu Log CSV (CSV Log Verification)
* Sau khi chạy chương trình, mở file log mới sinh ra trong thư mục `log/`.
* **Tiêu chuẩn vượt qua**:
  * Dòng tiêu đề đầu tiên chứa các cột tọa độ cơ bản: `frame_number,timestamp,x,y,z,doppler,snr`.
  * Các dòng dữ liệu ghi lại đúng tọa độ thực tế của từng điểm đơn lẻ trong mây điểm hiển thị.

### 2. Kiểm thử phân loại tư thế thực tế (Posture Classifier Verification)
* Chạy chương trình, người thử nghiệm thực hiện tuần tự các tư thế: Đứng thẳng di chuyển $\rightarrow$ Ngồi xuống ghế $\rightarrow$ Nằm/ngã ra sàn.
* **Tiêu chuẩn vượt qua**:
  * Trên giao diện Matplotlib, nhãn Bounding Box đổi từ `[ID x | STANDING]` $\rightarrow$ `[ID x | SITTING]` $\rightarrow$ `[ID x | LYING/FALLEN]` chính xác.
  * Hộp bounding box chuyển sang màu đỏ nổi bật ngay lập tức khi người dùng nằm sàn.
