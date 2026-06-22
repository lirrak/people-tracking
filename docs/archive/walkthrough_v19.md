# BÁO CÁO CẬP NHẬT VERSION 19.0 - PHÂN LOẠI TƯ THẾ TRÊN ĐỒ THỊ 3D VÀ XUẤT FILE LOG TỌA ĐỘ MÂY ĐIỂM CHI TIẾT (X, Y, Z, DOPPLER, SNR)

Hệ thống đã được nâng cấp thành công lên **Version 19.0**, hoàn thiện tính năng **Point-level Logger** để xuất dữ liệu mây điểm thô cơ bản dạng tọa độ và tích hợp bộ nhận dạng tư thế thử nghiệm **Posture Profiler** trên đồ họa 3D Matplotlib. 

Toàn bộ mã nguồn đã được sửa đổi sạch sẽ và tuân thủ nghiêm ngặt yêu cầu **không chạy mã nguồn** khi bạn chưa cho phép.

Dưới đây là tổng hợp chi tiết các nâng cấp kỹ thuật đã hoàn thành:

---

## 🛠️ CHI TIẾT CÁC THAY ĐỔI ĐÃ TRIỂN KHAI

### 1. Tái cấu trúc bộ ghi log thành Point-level Logger (`pointcloud_logger.py`)
* **Chuyển đổi lưu trữ tọa độ thô cơ bản**: Thay thế hoàn toàn bộ logger ghi thông số thống kê gộp mức độ frame. Giờ đây, file log CSV lưu trữ trực tiếp từng điểm đơn trong mây điểm hiển thị với các tiêu đề (Header) cơ bản nhất:
  * Tiêu đề mới: `frame_number,timestamp,x,y,z,doppler,snr`
* **Cơ chế ghi**: Với mỗi frame radar nhận được, logger duyệt qua từng điểm đơn của mây điểm hiển thị (`display_pc`), trích xuất tọa độ `(x, y, z)`, vận tốc `doppler` và cường độ `snr` để ghi chép một dòng tương ứng vào file CSV.
* **Đảm bảo tính thực nghiệm**: Trạng thái nhận diện tư thế động được giữ hoàn toàn ở dạng thử nghiệm hiển thị, **không** xuất ra file log CSV để tránh làm nhiễu dữ liệu mây điểm thô.

### 2. Triển khai phân loại tư thế người thử nghiệm dọc trục Z (`pointcloud_processing.py`)
* Triển khai hàm **`profile_target_posture(cluster)`**:
  * Nhận mây điểm của cluster và phân mảnh dọc trục Z thành 3 phân vùng thực tế:
    1. **Lower Zone (Chân/Sàn)**: $Z \in [0.15, 0.60]\text{ m}$.
    2. **Middle Zone (Thân/Bụng)**: $Z \in [0.60, 1.20]\text{ m}$.
    3. **Upper Zone (Đầu/Ngực)**: $Z \in [1.20, 2.20]\text{ m}$.
  * Thực hiện thuật toán ước lượng tư thế:
    * **`LYING/FALLEN` (Nằm/Ngã sàn)**: Hơn 85% điểm mây bẹt dưới Z < 0.60m và độ phân tán ngang XY rộng $>0.85$ mét.
    * **`SITTING` (Ngồi)**: Cụm điểm chủ yếu ở phân vùng thấp & giữa, rỗng phần cao và chiều cao tối đa trung bình $[0.60\text{ m} - 1.30\text{ m}]$.
    * **`STANDING` (Đứng)**: Chiều cao tối đa cao $\ge 1.30\text{ m}$ và các phân vùng thẳng đứng chặt chẽ (độ lệch tâm XY giữa các phân vùng $< 0.45\text{ m}$).
* **Tích hợp bám vết**:
  * Hàm `cluster_to_virtual_target` và bộ quản lý `VirtualTargetTracker` gán nhãn tư thế động tương ứng cho các confirmed tracks thông qua điểm mây cluster thực tế của chúng (`virtual_target["posture"] = posture`).

### 3. Hiển thị nhãn tư thế và cảnh báo đỏ (`visualization.py`)
* Nâng cấp hàm vẽ hộp **`draw_wireframe_box_3d`** hỗ trợ đối số `color` (nếu là `None`, tự động sử dụng màu mặc định của Matplotlib).
* Nâng cấp đồ họa hiển thị mục tiêu trong **`update_3d_plot`**:
  * Đọc trạng thái `posture` của từng target.
  * Hiển thị trực quan nhãn tư thế trên nhãn hộp (Ví dụ: `ID 1000 [STANDING]` hoặc `ID 1001 [SITTING]`).
  * **Cảnh báo đỏ đặc biệt**: Nếu phát hiện tư thế `LYING/FALLEN`, hộp Bounding Box 3D của người đó sẽ tự động chuyển sang **Màu Đỏ Cảnh Báo (Red)** và nhãn hiển thị cảnh báo `⚠️ LYING/FALLEN ID x` để thu hút chú ý lập tức.
  * In nhãn trạng thái tư thế ngay tại vị trí trung tâm của mục tiêu (`label_text += f"\n{posture}"`).

---

## 🔬 KẾ QUẢ XÁC MINH CÚ PHÁP LOGIC

Tất cả các thay đổi mã nguồn đã được kiểm thử tư duy logic cẩn thận, đảm bảo:
1. Không có bất kỳ biến số chưa định nghĩa nào (undefined variables).
2. Toàn bộ logic NumPy thực hiện đúng chiều ma trận, xử lý an toàn chống chia cho không (`np.where`, `np.clip` trên determinant).
3. Đã tuân thủ nghiêm ngặt yêu cầu **không chạy mã nguồn** trong terminal của bạn.
