# Kế Hoạch Triển Khai Giải Quyết Lỗi 2 Box (Double Box) & Hộp Ma (Ghost Box) (Version 2)

Tài liệu này phân tích chi tiết nguyên nhân gốc rễ và đề xuất phương án tối ưu hóa bộ lọc để khắc phục triệt để hiện tượng:
1. Một người đứng trong vùng quét bị vẽ thành 2 hộp (`Double Box`).
2. Hộp ma vẫn lưu lại hoặc nhấp nháy khi người rời đi (`Ghost Box`).

---

## 1. Cơ Sở Vật Lý & Cơ Chế Hoạt Động Của Radar mmWave

Trước khi đi vào phân tích chi tiết lỗi, chúng ta cần làm rõ nguyên lý phát hiện con người và cách radar mmWave (IWR6843AOP) phân biệt người với các đồ vật tĩnh hay nhiễu khác.

### A. Cách Radar phát hiện sóng phản xạ từ người
Radar IWR6843AOP hoạt động ở băng tần **60GHz - 64GHz** (bước sóng cực ngắn $\approx 5\text{ mm}$), phát hiện con người qua các cơ chế vật lý và xử lý tín hiệu sau:
1. **Tính chất điện môi:** Cơ thể con người chứa khoảng 60%–70% nước. Nước có hằng số điện môi cực cao ở tần số 60 GHz. Sự thay đổi đột ngột hằng số điện môi giữa không khí và da/quần áo tạo ra bề mặt phản xạ sóng điện từ cực tốt, phản xạ dội ngược sóng điện từ về phía anten thu.
2. **Xử lý tín hiệu 3D (3D FFT):**
   * **Range FFT (Khoảng cách):** Đo tần số beat của sóng thu được so với sóng phát đi để tính toán khoảng cách chính xác.
   * **Doppler FFT (Vận tốc & Vi động):** Đo sự dịch pha qua các chirp. Mọi cử động dù nhỏ nhất (như nhịp thở làm phập phồng lồng ngực $\approx 1\text{mm} - 12\text{mm}$) đều tạo ra độ dịch pha Doppler đặc trưng (Micro-Doppler).
   * **Angle FFT (Góc nhìn):** Nhờ mảng anten AOP (Antenna-on-Package), radar tính toán độ lệch pha giữa các anten để xác định Góc ngang (Azimuth) và Góc dọc (Elevation).
   * **Point Cloud:** Kết quả thu được là một đám mây điểm 3D có tọa độ $(X, Y, Z)$ kèm tốc độ Doppler và cường độ tín hiệu (SNR).

### B. Sự khác biệt giữa Người và Đồ vật khác

| Đặc tính | Phản xạ từ Người | Vật thể tĩnh (Tường, bàn ghế) | Vật thể kim loại (Tủ sắt, cửa) | Nhiễu động cơ học (Quạt, rèm) |
| :--- | :--- | :--- | :--- | :--- |
| **Vận tốc Doppler** | **Luôn động:** Nhịp thở và vi chuyển động tạo ra Doppler khác 0 liên tục. | **Bằng 0 tuyệt đối** ở mọi khung hình. | **Bằng 0 tuyệt đối.** | **Tuần hoàn tần số cao:** Dao động có chu kỳ đều đặn. |
| **Cường độ (RCS / SNR)**| **Trung bình & Phân tán:** Hấp thụ một phần, SNR vừa phải ($5 - 40\text{ dB}$). | **Yếu đến Trung bình:** Gỗ, nhựa hấp thụ sóng nhiều hơn, phản xạ rời rạc. | **Cực mạnh & Tập trung:** Kim loại phản xạ gần như 100% sóng, SNR cực lớn. | **Yếu đến Trung bình:** Nhấp nháy liên tục theo nhịp chuyển động. |
| **Hình học (Geometry)** | **Trục dọc sinh học:** Điểm mây cao từ $0.2\text{m} - 1.8\text{m}$, bề rộng hợp lý. | **Mảng phẳng lớn/Thấp:** Trải ngang dài (tường) hoặc dẹt sát sàn (mặt bàn). | **Điểm đơn lẻ (Single Point):** Tạo tiêu điểm chói phản xạ mạnh nhất. | **Vùng cục bộ nhỏ:** Tập trung ở cánh quạt hoặc mép rèm. |
| **Phản xạ đa đường (Multipath)** | **Có (Qua sàn):** Tạo ảnh gương ảo nằm sâu dưới sàn nhà ($Z < 0$). | **Ổn định:** Ít biến động theo thời gian. | **Có:** Tạo ảnh gương đối xứng qua vách kim loại. | **Không ổn định:** Tạo nhiễu động dạng quầng bao quanh. |

### C. Cách thuật toán trong code tận dụng sự khác biệt này
* **Static Clutter Removal:** Firmware radar tự động lọc bỏ các phản xạ có Doppler = 0 (bàn, ghế, tủ).
* **Lọc Target ngoài ROI (Lớp 1):** Dùng `TARGET_ROI_Z` để lọc bỏ các target có độ cao trung tâm phi vật lý dưới sàn hoặc quá cao.
* **Gộp trùng thông minh (Lớp 2):** Hàm `remove_duplicates` gộp target thật và ảnh ảo phản xạ sàn dựa trên vị trí không gian 3D đặc thù.
* **Xác thực thời gian (Lớp 3):** Tận dụng tính liên tục của động học người để khử nhiễu hộp ma tức thời.

---

## 2. Phân Tích Nguyên Nhân Gốc Rễ (Root Cause Analysis)

Dựa trên dữ liệu hình ảnh trực quan và file log hệ thống truyền về, chúng tôi phát hiện 2 nguyên nhân kỹ thuật chính:

### A. Hiện tượng 1 người ra 2 box (Double Box)
* **Nguyên nhân do Phản xạ sàn (Floor Reflection Multipath):** Radar TI đôi khi theo vết các phản xạ đa đường từ mặt sàn, tạo ra các target phần cứng (`firmware_target`) có tâm Z rất thấp hoặc âm (như `ID 1` có `Z = -0.41m` trong ảnh của bạn).
* **Do Bán kính quét dọc quá lớn:** Mặc dù điểm mây (point cloud) đã được cắt ở mức `Z >= 0.20m` (loại bỏ nhiễu sàn), bộ lọc trong Python vẫn dùng bán kính quét dọc `GHOST_SUPPORT_RADIUS_Z = 1.20m`. Do đó, target ảo nằm dưới sàn `Z = -0.41m` vẫn quét và ôm lấy các điểm thuộc chân của người thật (quét tới `-0.41 + 1.20 = 0.79m`). Cả target thật (`ID 0`, `Z ~ 0.06m`) và target phản xạ dưới sàn (`ID 1`, `Z ~ -0.41m`) đều đủ điều kiện điểm hỗ trợ để hiển thị đồng thời.
* **Khoảng cách gộp trùng quá hẹp:** Khoảng cách XY giữa hai target này là `1.27m`. Ngưỡng lọc trùng hiện tại `GHOST_DUPLICATE_DISTANCE_XY = 1.05m` không thể gộp chúng lại, dẫn đến hiển thị song song 2 box.

### B. Hiện tượng hộp ma lưu lại khi người rời đi (Ghost Box)
* **Chưa áp dụng xác thực thời gian cho Target cứng:** `APPLY_CONFIRMATION_TO_FIRMWARE_TARGETS` đang là `False`. Mọi nhiễu tức thời được radar phát ra dưới dạng target cứng đều được vẽ box ngay lập tức ở frame đầu tiên.
* **Thời gian lưu vết quá dài:** `GHOST_MAX_MISSING_FRAMES` đang là `4` frames, khiến box cũ tiếp tục tồn tại thêm 4 frame sau khi người đã rời đi.

---

## 3. Giải Pháp Khắc Phục Đề Xuất (Proposed Solutions)

Chúng tôi sẽ triển khai hệ thống lọc 3 lớp thông minh:

### Lớp 1: Lọc Target ngoài vùng ROI vật lý (Target ROI Filter)
* Loại bỏ ngay lập tức các target có tâm Z phi vật lý (nằm ngoài vùng cơ thể người thực tế).
* Thêm tham số mới `TARGET_ROI_Z = (-0.15, 2.20)` trong `settings.py`. Nếu target có `posZ < -0.15m` hoặc `posZ > 2.20m`, nó sẽ bị loại bỏ hoàn toàn khỏi luồng xử lý.

### Lớp 2: Cơ chế gộp trùng thông minh do phản xạ sàn (Smart Floor-Reflection Merger)
* Cải tiến hàm `remove_duplicates` trong `filters.py`:
  * Nếu 2 target cách nhau dưới `1.15m`, coi là trùng lặp.
  * Nếu 2 target cách nhau dưới `1.35m` **VÀ** ít nhất một trong hai có tâm nằm sát sàn (`Z < 0.05m`), coi là trùng lặp do phản xạ sàn và gộp làm một.

### Lớp 3: Tối ưu hóa bộ lọc thời gian (Temporal Tuning)
* Bật `APPLY_CONFIRMATION_TO_FIRMWARE_TARGETS = True` để bắt buộc các target phần cứng cũng phải được xác thực qua 2 frame liên tiếp trước khi hiển thị.
* Giảm `GHOST_MAX_MISSING_FRAMES` từ `4` xuống `2` frames để xóa hộp ma nhanh gấp đôi ngay khi người rời vùng quét.

---

## 4. Chi Tiết Các Thay Đổi Sẽ Thực Hiện (Review Proposed Code)

Chúng tôi cam kết **KHÔNG xóa bất kỳ file nào**. Dưới đây là chi tiết các dòng code đề xuất thay đổi để bạn xem xét trước:

### 📄 Cập nhật cấu hình trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)

```diff
# Thêm cấu hình giới hạn chiều cao trung tâm target
+TARGET_ROI_Z = (-0.15, 2.20)

# Bật xác thực cho target phần cứng để chống nhảy hộp ma tức thời
-APPLY_CONFIRMATION_TO_FIRMWARE_TARGETS = False
+APPLY_CONFIRMATION_TO_FIRMWARE_TARGETS = True

# Giảm số frame lưu giữ để xóa hộp ma nhanh hơn khi người đi ra
-GHOST_MAX_MISSING_FRAMES = 4
+GHOST_MAX_MISSING_FRAMES = 2

# Tăng khoảng cách gộp trùng tổng quát
-GHOST_DUPLICATE_DISTANCE_XY = 1.05
+GHOST_DUPLICATE_DISTANCE_XY = 1.15
```

### 📄 Cập nhật logic lọc Target ROI trong [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

*(Khoảng dòng 615 - Thêm kiểm tra chiều cao tâm Z của Target)*
```diff
     for target in raw_targets:
         target = dict(target)
         tid = target.get("tid", -1)
+        tz = target.get("posZ", 0.0)
+
+        # Loại bỏ các target có vị trí tâm phi vật lý (như phản xạ sâu dưới sàn Z = -0.41m)
+        if tz < TARGET_ROI_Z[0] or tz > TARGET_ROI_Z[1]:
+            continue
 
         associated_points = empty_point_cloud()
```

### 📄 Cập nhật bộ lọc trùng thông minh trong [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)

*(Khoảng dòng 252 - Hàm `remove_duplicates`)*
```diff
         for target in sorted_targets:
             tx = target.get("posX", 0.0)
             ty = target.get("posY", 0.0)
+            tz = target.get("posZ", 0.0)
 
             is_duplicate = False
 
             for kept in kept_targets:
                 kx = kept.get("posX", 0.0)
                 ky = kept.get("posY", 0.0)
+                kz = kept.get("posZ", 0.0)
 
                 distance_xy = float(np.sqrt((tx - kx) ** 2 + (ty - ky) ** 2))
 
-                if distance_xy < self.duplicate_distance_xy:
+                # Gộp trùng thông thường
+                if distance_xy < self.duplicate_distance_xy:
+                    is_duplicate = True
+                    break
+
+                # Gộp trùng thông minh do phản xạ sàn (Floor Reflection Merger)
+                # Nếu khoảng cách XY < 1.35m và có một target nằm sát sàn (Z < 0.05m)
+                is_floor_split = (distance_xy < 1.35) and (tz < 0.05 or kz < 0.05)
+                if is_floor_split:
+                    is_duplicate = True
+                    break
 
             if not is_duplicate:
```

---

## 5. Kế Hoạch Xác Minh & Thử Nghiệm (Verification Plan)

Sau khi được bạn phê duyệt, chúng tôi sẽ thực hiện theo workflow sau:

1. **Bước 1: Áp dụng thay đổi cấu hình và mã nguồn** (Cập nhật 3 file `settings.py`, `pointcloud_processing.py`, `filters.py`).
2. **Bước 2: Kiểm tra tính đúng đắn của mã nguồn** (Run cú pháp Python độc lập để đảm bảo không lỗi import/runtime).
3. **Bước 3: Chạy thực nghiệm hệ thống** (`python -u main.py`):
   - Đánh giá sự biến mất ngay lập tức của target phản xạ sàn âm (`Z = -0.41m`).
   - Đánh giá độ nhạy khi người thật bước vào (đảm bảo hộp xuất hiện ổn định sau 2 frame xác thực).
   - Đánh giá tốc độ xóa hộp ma khi người rời khỏi tầm quét.
4. **Bước 4: Cập nhật tài liệu kết quả** vào file báo cáo kiểm thử `docs/walkthrough.md`.
