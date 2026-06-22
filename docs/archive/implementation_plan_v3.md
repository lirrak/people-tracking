# Kế Hoạch Triển Khai Giải Quyết Lỗi Nhận Diện Loạn & Thiếu Target (Version 3)

Tài liệu này phân tích chi tiết nguyên nhân gốc rễ và đề xuất phương án tối ưu hóa thuật toán để khắc phục triệt để hiện tượng:
1. Nhận diện người bị loạn/nhấp nháy ở giai đoạn đầu (khởi động) hoặc một số thời điểm khi di chuyển.
2. Khi có 3 người đứng trong phòng thì hệ thống chỉ nhận diện được tối đa 2 người.

---

## 1. Phân Tích Nguyên Nhân Gốc Rễ (Root Cause Analysis)

### A. Hiện tượng nhận diện bị loạn ở giai đoạn đầu và nhấp nháy
Sau khi rà soát kỹ lưỡng logic của bộ lọc thời gian `GhostTargetFilter` trong [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py), chúng tôi đã phát hiện **2 lỗi logic cực kỳ nghiêm trọng**:

1. **Lỗi Logic Xác Thực Target Chưa Xác Nhận (Unconfirmed Target Paradox):**
   * Khi một target mới xuất hiện ở frame đầu tiên (chưa được confirm), nó bị ẩn đi để tránh nhiễu.
   * Tuy nhiên, nếu ở frame tiếp theo nó bị mất điểm hỗ trợ (`supported = False`), luồng code nhảy vào nhánh `else`. Ở đây, do `drop_unsupported_immediately` đang là `False` hoặc chưa được kiểm soát chặt chẽ, target chưa từng được xác nhận này lại **bị vẽ lên màn hình** vì số frame thiếu hụt của nó ($1$) nhỏ hơn `max_missing_frames` ($2$).
   * *Hậu quả:* Target chưa được xác nhận xuất hiện nhấp nháy/loạn xạ ngay khi nó bắt đầu chập chờn.
2. **Lỗi Không Giữ Khung Cho Target Bị Mất ID (Completely Missing Target Drop):**
   * Hàm `update()` của bộ lọc chỉ duyệt qua danh sách target đầu vào của frame hiện tại.
   * Nếu ở frame hiện tại, bộ theo vết của radar (hoặc bộ gom cụm) bị mất dấu hoàn toàn ID đó (không có trong danh sách đầu vào), vòng lặp `for target in targets` không chạy qua ID này.
   * *Hậu quả:* Hộp của người đó bị **biến mất ngay lập tức** ở frame tiếp theo bất kể `max_missing_frames = 2`! Cơ chế lưu khung hình đệm (missing frames buffer) hoàn toàn vô tác dụng đối với các target bị mất ID đột ngột, dẫn đến hiện tượng box giật cục và biến mất liên tục khi di chuyển.
3. **Nhiễu đơn lẻ từ Frame hiện tại (Current Frame Noise Leak):**
   * `POINTCLOUD_STABILIZER_KEEP_CURRENT_FRAME` đang là `True` khiến bộ ổn định điểm mây cho phép toàn bộ điểm của frame hiện tại đi qua mà không lọc qua bộ đếm Voxel.
   * *Hậu quả:* Các điểm nhiễu đơn lẻ ở frame hiện tại vẫn tạo ra cụm giả gây loạn hộp ở giai đoạn đầu.

### B. Hiện tượng có 3 người chỉ detect được 2
Nguyên nhân nằm ở các giới hạn cấu hình cực kỳ chặt chẽ trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py) nhằm chống Double Box ở Phase 1, nay đã vô tình bóp nghẹt khả năng phát hiện đa mục tiêu:

1. **Chế độ chặn song song Virtual Target:**
   * Cấu hình `VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS = True` quy định: Chỉ tạo hộp ảo từ Point Cloud nếu firmware radar **không nhận diện được bất kỳ ai**.
   * Nếu có 3 người, firmware nhận diện được 2 người (`len(final_targets) = 2 > 0`), chế độ này sẽ **tắt hoàn toàn** luồng tạo hộp ảo cho người thứ 3! Do đó người thứ 3 bị bỏ sót vĩnh viễn nếu firmware radar chưa kịp theo vết.
2. **Giới hạn số hộp ảo quá thấp:**
   * `VIRTUAL_CLUSTER_MAX_TARGETS = 1` chỉ cho phép vẽ tối đa 1 hộp ảo từ Point Cloud. Nếu có nhiều hơn 1 người chưa được firmware theo vết, họ sẽ không thể có hộp ảo.
3. **Khoảng cách gộp cụm quá rộng:**
   * `VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 1.20` m. Nếu hai người đứng tương đối gần nhau (dưới 1.2 mét, rất phổ biến khi có 3 người trong phòng nhỏ), Point Cloud của họ sẽ bị gộp chung thành một cụm duy nhất, làm mất đi 1 người.

---

## 2. Giải Pháp Khắc Phục Đề Xuất (Proposed Solutions)

Chúng tôi đề xuất nâng cấp hệ thống lên **Version 3** với các cải tiến thuật toán mạnh mẽ:

### Lớp 1: Thiết kế lại bộ lọc thời gian GhostTargetFilter (filters.py)
* **Dead Reckoning & State Keeper:** Bổ sung biến thành viên `self.last_target_state = {}` để lưu lại trạng thái đầy đủ cuối cùng của các target đã từng được xác nhận (`confirmed`).
* **Đảm bảo giữ khung thực tế:** Khi một ID target biến mất hoàn toàn khỏi danh sách đầu vào, nếu nó đã từng được xác nhận trước đó và số frame biến mất $\le$ `max_missing_frames`, chúng tôi sẽ phục dựng lại target từ trạng thái lưu trữ cuối cùng, tiến hành smooth vị trí và vẽ tiếp để giữ hộp không bị biến mất đột ngột.
* **Sửa lỗi Unconfirmed paradox:** Chỉ cho phép đưa target vào bộ đệm giữ khung (`missing_count`) nếu target đó **đã từng được xác nhận thành công** trước đó.

### Lớp 2: Mở rộng cấu hình đa mục tiêu song song (settings.py)
* Thiết lập `VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS = False` để cho phép tạo hộp ảo song song với target phần cứng. Sự an toàn chống Double Box sẽ do cơ chế lọc trùng thông minh của Lớp 2 gánh vác.
* Tăng `VIRTUAL_CLUSTER_MAX_TARGETS = 3` (hoặc 4) để hỗ trợ nhận diện nhiều người cùng lúc bằng Point Cloud.
* Giảm khoảng cách gộp cụm ảo `VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 0.85` m để tránh gộp hai người đứng gần nhau thành một.
* Tắt `POINTCLOUD_STABILIZER_KEEP_CURRENT_FRAME = False` để bộ lọc Voxel hits lọc sạch nhiễu đơn lẻ của cả frame hiện tại, tăng độ ổn định tuyệt đối ở giai đoạn đầu.
* Thiết lập `GHOST_DROP_UNSUPPORTED_IMMEDIATELY = False` để kích hoạt thực sự bộ đệm giữ khung hình cho các target bị chập chờn điểm hỗ trợ.

---

## 3. Chi Tiết Các Thay Đổi Sẽ Thực Hiện (Review Proposed Code)

Chúng tôi tiếp tục cam kết **KHÔNG xóa bất kỳ file nào**. Dưới đây là chi tiết các dòng code đề xuất thay đổi:

### 📄 Cập nhật cấu hình trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)

```diff
# Cho phép tạo target ảo song song kể cả khi đã có target firmware
-VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS = True
+VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS = False

# Tăng số lượng target ảo tối đa để hỗ trợ nhận diện 3 người trở lên
-VIRTUAL_CLUSTER_MAX_TARGETS = 1
+VIRTUAL_CLUSTER_MAX_TARGETS = 3

# Giảm bán kính gộp cụm để tránh gộp 2 người đứng gần nhau
-VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 1.20
+VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 0.85

# Tắt bỏ qua lọc frame hiện tại để triệt tiêu nhiễu đơn lẻ tức thời ở giai đoạn đầu
-POINTCLOUD_STABILIZER_KEEP_CURRENT_FRAME = True
+POINTCLOUD_STABILIZER_KEEP_CURRENT_FRAME = False

# Tắt drop ngay lập tức để cho phép bộ đệm giữ khung hoạt động khi chập chờn
-GHOST_DROP_UNSUPPORTED_IMMEDIATELY = True
+GHOST_DROP_UNSUPPORTED_IMMEDIATELY = False
```

### 📄 Cấu trúc lại bộ lọc thời gian trong [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)

```diff
     def __init__(
         self,
         max_missing_frames=3,
         min_support_points=3,
         support_radius_x=0.70,
         support_radius_y=0.70,
         support_radius_z=1.20,
         duplicate_distance_xy=0.85,
         drop_unsupported_immediately=False,
         confirm_frames=2,
         apply_confirmation_to_firmware_targets=False,
         enable_smoothing=True,
         smoothing_alpha=0.35,
         smoothing_reset_distance=1.50,
     ):
         ...
         self.missing_count = {}
         self.last_seen_frame = {}
         self.confirm_count = {}
         self.smoothed_position = {}
+        self.last_target_state = {}  # Lưu trữ trạng thái cuối cùng của target đã confirm
```

*(Phương thức `reset`)*
```diff
     def reset(self):
         self.missing_count.clear()
         self.last_seen_frame.clear()
         self.confirm_count.clear()
         self.smoothed_position.clear()
+        self.last_target_state.clear()
```

*(Thiết kế lại toàn bộ phương thức `update` để sửa triệt để 2 lỗi logic)*
```python
    def update(self, targets, point_cloud, frame_number=None):
        if targets is None:
            targets = []

        filtered_targets = []
        current_ids = set()

        # 1) Xử lý các target có mặt trong frame hiện tại
        for target in targets:
            target = dict(target)
            tid = target.get("tid", -1)
            current_ids.add(tid)

            supported = self.is_target_supported(target, point_cloud)
            target["ghostFiltered"] = not supported

            if supported:
                self.missing_count[tid] = 0
                if frame_number is not None:
                    self.last_seen_frame[tid] = frame_number

                if self.is_confirmed(target, supported):
                    target = self.smooth_target(target)
                    filtered_targets.append(target)
                    self.last_target_state[tid] = target.copy()  # Lưu lại trạng thái confirm tốt nhất
            else:
                # Chỉ giữ lại target chập chờn nếu trước đó nó đã TỪNG được xác nhận thành công
                was_previously_confirmed = (self.confirm_count.get(tid, 0) >= self.confirm_frames) or (not self.should_apply_confirmation(target))
                
                self.confirm_count[tid] = 0
                self.missing_count[tid] = self.missing_count.get(tid, 0) + 1
                target["missingFrames"] = self.missing_count[tid]

                if not self.drop_unsupported_immediately and was_previously_confirmed:
                    if self.missing_count[tid] <= self.max_missing_frames:
                        target = self.smooth_target(target)
                        filtered_targets.append(target)
                        self.last_target_state[tid] = target.copy()

        # 2) Xử lý các target bị mất ID hoàn toàn khỏi frame hiện tại (Dead Reckoning)
        for tid in list(self.last_target_state.keys()):
            if tid not in current_ids:
                self.missing_count[tid] = self.missing_count.get(tid, 0) + 1
                
                if not self.drop_unsupported_immediately and self.missing_count[tid] <= self.max_missing_frames:
                    # Tái tạo target từ trạng thái đã confirm cuối cùng
                    missing_target = self.last_target_state[tid].copy()
                    missing_target["missingFrames"] = self.missing_count[tid]
                    missing_target["ghostFiltered"] = True
                    
                    missing_target = self.smooth_target(missing_target)
                    filtered_targets.append(missing_target)
                else:
                    # Đã quá thời hạn giữ khung -> Tiến hành xóa sạch trạng thái
                    if self.missing_count[tid] > self.max_missing_frames:
                        self.missing_count.pop(tid, None)
                        self.last_seen_frame.pop(tid, None)
                        self.confirm_count.pop(tid, None)
                        self.smoothed_position.pop(tid, None)
                        self.last_target_state.pop(tid, None)

        # 3) Lọc trùng và sắp xếp
        filtered_targets = self.remove_duplicates(filtered_targets)
        return filtered_targets
```

---

## 4. Kế Hoạch Xác Minh & Thử Nghiệm (Verification Plan)

Sau khi được bạn phê duyệt, chúng tôi sẽ thực hiện theo workflow sau:

1. **Bước 1: Áp dụng các thay đổi cấu hình và mã nguồn** (Cập nhật `settings.py` và `filters.py`).
2. **Bước 2: Kiểm tra tính đúng đắn của mã nguồn** (Chạy biên dịch `py_compile` để đảm bảo không có lỗi cú pháp).
3. **Bước 3: Chạy thực nghiệm hệ thống** (`python main.py`):
   - Đánh giá độ ổn định ở giai đoạn khởi động (hộp xuất hiện mượt mà, không bị giật/nháy loạn).
   - Đánh giá khả năng bám vết 3 người đồng thời (đảm bảo hiển thị đầy đủ 3 hộp khi có 3 người đứng gần nhau khoảng 1m).
4. **Bước 4: Cập nhật tài liệu kết quả** vào file báo cáo kiểm thử [walkthrough.md](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/docs/walkthrough.md).
