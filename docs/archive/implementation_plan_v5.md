# Kế Hoạch Triển Khai Giải Quyết Lỗi Nhận Diện Loạn & Lọc Nhiễu Radar (Version 5)

Tài liệu này đề xuất phương án cải tiến và sửa đổi hệ thống lên **Version 5** nhằm giải quyết triệt để lỗi loạn hộp nhận diện (box jitter) và hiện tượng nhảy mã định danh ID (ID fragmentation) được phát hiện trong kết quả chạy thực tế của `main.py`.

---

## 1. Phân Tích Hiện Tượng Loạn Hộp Trong Logs Thực Tế
Qua phân tích log chạy thô tại [radar_run_output.log](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/log/radar_run_output.log), hệ thống đang gặp lỗi nhận diện không cố định do các nguyên nhân liên đới sau:

1. **Bán kính kế thừa vết quá hẹp (`VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 0.85m`)**:
   * Cấu hình này đang bị dùng chung cho cả **2 mục đích khác nhau**: (1) Gộp cụm điểm trong một frame và (2) So khớp kế thừa ID giữa các frame liên tiếp.
   * Khi tâm cụm mây điểm của người dịch chuyển nhẹ $> 0.85$ mét giữa hai frame (do người di chuyển hoặc mây điểm thắt nút thưa/dày), hệ thống không khớp được cụm này với ID cũ. Hệ thống coi đây là mục tiêu mới và cấp ID tăng dần (`1000` $\rightarrow$ `1001` $\rightarrow$ `1002` $\rightarrow$ `1047`).
2. **Bộ lọc vật thể tĩnh bị vô hiệu hóa vô tình**:
   * Bộ lọc `ENABLE_STATIC_CLUTTER_FILTER` yêu cầu một ID phải tồn tại cố định liên tục **30 frame** (`STATIC_CLUTTER_MIN_FRAMES = 30`) để xác định đó là bàn ghế và ẩn đi.
   * Vì ID bị nhảy quá nhanh (thường bị xóa hoặc đổi ID chỉ sau 2-10 frame), lịch sử vị trí của ID đó liên tục bị xóa và không bao giờ đạt ngưỡng 30 frame. Do đó, các nhiễu tĩnh từ cạnh bàn, mảng tường không bao giờ bị loại bỏ.
3. **Bộ giữ khung quá ngắn (`GHOST_MAX_MISSING_FRAMES = 2`) & Xác nhận quá nhạy (`TARGET_CONFIRM_FRAMES = 2`)**:
   * Chỉ cần radar mất điểm trong 0.1 giây (2 frame), box lập tức bị xóa và khi có điểm lại sẽ xuất hiện lại với một ID hoàn toàn mới.
   * Nhiễu nhấp nháy xuất hiện chỉ 2 frame đã đủ điều kiện dựng box tạm thời, tạo cảm giác hộp nhấp nháy liên tục (loạn box).

### 1.1. Chứng Minh Thực Tế Bằng Dữ Liệu Logs (Empirical Log Analysis)

Dựa trên dữ liệu thực tế trích xuất từ file log chạy thử nghiệm [radar_run_output.log](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/log/radar_run_output.log), dưới đây là bằng chứng số liệu cụ thể cho thấy sự đứt gãy vết (ID fragmentation) và hiện tượng bypass bộ lọc tĩnh:

#### A. Minh chứng cho việc nhảy ID liên tục trên cùng 1 người thực tế:
Hệ thống ghi nhận một người đứng im/di chuyển cực kỳ ít tại khu vực tọa độ $X \approx [0.7m, 1.1m], Y \approx [0.6m, 0.9m], Z \approx [0.2m, 0.3m]$. Tuy nhiên, mã định danh liên tục bị thay đổi:
* **Thời kỳ 1 (ID 1000)**: 
  * Dòng 178: `ID 1000 | pos=(0.99, 0.74, 0.29) m` (vừa được phát hiện từ DBSCAN Cluster).
  * Dòng 203: `ID 1000 | pos=(0.98, 0.78, 0.29) m` (vẫn hoạt động ổn định).
  * Dòng 230: `ID 1000 | pos=(0.98, 0.81, 0.29) m | missing_frames=1` (bắt đầu mất tín hiệu).
  * Dòng 233: `ID 1000 | pos=(0.98, 0.81, 0.29) m | missing_frames=2` (mất tín hiệu frame thứ 2).
  * **Hậu quả**: Vì `GHOST_MAX_MISSING_FRAMES = 2`, ngay frame tiếp theo ID 1000 bị xóa sổ hoàn toàn khỏi tracker.
* **Thời kỳ 2 (ID 1047)**:
  * Sau một vài frame mất tín hiệu hoàn toàn, mây điểm xuất hiện trở lại tại chính vị trí đó.
  * Dòng 2296: Hệ thống tạo ra một ID hoàn toàn mới **ID 1047** tại `pos=(0.96, 0.75, 0.28) m` do không thể tìm thấy ID 1000 cũ trong bộ nhớ (đã bị xóa).
  * Dòng 2374: `ID 1047 | pos=(0.77, 0.82, 0.27) m`.
  * Dòng 2583: `ID 1047 | pos=(0.93, 0.81, 0.30) m`.
  * Dòng 2601: `ID 1047 | pos=(0.92, 0.83, 0.30) m | missing_frames=2` -> tiếp tục bị xóa!

> [!IMPORTANT]
> **Nhận định:** Người dùng thực tế không hề di chuyển nhanh hoặc biến mất, nhưng do bộ giữ khung `GHOST_MAX_MISSING_FRAMES` quá ngắn (0.1 giây), radar chỉ cần nháy nhẹ là ID bị hủy và cấp mới. Điều này chứng minh tại sao người dùng nhìn thấy các box nhận diện chớp tắt liên tục và ID nhảy từ `1000` lên `1047`.

#### B. Minh chứng cho việc Nhiễu Tĩnh (Static Clutter) từ đồ vật "qua mặt" bộ lọc:
Trong phòng thí nghiệm có vật thể tĩnh (bàn/ghế) ở vùng tọa độ xa radar tại $X \approx 1.1m, Y \approx 5.0m, Z \approx 1.1m$.
* **Dữ liệu log**:
  * Dòng 235: `ID 1002 | pos=(1.10, 5.01, 1.17) m` xuất hiện với điểm số rất cao `score=78.0` (vượt ngưỡng human).
  * Dòng 250: `ID 1002 | pos=(1.08, 4.97, 0.99) m` (hoạt động được 15 frame).
  * Dòng 268: `ID 1002 | pos=(1.05, 4.99, 1.03) m | missing_frames=2` -> **Bị xóa!**
  * Dòng 316: `ID 1002 | pos=(1.06, 4.88, 1.19) m` xuất hiện trở lại dưới dạng ID 1002 mới (do ID base ảo được tuần hoàn hoặc reset khi không có mục tiêu hoạt động).
  * Dòng 322: `ID 1002 | pos=(1.06, 4.89, 1.19) m | missing_frames=2` -> **Bị xóa tiếp!**

> [!WARNING]
> **Hậu quả bypass bộ lọc tĩnh:** Vì vật thể tĩnh này liên tục bị xóa và tạo lại chỉ sau 15-20 frame, nó không bao giờ đạt ngưỡng tích lũy liên tục **30 frame** của bộ lọc tĩnh (`STATIC_CLUTTER_MIN_FRAMES = 30`). Lịch sử vị trí của ID bị reset hoàn toàn. Do đó, thuật toán tính độ lệch chuẩn vị trí không bao giờ được kích hoạt, khiến hộp nhiễu tĩnh xuất hiện nhấp nháy mãi mãi.

---

### 1.2. So Sánh Tính Năng Giữa Version 4 và Version 5 (Kế thừa & Cải tiến)

Để làm rõ lý do tại sao phương án này là tối ưu và không bị trùng lặp với các nỗ lực thiết kế trước đây, dưới đây là bảng so sánh phân tích tính kế thừa giữa hai phiên bản:

| Trọng tâm kỹ thuật | Version 4 (Thiết lập khung thuật toán cơ bản) | Version 5 (Tinh chỉnh và tối ưu tham số thực nghiệm) | Mục tiêu giải quyết của Version 5 |
| :--- | :--- | :--- | :--- |
| **Bán kính liên kết mây điểm** | Sử dụng chung `VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 0.85m` cho gộp cụm nội frame và so khớp ID liên khung. | **Tách biệt hoàn toàn**: Giữ `0.85m` cho gộp cụm nội frame. Thêm mới **`VIRTUAL_TRACKER_ASSOCIATION_RADIUS = 1.30m`** cho bộ Tracker khớp ID liên khung. | **Sửa lỗi nhảy ID**: Cho phép người di chuyển hoặc mây điểm dao động nhẹ vẫn giữ nguyên ID cố định, không tạo ID mới. |
| **Bộ đệm giữ hộp ảo (`Ghost Frames`)** | Chỉ lưu giữ **`2`** frame (`GHOST_MAX_MISSING_FRAMES = 2`). | Tăng lên giữ **`5`** frame (`GHOST_MAX_MISSING_FRAMES = 5`). | **Chống mất dấu tạm thời**: Giữ hộp ổn định ngay cả khi người đứng im làm radar bị hụt điểm trong tối đa 0.25 giây. |
| **Xác nhận Target mới (`Confirm Frames`)** | Chỉ cần **`2`** frame liên tiếp (`TARGET_CONFIRM_FRAMES = 2`). | Cần **`4`** frame liên tiếp (`TARGET_CONFIRM_FRAMES = 4`). | **Triệt tiêu nhiễu nhấp nháy**: Các điểm nhiễu thoáng qua (1-2 frame) sẽ bị bỏ qua, không thể tự dựng hộp ảo. |
| **Kích hoạt lọc nhiễu tĩnh** | Tích lũy liên tục **`30`** frame (~1.5 giây) dưới **cùng một ID** (`STATIC_CLUTTER_MIN_FRAMES = 30`). | Rút ngắn xuống còn **`15`** frame (~0.75 giây) (`STATIC_CLUTTER_MIN_FRAMES = 15`). | **Triệt tiêu vật thể tĩnh nhanh chóng**: Khi ID đã cố định lâu dài nhờ bán kính 1.30m, đồ vật tĩnh chỉ cần 0.75s là bị ẩn đi hoàn toàn. |

---

## 2. Giải Pháp Khắc Phục Đề Xuất (Proposed Solutions)

Chúng tôi đề xuất nâng cấp hệ thống lên **Version 5** với các thay đổi trọng tâm sau:

1. **Tách biệt 2 bán kính xử lý mây điểm**:
   * Giữ nguyên `VIRTUAL_CLUSTER_CLUSTER_MERGE_DISTANCE_XY = 0.85` mét cho việc gộp các cụm điểm thưa trên cơ thể người trong cùng một frame.
   * Bổ sung tham số mới `VIRTUAL_TRACKER_ASSOCIATION_RADIUS = 1.30` mét dùng riêng cho bộ tracker `VirtualTargetTracker` để so khớp kế thừa ID giữa các frame liên tiếp.
2. **Tinh chỉnh các tham số bộ lọc thời gian trong `settings.py`**:
   * Tăng `GHOST_MAX_MISSING_FRAMES` từ `2` lên **`5`** frame để chịu đựng tốt hơn các khoảng mất điểm tạm thời của radar.
   * Tăng `TARGET_CONFIRM_FRAMES` từ `2` lên **`4`** frame để loại bỏ các hộp nhiễu nhấp nháy tức thời.
   * Giảm `STATIC_CLUTTER_MIN_FRAMES` từ `30` xuống **`15`** frame để bộ lọc tĩnh có thể nhận diện và ẩn nhiễu bàn ghế nhanh hơn (trong vòng 0.75 giây).

---

## 3. Các File Sẽ Sửa Đổi (Proposed Code Changes)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)

#### Cập nhật các tham số lọc nhiễu tĩnh và bộ đệm thời gian:
```diff
 # Cần bao nhiêu frame liên tiếp trước khi xác nhận target mới.
 # Tăng lên 3 nếu detect loạn. Giảm xuống 1 nếu người thật bị chậm hiện box.
-TARGET_CONFIRM_FRAMES = 2
+TARGET_CONFIRM_FRAMES = 4

 # Số frame giữ lại target khi không còn point cloud hỗ trợ.
 # Giảm xuống 2 hoặc 3 nếu box vẫn tồn tại quá lâu sau khi người rời đi.
-GHOST_MAX_MISSING_FRAMES = 2
+GHOST_MAX_MISSING_FRAMES = 5
```

```diff
 # ID bắt đầu cho các target ảo sinh ra từ point cloud cluster.
 VIRTUAL_TARGET_ID_BASE = 1000
 
+# Khoảng cách tối đa giữa các frame để so khớp kế thừa ID ảo (mét).
+# Cho phép cụm mây điểm di chuyển linh hoạt vẫn giữ được đúng mã định danh cũ.
+VIRTUAL_TRACKER_ASSOCIATION_RADIUS = 1.30
```

```diff
 # ============================================================
 # STATIC CLUTTER FILTER SETTINGS (Version 4)
 # ============================================================
 ENABLE_STATIC_CLUTTER_FILTER = True
-STATIC_CLUTTER_MIN_FRAMES = 30
+STATIC_CLUTTER_MIN_FRAMES = 15       # Số frame để bắt đầu lọc vật thể tĩnh
```

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

#### Tinh chỉnh hàm liên kết của `VirtualTargetTracker` để áp dụng bán kính so khớp mới:
```python
<<<<
            # Sắp xếp các cặp theo khoảng cách tăng dần
            pairs.sort(key=lambda x: x[0])
            
            # Liên kết tham lam (Greedy Association)
            for dist_xy, c_idx, tid in pairs:
                if c_idx not in matched_cluster_ids and tid not in matched_tids:
                    # Nếu nằm trong bán kính gộp cụm hợp lý, kế thừa ID
                    if dist_xy <= VIRTUAL_CLUSTER_MERGE_DISTANCE_XY:
                        matched_cluster_ids.add(c_idx)
                        matched_tids.add(tid)
                        assignments[c_idx] = tid
====
            # Sắp xếp các cặp theo khoảng cách tăng dần
            pairs.sort(key=lambda x: x[0])
            
            # Áp dụng bán kính so khớp liên khung độc lập để bảo toàn ID ổn định
            assoc_radius = VIRTUAL_TRACKER_ASSOCIATION_RADIUS if 'VIRTUAL_TRACKER_ASSOCIATION_RADIUS' in globals() else VIRTUAL_CLUSTER_MERGE_DISTANCE_XY
            
            # Liên kết tham lam (Greedy Association)
            for dist_xy, c_idx, tid in pairs:
                if c_idx not in matched_cluster_ids and tid not in matched_tids:
                    if dist_xy <= assoc_radius:
                        matched_cluster_ids.add(c_idx)
                        matched_tids.add(tid)
                        assignments[c_idx] = tid
>>>>
```

---

## 4. Kế Hoạch Xác Minh (Verification Plan)

### Kiểm thử tự động (Automated Verification)
1. Chạy lệnh kiểm tra lỗi cú pháp và biên dịch Python:
   ```powershell
   python -m py_compile settings.py pointcloud_processing.py main.py
   ```

### Kiểm thử thực tế (Manual Verification)
1. Khởi chạy radar theo thời gian thực:
   ```powershell
   python -u main.py
   ```
2. **Tiêu chuẩn vượt qua (Pass Criteria)**:
   * **Bám đuổi ID**: Người đứng im hoặc đi lại chậm trong vùng quét phải giữ nguyên một ID duy nhất (ví dụ liên tục là `ID 1000`), không bị nhảy mã định danh hay tách thành nhiều hộp song song.
   * **Triệt tiêu nhiễu tĩnh**: Các hộp ảo xuất hiện tại khu vực bàn ghế/tường ở tọa độ `(2.8, 4.6)` và `(-0.7, 3.7)` phải bị ẩn hoàn toàn sau đúng 15 frame (~0.75 giây) hoạt động.
   * **Độ mượt**: Không còn hiện tượng các hộp người chớp tắt (blinking) hoặc giật cục dữ dội trên đồ thị 3D.
