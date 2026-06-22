# KẾ HOẠCH TRIỂN KHAI v12.0 - BÁO CÁO PHÂN TÍCH WEBCAM: TỰ THÍCH NGHI ĐỘNG HỌC THỜI GIAN THỰC (DYNAMICS ADAPTIVE TRACKING)

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 12.0** dựa trên các so sánh trực quan từ dữ liệu video đồng bộ v11.0. Chúng tôi thiết kế **3 cơ chế tự thích nghi thông minh** nhằm khắc phục triệt để các khuyết điểm về **mất dấu khi đứng im**, **trễ phản hồi khi di chuyển** và **hoán đổi ID** mà không cần khôi phục lại giải pháp tĩnh nhân tạo.

---

## 🔍 THUẬT TOÁN TỰ THÍCH NGHI ĐỀ XUẤT TRONG VERSION 12.0

### 1. Thời gian chờ biến mất thích nghi (Adaptive Target Missing Timeout)
* **Logic hoạt động**: 
  * Thay vì áp dụng cứng nhắc `GHOST_MAX_MISSING_FRAMES = 5` cho mọi trường hợp, hệ thống tự động xác định trạng thái động học của Confirmed Target trước khi biến mất.
  * Nếu target đang di chuyển chậm/đứng im ($V_{Kalman} < 0.25\text{ m/s}$) và có độ tin cậy tích lũy cao trước đó, ta cho phép kéo dài thời gian chờ biến mất động lên `ADAPTIVE_TIMEOUT_STATIONARY_FRAMES = 35` frame (~1.75 giây).
  * Nếu là target chuyển động nhanh ($V_{Kalman} \ge 0.25\text{ m/s}$): Giữ nguyên `max_miss = 5` để triệt tiêu ghost cực nhanh khi người thực sự đi ra ngoài.
* **Mục tiêu**: Giúp hộp bám đuổi đứng im vững chắc, không nhấp nháy khi người dừng lại đứng im mà mây điểm thưa đi.

### 2. Bộ lọc làm mịn động lực thích nghi (Dynamic Adaptive Smoothing Filter)
* **Logic hoạt động**: 
  * Thay thế hằng số làm mịn cố định bằng hệ số thích nghi tuyến tính theo tốc độ di chuyển thực tế của mục tiêu ($v = \sqrt{vx^2 + vy^2 + vz^2}$):
    $$\alpha_{dynamic} = \alpha_{min} + (\alpha_{max} - \alpha_{min}) \times \min\left(1.0, \frac{v}{v_{scale}}\right)$$
    * *Đứng im hoặc đi chậm ($v \approx 0\text{ m/s}$)*: $\alpha_{dynamic} \rightarrow \alpha_{min} = 0.15$ (Độ mịn tối đa, chống rung lắc hộp tuyệt đối).
    * *Di chuyển nhanh ($v \ge 1.0\text{ m/s}$)*: $\alpha_{dynamic} \rightarrow \alpha_{max} = 0.82$ (Phản hồi siêu tốc, triệt tiêu hoàn toàn độ trễ bám đuổi so với webcam).
* **Mục tiêu**: Hộp bám đuổi dịch chuyển "dính chặt" theo cơ thể người di chuyển tức thời, không bị lết trễ.

### 3. Vùng bảo vệ phản xạ vi mô (Micro-Motion Gate & Protection Zone)
* **Logic hoạt động**: 
  * Xác lập một "Vùng bảo vệ" hình cầu bán kính `MICRO_MOTION_ZONE_RADIUS = 0.80` mét xung quanh các Confirmed Target.
  * Trong vùng này, thuật toán lọc điểm thô sẽ tự động hạ thấp ngưỡng lọc `MIN_POINT_SNR` xuống `MICRO_MOTION_MIN_SNR = 1.0` (thay vì 1.5) và chấp nhận các điểm có Doppler cực nhỏ.
* **Mục tiêu**: Nhặt lại các phản xạ cực yếu từ cử động vi mô của cơ thể (như thở, dịch chuyển đầu/tay khi đứng im) để duy trì mây điểm vật lý liên tục, giúp radar không bị mù hoàn toàn.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Bổ sung các tham số tự thích nghi mới:
```python
# ============================================================
# DYNAMICS ADAPTIVE TRACKING SETTINGS (Version 12.0)
# ============================================================
ENABLE_ADAPTIVE_TIMEOUT = True
ADAPTIVE_TIMEOUT_STATIONARY_FRAMES = 35 # Tăng thời gian chờ lên 1.75s khi đứng im

ENABLE_DYNAMIC_SMOOTHING = True
SMOOTHING_ALPHA_MIN = 0.15             # Cực kỳ mượt khi đứng im/đi chậm
SMOOTHING_ALPHA_MAX = 0.82             # Phản hồi tức thời khi chạy/đi nhanh
SMOOTHING_VELOCITY_SCALE = 1.0         # Tốc độ quy đổi đạt tối đa nhạy bén (m/s)

ENABLE_MICRO_MOTION_ZONE = True
MICRO_MOTION_ZONE_RADIUS = 0.80        # Bán kính 80cm quanh confirmed track
MICRO_MOTION_MIN_SNR = 1.0             # Giảm ngưỡng SNR để giữ điểm phản xạ thở/cử động nhẹ
```

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* Tích hợp **Micro-Motion Gate** vào hàm lọc/tạo mask điểm và điều chỉnh thời gian chờ trong `VirtualTargetTracker`:
```python
# 1) Trong hàm build_human_point_mask hoặc lọc SNR ở pointcloud_processing.py:
# Nếu ENABLE_MICRO_MOTION_ZONE = True và điểm nằm gần confirmed_positions, hạ thấp ngưỡng SNR lọc điểm.

# 2) Trong VirtualTargetTracker.track_and_build (Step 7):
for tid in list(self.active_tracks.keys()):
    if tid not in matched_tids:
        track_info = self.active_tracks[tid]
        track_info["miss_count"] += 1
        
        max_miss = GHOST_MAX_MISSING_FRAMES
        if track_info["state"] == "tentative":
            max_miss = 1
        elif track_info["state"] == "confirmed" and ENABLE_ADAPTIVE_TIMEOUT:
            # Nếu tốc độ thấp (đứng im), tăng thời gian chờ thích nghi
            k_vel = track_info["kalman"].x[3:]
            speed = np.sqrt(np.sum(k_vel**2))
            if speed < 0.25:
                max_miss = ADAPTIVE_TIMEOUT_STATIONARY_FRAMES
                
        if track_info["miss_count"] > max_miss:
            self.active_tracks.pop(tid, None)
```

### 📄 [MODIFY] [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)
* Cấu trúc lại bộ lọc làm mịn trong `GhostTargetFilter` để tính toán `alpha` động học thích nghi:
```python
# Trong GhostTargetFilter.update():
# Đo đạc tốc độ của mục tiêu hiện tại:
speed = np.sqrt(target["velX"]**2 + target["velY"]**2 + target["velZ"]**2)

if ENABLE_DYNAMIC_SMOOTHING:
    # Nội suy tuyến tính hệ số alpha thích nghi tốc độ
    alpha = SMOOTHING_ALPHA_MIN + (SMOOTHING_ALPHA_MAX - SMOOTHING_ALPHA_MIN) * min(1.0, speed / SMOOTHING_VELOCITY_SCALE)
else:
    alpha = TARGET_SMOOTHING_ALPHA

# Thực hiện làm mịn mũ (exponential smoothing) với alpha động học
smoothed_x = alpha * target["posX"] + (1 - alpha) * prev_x
# ... áp dụng tương tự cho Y, Z ...
```

---

## 🔬 KẾ HÌNH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử mô phỏng ngoại tuyến (Offline Check)
* Biên dịch kiểm tra cú pháp độc lập toàn bộ các file sửa đổi.

### 2. Kiểm thử chạy thực tế đồng bộ (Real-time Live Verification)
* Bật radar và webcam chạy song song:
  ```powershell
  python main.py
  ```
* **Tiêu chuẩn vượt qua**:
  1. Khi bạn **đứng yên hoàn toàn**, mây điểm vi mô vẫn được giữ lại một phần quanh chân/thân, và hộp Bounding Box đứng im vững vàng liên tục lên tới 1.5 - 2.0 giây mà không bị nhấp nháy biến mất.
  2. Khi bạn **bước đi đột ngột**, hộp Bounding Box lập tức bám đuổi theo sát cơ thể trên video side-by-side mà không xuất hiện độ trễ kéo dài như trước.
  3. Video phân tích ghi lại sự tương thích hoàn hảo này trong file MP4 lưu trữ mới.
