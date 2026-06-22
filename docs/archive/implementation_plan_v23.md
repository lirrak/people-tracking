# KẾ HOẠCH TRIỂN KHAI v23.0 - TRUST-BASED ADAPTIVE SPATIAL PROTECTION GATE (CỔNG BẢO VỆ THÍCH NGHI THEO ĐỘ TIN CẬY & DỰA TRÊN LỊCH SỬ ĐỘNG HỌC)

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 23.0** nhằm giải quyết triệt để lỗi khóa cứng hộp bóng ma phần cứng (`firmware_target`) và bóng ma ảo (`virtual_target`) khi không có người trong phòng. Giải pháp kết hợp phân tích vi động thô trước khi lọc và lưu vết lịch sử vận tốc để phá vỡ hoàn toàn vòng lặp phản hồi ngược khóa cứng (infinite feedback loop).

---

## 🔍 PHÂN TÍCH BẢN CHẤT LỖI PHẢN HỒI NGƯỢC (FEEDBACK LOOP CORE CAUSE)

Qua phân tích chi tiết v22.0, lý do giải pháp v22.0 vẫn gặp hiện tượng khóa cứng vô hạn các hộp ma tĩnh (như ID 1) sát tường/bàn ghế là vì **vòng lặp phản hồi ngược tự bảo vệ**:

```
[Mục tiêu phần cứng/phần mềm có speed = 0] 
                 │
                 ▼ Bán kính mặc định R = 0.45m
[Tạo Protection Gate quanh tâm bàn/ghế]
                 │
                 ▼ Point-level filter bảo vệ
[Giữ lại toàn bộ các điểm phản xạ tĩnh của bàn/ghế]
                 │
                 ▼ Gom cụm DBSCAN & Association
[Tạo support_points cao > 30 điểm]
                 │
                 ▼ GhostTargetFilter.update
[Hệ thống kiểm tra is_confident_human]
                 │
                 ▼ support_points > 6 làm tắt điều kiện lọc tĩnh vật
[Bỏ qua bộ lọc tĩnh vật & Hiển thị hộp ma]
                 │
                 ▼ (Vòng tiếp theo: Lặp lại vô hạn)
[Mục tiêu tiếp tục bảo vệ chính mình]
```

Khi radar khóa vào chiếc ghế kim loại:
1. `track_and_build` tự động đưa vị trí chiếc ghế vào `confirmed_positions` với `r_prot = 0.45m`.
2. Do nằm trong bán kính bảo vệ $0.45\text{ m}$ xung quanh tâm ghế, tất cả các điểm phản xạ tĩnh cực mạnh của chiếc ghế **không bị lọc bỏ**.
3. Các điểm này được liên kết, tạo ra `supportPointCount` rất lớn (ví dụ 30 điểm).
4. Trong `GhostTargetFilter`, điều kiện bảo vệ người đứng im:
   `is_confident_human = (target.get("humanScore", 0.0) > 40.0) or (target.get("supportPointCount", 0) > 6)`
   Bị kích hoạt do `supportPointCount = 30 > 6`, nên hệ thống coi chiếc ghế là con người đáng tin cậy đứng im!
5. Hệ thống hiển thị hộp và tiếp tục duy trì trạng thái `confirmed` của target, bảo vệ các điểm tĩnh của nó ở frame tiếp theo $\rightarrow$ **Khóa cứng vĩnh viễn!**

---

## 💡 GIẢI PHÁP ĐỀ XUẤT TRONG VERSION 23.0

Để phá vỡ hoàn toàn vòng lặp phản hồi ngược này, chúng tôi đề xuất 3 cơ chế kết hợp đồng bộ:

### 1. Phân tích Vi động Thô trước khi Lọc (Pre-Association Doppler Variance Check)
* **Logic**: Trước khi lọc mây điểm tĩnh, chúng ta trích xuất một mây điểm thô hình cầu (bán kính $0.6\text{ m}$) xung quanh tọa độ của mục tiêu từ **mây điểm thô ban đầu (chưa lọc)** và tính độ lệch chuẩn Doppler `dop_std`.
* Nếu là con người đang thở/cử động nhẹ, `dop_std` thô sẽ nằm trong dải $[0.012, 0.10]$.
* Nếu là bàn ghế tĩnh vật, `dop_std` thô sẽ tiệm cận $0.0$ tuyệt đối.

### 2. Kiểm tra Lịch sử Di chuyển gần đây (Recent Motion History Verification)
* Con người thật phải di chuyển vào phòng trước khi đứng im. Bàn ghế tĩnh vật sẽ có vận tốc và lịch sử vận tốc bằng $0.0$ kể từ lúc khởi tạo.
* Chúng ta duy trì bộ nhớ đệm `speed_history` giới hạn trong 30 frame gần nhất (~1.5 giây).
* **Định nghĩa tin cậy (Trust State)**: Một mục tiêu tĩnh (`speed < 0.12`) chỉ được phép mở cổng bảo vệ và duy trì box hiển thị nếu nó thỏa mãn ít nhất một trong hai điều kiện:
  1. Có vi động thở rõ ràng từ mây điểm thô: `has_micro_motion = True`.
  2. Vừa mới di chuyển rồi dừng lại: `max_speed_recent >= 0.15 m/s`.
* Nếu không thỏa mãn cả hai, cổng bảo vệ sẽ đóng (`r_prot = 0.0`), quét sạch điểm tĩnh vật của bàn ghế, đưa `supportPointCount` về 0 và xóa bỏ hộp ma ngay lập tức!

### 3. Phạt nặng Cụm Tĩnh vật trong Hàm tính Điểm Con người (Score Penalty)
* Cải tiến hàm `score_human_cluster`: Nếu một cụm có tốc độ trung bình và biến thiên Doppler cực nhỏ (`avg_motion < 0.005` và `doppler_std < 0.005`), điểm số sẽ bị **nhân hệ số phạt 0.3** (giảm 70% điểm số). Điều này kéo `humanScore` của bàn ghế xuống cực thấp (thường $< 20.0$), loại bỏ hoàn toàn khả năng vượt qua ngưỡng tin cậy `humanScore > 40.0`.
* Loại bỏ điều kiện lỗi thời `supportPointCount > 6` trong `GhostTargetFilter`. Số lượng điểm không phản ánh độ tin cậy của con người nếu cụm đó hoàn toàn không có vi động hay chuyển động.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

#### 1. Thêm hàm hỗ trợ `check_raw_micro_motion`
Tích hợp hàm kiểm tra vi động thô xung quanh một tọa độ:
```python
def check_raw_micro_motion(pos, point_cloud, radius=0.6, min_points=3):
    """
    Kiểm tra xem mây điểm thô xung quanh vị trí có vi động (nhịp thở/cử động) hay không.
    Sử dụng mây điểm thô trước khi lọc tĩnh vật để tránh hiện tượng vòng lặp feedback.
    """
    if point_cloud is None or len(point_cloud) == 0:
        return False
    
    x = point_cloud[:, 0]
    y = point_cloud[:, 1]
    dx = x - pos[0]
    dy = y - pos[1]
    dist_xy = np.sqrt(dx**2 + dy**2)
    
    nearby_points = point_cloud[dist_xy <= radius]
    if len(nearby_points) < min_points:
        return False
        
    dopplers = nearby_points[:, 3]
    dop_std = float(np.std(dopplers))
    
    return 0.012 <= dop_std <= 0.10
```

#### 2. Cấu trúc lại `VirtualTargetTracker` để theo dõi lịch sử vận tốc
* Bổ sung `self.hw_speed_history = {}` trong hàm `__init__`.
* Trong `track_and_build()`, cập nhật lịch sử vận tốc cho cả virtual targets (trong `track_info["speed_history"]`) và hardware targets (trong `self.hw_speed_history[tid]`).
* Áp dụng cổng bảo vệ thích nghi độ tin cậy:
  ```python
  # Lấy confirmed tracks với cổng bảo vệ thích nghi độ tin cậy
  confirmed_positions = []
  for tid, track_info in self.active_tracks.items():
      if track_info["state"] == "confirmed":
          k_state = track_info["kalman"].x
          speed = np.sqrt(k_state[3]**2 + k_state[4]**2 + k_state[5]**2)
          
          speed_hist = track_info.get("speed_history", [])
          max_speed_recent = max(speed_hist) if speed_hist else speed
          
          pos = k_state[:2]
          if speed >= 0.12:
              r_prot = 0.85
          else:
              has_micro_motion = check_raw_micro_motion(pos, point_cloud)
              has_moved_recent = max_speed_recent >= 0.15
              r_prot = 0.45 if (has_micro_motion or has_moved_recent) else 0.0
          
          if r_prot > 0.0:
              confirmed_positions.append((pos, r_prot))
  ```
  *(Áp dụng logic tương tự cho phần cứng raw_targets)*.

#### 3. Bổ sung hình phạt tĩnh vật trong `score_human_cluster`
```python
    avg_motion = float(np.mean(np.abs(doppler))) if point_count > 0 else 0.0
    doppler_std = float(np.std(doppler)) if point_count > 0 else 0.0

    # ... các logic tính score hình học cũ giữ nguyên ...

    # Phạt nặng các cụm tĩnh vật tuyệt đối không có vi động (như bàn ghế kim loại) (Version 23.0)
    if avg_motion < 0.005 and doppler_std < 0.005:
        score *= 0.3
```

### 📄 [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)

#### 1. Nâng cấp `GhostTargetFilter` để theo dõi lịch sử vận tốc và sửa lỗi `is_confident_human`
* Thêm `self.max_speed_history = {}` để theo dõi vận tốc cao nhất của từng target ID từ lúc sinh ra.
* Sửa logic kiểm tra `is_confident_human` trong `update()`:
  ```python
  # Bỏ qua lọc tĩnh vật nếu đây là người thật dựa trên vi động thở hoặc lịch sử di chuyển (Version 23.0)
  is_breathing = (0.015 <= dop_std <= 0.10)
  
  current_speed = self.target_speed(target)
  self.max_speed_history[tid] = max(self.max_speed_history.get(tid, 0.0), current_speed)
  has_moved = self.max_speed_history[tid] >= 0.20
  
  is_confident_score = (target.get("humanScore", 0.0) > 40.0)
  is_human_presence = is_breathing or (has_moved and is_confident_score)
  
  if not is_human_presence:
      is_static = True
  ```
* Bổ sung cơ chế dọn dẹp bộ nhớ đệm `self.max_speed_history` khi target bị xóa khỏi hệ thống.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Xác minh triệt tiêu hộp ma tĩnh vật
* Khởi động chương trình khi không có người trong phòng.
* **Tiêu chuẩn vượt qua**: Hộp bám vết phần cứng ID 1 (hoặc bất kỳ hộp ma nào) tại bàn ghế, tường **không được phép xuất hiện** hoặc nếu xuất hiện nhất thời sẽ biến mất hoàn toàn trong vòng dưới 1.5 giây.

### 2. Xác minh duy trì bám vết khi đứng im
* Một người thật bước vào phòng, đứng im hoàn toàn trước radar trong 60 giây.
* **Tiêu chuẩn vượt qua**: Hộp bám vết duy trì confirmed 100% thời gian, không nhấp nháy, không bị ẩn do bộ lọc tĩnh vật nhờ cơ chế phát hiện vi động thở thô và lịch sử di chuyển.

### 3. Xác minh xóa hộp khi người rời phòng
* Sau khi đứng im, người di chuyển nhanh ra ngoài phòng quét.
* **Tiêu chuẩn vượt qua**: Hộp bám vết cũ biến mất hoàn toàn sau 1.5 giây, không bị khóa cứng lại tại bất kỳ đồ vật kim loại hay vách tường lân cận nào.
