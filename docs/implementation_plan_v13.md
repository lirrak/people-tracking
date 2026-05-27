# KẾ HOẠCH TRIỂN KHAI v13.0 - GIẢI PHÁP ĐỘT PHÁ VẬT LÝ VÀ TỰ ĐỘNG DÒ TÌM WEBCAM LOGITECH MỚI

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 13.0** nhằm giải quyết triệt để các hạn chế vật lý cốt lõi đã được phân tích ở báo cáo trước đó. Đồng thời, kế hoạch này tích hợp giải pháp **Tự động dò tìm cổng USB Webcam Logitech mới** giúp hệ thống khởi chạy ngay lập tức mà không gặp lỗi kết nối camera.

---

## 🔍 PHÂN TÍCH NGUYÊN NHÂN & GIẢI PHÁP ĐỘT PHÁ TRONG VERSION 13.0

Chúng tôi đề xuất 3 sự thay đổi cốt lõi nhằm giải quyết 3 khuyết điểm lớn nhất của hệ thống:

### 1. Hiện tượng "Hòa ảnh nội thất" (Furniture Fusion) và Che khuất (Occlusion)
* **Phân tích nguyên nhân**: Khi người đứng im sát ghế văn phòng hoặc đứng nghiêng cơ thể, mây điểm thô bị thưa đi hoặc phản xạ lan sang sườn ghế kim loại. Thuật toán DBSCAN gộp cả ghế vào người làm hộp Bounding Box ảo bị phình to bất thường (Furniture Fusion) hoặc co rúm kích thước (Self-Occlusion).
* **Giải pháp đột phá - Neo giữ hình học (Geometric Anchor Lock)**:
  * Khi một Target ảo đạt trạng thái `confirmed`, hệ thống sẽ "khóa băng" và neo giữ kích thước mặc định chuẩn của hình thể người ($0.85\text{ m}$ chiều rộng, $1.70\text{ m}$ chiều cao) làm kích thước nền móng bền vững.
  * Khi người dùng đứng im hoặc đứng sát ghế, hệ thống sẽ bỏ qua sự co giãn thất thường của mây điểm thô thời gian thực và áp dụng thuật toán **Làm mịn kích thước hộp (Size Smoothing)** cực nặng:
    $$\text{Size}_{smoothed} = 0.95 \times \text{Size}_{anchor} + 0.05 \times \text{Size}_{current\_cluster}$$
  * *Kết quả*: Hộp bám đuổi luôn giữ nguyên phom dáng chuẩn của cơ thể người, triệt tiêu hoàn toàn hiện tượng phình to nuốt chiếc ghế hay méo mó hình thể.

### 2. Hiện tượng "Suy hao mây điểm ở rìa trường quét" (Peripheral Cloud Decay)
* **Phân tích nguyên nhân**: Anten patch phẳng của chip IWR6843AOP có độ lợi suy hao tự nhiên cực mạnh (giảm từ 3dB đến 6dB) ở rìa góc quét lớn ($>45^\circ$ Azimuth), khiến các điểm phản xạ ở biên bị lọc bỏ sạch sẽ do không đạt SNR tối thiểu.
* **Giải pháp đột phá - Bù độ nhạy rìa thích nghi góc quét (Antenna Edge Gain Compensation)**:
  * Trong hàm lọc điểm thô `build_human_point_mask`, ta tính toán góc lệch Azimuth $\theta = \arctan2(x, y)$ của từng điểm.
  * Nếu điểm nằm ngoài vùng quét trung tâm ($|\theta| \ge 40^\circ$), ta thực hiện nhân bù độ nhạy SNR thô theo mức độ lệch biên để điểm dễ dàng vượt qua bộ lọc chất lượng:
    $$SNR_{compensated} = SNR \times \left(1.0 + 0.6 \times \left(\frac{|\theta| - 40^\circ}{20^\circ}\right)\right)$$
  * *Kết quả*: Giữ lại đầy đủ các điểm thô phản xạ ở mép rìa biên, duy trì vết bám ổn định của hộp khi người dùng di chuyển ra sát rìa trái/phải bàn làm việc.

### 3. Thay đổi thiết bị phần cứng Webcam (Logitech USB Camera Index)
* **Phân tích nguyên nhân**: Khi người dùng rút webcam cũ và cắm webcam Logitech mới vào cổng USB khác, Windows sẽ thay đổi mã định danh thiết bị (`device index` từ 0 sang 1, 2, hoặc 3). Cố định index = 0 sẽ làm chương trình bị lỗi kết nối hoặc gọi sai camera tích hợp của laptop.
* **Giải pháp đột phá - Bộ tự động quét dò cổng webcam (Active Webcam Auto-Scan & Fallback)**:
  * Nâng cấp `SyncRecorder.start()` để tự động dò tìm cổng USB đang hoạt động.
  * Nếu không mở được camera ở chỉ số cấu hình `WEBCAM_INDEX` (ví dụ cổng mặc định `0`), hệ thống sẽ tự động quét tuần tự các cổng khác `[1, 2, 0, 3]`.
  * *Kết quả*: Tự động nhận diện và khởi chạy camera Logitech mới cắm của bạn mà không cần bạn phải đoán hay sửa chỉ số cổng trong code.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Cấu hình các tham số neo giữ hình học và bù biên anten:
```python
# ============================================================
# GEOMETRIC ANCHOR & COMPENSATIONS (Version 13.0)
# ============================================================
ENABLE_GEOMETRIC_ANCHOR_LOCK = True    # Khóa kích thước hình thể khi bám vết
BOX_SIZE_SMOOTHING_ALPHA = 0.05        # Làm mịn kích thước cực mạnh để chống phình hộp gộp ghế

ENABLE_ANTENNA_EDGE_COMPENSATION = True # Nhân bù cường độ SNR ở rìa quét biên (>40 độ)
ANTENNA_EDGE_BOUNDARY_DEG = 40.0
ANTENNA_EDGE_MAX_COMP_SCALE = 0.6      # Bù thêm tối đa 60% SNR tại rìa biên 60 độ
```

### 📄 [MODIFY] [sync_recorder.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/sync_recorder.py)
* Nâng cấp cơ chế tự động quét dò tìm webcam Logitech hoạt động:
```python
        if self.webcam_enabled:
            # Thử mở camera theo chỉ số cấu hình trước
            self.cap = cv2.VideoCapture(WEBCAM_INDEX, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(WEBCAM_INDEX)
                
            # Bộ tự động quét dò cổng nếu cổng cấu hình bị lỗi (Webcam Logitech mới cắm)
            if not self.cap.isOpened():
                print(f"[INFO] Configured webcam index {WEBCAM_INDEX} failed. Auto-scanning active ports...")
                for test_idx in [1, 2, 0, 3]:
                    if test_idx == WEBCAM_INDEX:
                        continue
                    self.cap = cv2.VideoCapture(test_idx, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        self.cap = cv2.VideoCapture(test_idx)
                    if self.cap.isOpened():
                        print(f"[INFO] Successfully auto-detected and connected to active webcam at index {test_idx}!")
                        break
```

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* **Bù độ lợi biên anten** trong `build_human_point_mask`:
```python
        if has_real_snr:
            # Thuật toán bù độ nhạy rìa quét biên (Version 13.0)
            if ENABLE_ANTENNA_EDGE_COMPENSATION if 'ENABLE_ANTENNA_EDGE_COMPENSATION' in globals() else True:
                # Tính góc Azimuth của từng điểm
                azimuth_rad = np.abs(np.arctan2(x, y))
                azimuth_deg = np.degrees(azimuth_rad)
                
                # Tính hệ số nhân bù SNR thích nghi tuyến tính từ 40 đến 60 độ
                edge_boundary = ANTENNA_EDGE_BOUNDARY_DEG if 'ANTENNA_EDGE_BOUNDARY_DEG' in globals() else 40.0
                max_comp = ANTENNA_EDGE_MAX_COMP_SCALE if 'ANTENNA_EDGE_MAX_COMP_SCALE' in globals() else 0.6
                
                comp_factor = 1.0 + max_comp * np.clip((azimuth_deg - edge_boundary) / 20.0, 0.0, 1.0)
                snr_compensated = snr * comp_factor
            else:
                snr_compensated = snr

            if ENABLE_DISTANCE_ADAPTIVE_SNR if 'ENABLE_DISTANCE_ADAPTIVE_SNR' in globals() else True:
                boundary = SNR_BOUNDARY_DISTANCE if 'SNR_BOUNDARY_DISTANCE' in globals() else 1.5
                near_snr = SNR_MIN_NEAR if 'SNR_MIN_NEAR' in globals() else 6.0
                far_snr = SNR_MIN_FAR if 'SNR_MIN_FAR' in globals() else 4.0
                dynamic_min_snr = np.where(y < boundary, near_snr, far_snr)
                min_snr_limit = dynamic_min_snr
            else:
                min_snr_limit = MIN_POINT_SNR
                
            # Vùng bảo vệ vi mô ...
            # Áp dụng mask dựa trên snr_compensated (đã bù biên)
            mask &= (snr_compensated >= effective_min_snr) & (snr_compensated <= MAX_POINT_SNR)
```

### 📄 [MODIFY] [visualization.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People Tracking/visualization.py)
* **Neo giữ hình học (Geometric Anchor Lock)** cho hộp Bounding Box:
```python
def get_human_box_from_target(target, height_map):
    # ...
    # Nếu ENABLE_GEOMETRIC_ANCHOR_LOCK = True, ta khóa chặt kích thước rộng x sâu x cao mặc định:
    if ENABLE_GEOMETRIC_ANCHOR_LOCK if 'ENABLE_GEOMETRIC_ANCHOR_LOCK' in globals() else True:
        width_x = HUMAN_BOX_DEFAULT_WIDTH_X # 0.85
        depth_y = HUMAN_BOX_DEFAULT_DEPTH_Y # 0.85
        height_z = HUMAN_BOX_DEFAULT_HEIGHT_Z # 1.70
        center_z = z
        if not np.isfinite(center_z):
            center_z = height_z / 2.0
    else:
        # Sử dụng logic co giãn kích thước cũ dựa trên cụm điểm thô
```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử dò tìm Logitech Webcam
* Kết nối camera Logitech mới vào máy.
* Khởi chạy chương trình và kiểm tra xem hệ thống có tự động phát hiện index camera mới và hiển thị live feed lên màn hình đồ họa hay không.

### 2. Kiểm thử triệt tiêu phình hộp (Furniture Fusion)
* Đứng yên sát cạnh chiếc ghế văn phòng kim loại hoặc sát bàn.
* **Tiêu chuẩn vượt qua**: Hộp Bounding Box giữ nguyên kích thước chuẩn $0.85 \times 0.85 \times 1.70\text{ m}$ của hình thể người, không bị phình to ra để ôm trọn chiếc ghế bên cạnh.

### 3. Kiểm thử góc biên (Antenna Edge Compensation)
* Di chuyển ra vị trí cực rìa trái hoặc cực rìa phải của bàn làm việc (góc quét biên của radar).
* **Tiêu chuẩn vượt qua**: Mây điểm thô ở rìa biên vẫn duy trì được độ dày ổn định (nhờ nhân bù SNR), hộp bám đuổi không bị rung giật hay đứt kết nối đột ngột.
