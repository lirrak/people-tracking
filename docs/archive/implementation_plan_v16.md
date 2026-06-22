# KẾ HOẠCH TRIỂN KHAI v16.0 - ĐỒNG BỘ TOÀN DIỆN VẬT LÝ VÀ LÀM MỊN BÁM VẾT CAO CẤP

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 16.0** để giải quyết triệt để sự sai lệch vị trí camera-radar (lỗi toán học ma trận quay), sửa lỗi lưu hộp ma của các mục tiêu phần cứng, và tối ưu hóa chuyển động bám vết trơn tru bằng cách làm mịn hệ số lọc alpha.

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ PHƯƠNG ÁN NÂNG CẤP

### 1. Sửa lỗi sai dấu Ma trận quay (`pointcloud_processing.py`)
* **Vấn đề**: Các hàm chuyển đổi tọa độ hiện tại đang xoay ngược dấu góc nghiêng $\theta$ (giống như chĩa radar lên trời 30 độ thay vì chĩa xuống đất 30 độ). Điều này khiến người đi ra xa bị tính là đang bay lên cao và sai số cự ly lớn.
* **Giải pháp**: Đảo ngược dấu ma trận xoay quanh trục X cho đúng hướng Pitch DOWN ($-\theta$):
  $$\text{posY}_{room} = y \times \cos(\theta) + z \times \sin(\theta)$$
  $$\text{posZ}_{room} = -y \times \sin(\theta) + z \times \cos(\theta) + h$$

### 2. Triển khai Lọc Tĩnh Vật Toàn Diện (`filters.py` & `pointcloud_processing.py`)
* **Vấn đề**: Bộ lọc tĩnh vật $\sigma_{xy} \le 0.05\text{ m}$ mới chỉ được áp dụng cho *virtual targets*, bỏ sót hoàn toàn các *firmware targets* từ phần cứng, tạo ra các hộp ma bàn ghế.
* **Giải pháp**:
  * Thu hồi logic lọc tĩnh vật cũ trong `pointcloud_processing.py` để trả lại sự gọn nhẹ cho tracker.
  * Di chuyển toàn bộ logic lưu lịch sử vị trí và bộ lọc tĩnh vật $\sigma_{xy} \le 0.05\text{ m}$ lên bộ lọc chung cuối cùng **`GhostTargetFilter`** trong `filters.py`. Điều này đảm bảo triệt tiêu hộp ma 100% cho mọi nguồn dữ liệu (cả phần cứng và phần mềm).

### 3. Làm mịn hệ số lọc thích nghi (`filters.py`)
* **Vấn đề**: Hệ số làm mịn thích nghi `alpha` thay đổi đột ngột giữa `0.15` và `0.82` tạo ra các chuyển động dạng bước giật cục nhẹ khi tăng tốc.
* **Giải pháp**: Áp dụng bộ lọc thông thấp (EMA) để làm mịn sự biến thiên của hệ số `alpha` qua các frame:
  $$\alpha_{smoothed} = 0.80 \times \alpha_{previous} + 0.20 \times \alpha_{current}$$

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* Đảo ngược dấu ma trận quay trong `transform_to_room_coordinates` và `transform_target_to_room_coordinates`:
* Thu hồi logic lọc tĩnh vật cũ của Version 15.0 để dọn dẹp mã nguồn.

### 📄 [MODIFY] [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)
* Khởi tạo `self.history_positions = {}` và `self.last_alpha = {}` trong `GhostTargetFilter.__init__`.
* Cập nhật `GhostTargetFilter.update` để tích lũy vị trí, tính $\sigma_{xy}$ lọc tĩnh vật toàn diện cho mọi mục tiêu.
* Cập nhật `GhostTargetFilter.smooth_target` để làm mịn thích nghi `alpha` qua các frame.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử đồng bộ tuyệt đối tọa độ Camera - Radar
* Người dùng di chuyển ra xa cảm biến ($> 3.0\text{ m}$).
* **Tiêu chuẩn vượt qua**: Hộp bám đuổi 3D bám sát cơ thể dọc mặt sàn ($Z \approx 0.15\text{ m} - 1.70\text{ m}$), hoàn toàn không bị bay lên trời, trùng khớp phối cảnh 100% với Webcam Logitech đặt trên đỉnh radar.

### 2. Kiểm thử triệt tiêu hộp ma bàn ghế phần cứng
* Rời khỏi phòng để chỉ còn bàn ghế tĩnh.
* **Tiêu chuẩn vượt qua**: Không có bất kỳ hộp bám vết ma nào xuất hiện trên màn hình đồ họa (cả phần cứng và phần mềm đều bị lọc sạch).

### 3. Kiểm thử độ mượt bám đuổi
* Bước nhanh, chạy chéo, chuyển động đột ngột.
* **Tiêu chuẩn vượt qua**: Hộp di chuyển mềm mại, bám vết trơn tru không giật cục.
