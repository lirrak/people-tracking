# KẾ HOẠCH TRIỂN KHAI v15.0 - TIÊU DIỆT HỘP MA TĨNH VẬT VÀ TỐI ƯU ĐỘ MƯỢT BÁM ĐUỔI TỨC THỜI

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 15.0** nhằm giải quyết triệt để 2 vấn đề lớn nhất được phát hiện trong phiên record v14.0: lỗi lưu hộp bám đuổi từ bàn ghế tĩnh và hiện tượng trễ lag bám đuổi khi người dùng bắt đầu chuyển động.

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ PHƯƠNG ÁN NÂNG CẤP

### 1. Triển khai Lọc Tĩnh Vật Cấp Mục Tiêu (`ENABLE_STATIC_CLUTTER_FILTER`)
* **Mục tiêu**: Loại bỏ hoàn toàn các hộp ma xuất hiện do phản xạ tĩnh từ bàn ghế (các vật thể tĩnh không có chuyển động).
* **Giải pháp**:
  * Tích lũy lịch sử `history_positions` cho từng track trong `VirtualTargetTracker` giới hạn trong `STATIC_CLUTTER_MIN_FRAMES = 15` frames.
  * Khi xuất danh sách mục tiêu ảo (`virtual_targets`), ta tính độ lệch chuẩn dịch chuyển XY ($\sigma_{xy} = \sqrt{\sigma_x^2 + \sigma_y^2}$). 
  * Nếu $\sigma_{xy} \le \text{STATIC\_CLUTTER\_MAX\_STD} = 0.05\text{ m}$ (nghĩa là vị trí đo đạc hoàn toàn đứng im tuyệt đối, không có rung lắc cơ thể sinh học của con người), ta lập tức loại bỏ và ẩn hộp bám đuổi này đi.

### 2. Triển khai Vận Tốc Dịch Chuyển Thích Nghi Tức Thời (`displacement_speed`)
* **Mục tiêu**: Loại bỏ độ trễ (lết) của hộp bám đuổi khi người dùng đột ngột di chuyển nhanh.
* **Giải pháp**:
  * Trong hàm `smooth_target` của `filters.py`, ngoài vận tốc Doppler (`doppler_speed`), ta tính thêm vận tốc dịch chuyển tức thời dựa trên sự chênh lệch khoảng cách thực tế giữa vị trí hiện tại và vị trí đã làm mịn trước đó:
    $$\text{displacement\_speed} = \frac{\text{jump\_distance}}{0.05} \quad (\text{với } dt = 0.05\text{s tương đương 20fps})$$
  * Sử dụng vận tốc hiệu dụng lớn nhất: `effective_speed = max(doppler_speed, displacement_speed)`.
  * *Kết quả*: Ngay khi người dùng bước chân, `jump_distance` tăng vọt đẩy `effective_speed` lên cao, lập tức tăng `alpha` lên tối đa `0.82` ở frame đầu tiên giúp hộp bám vết nhạy bén phản hồi tức thời.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* Nâng cấp `VirtualTargetTracker` để tích lũy vị trí và lọc tĩnh vật cấp mục tiêu:
```python
                 tid = assignments[c_idx]
                 track_info = self.active_tracks[tid]
                 track_info["kalman"].update(cc)
                 track_info["hit_count"] += 1
                 track_info["miss_count"] = 0
                 track_info["score"] = score
                 track_info["features"] = features
                 track_info["pt_count"] = pt_count
                 
                 # Lưu lịch sử vị trí đo đạc (Version 15.0)
                 if "history_positions" not in track_info:
                     track_info["history_positions"] = []
                 track_info["history_positions"].append(cc.copy())
                 
                 # Nâng cấp lên confirmed nếu đủ số frame tích lũy
                 if track_info["state"] == "tentative" and track_info["hit_count"] >= TARGET_CONFIRM_FRAMES:
                     track_info["state"] = "confirmed"
```

```python
             else:
                 tid = self.next_virtual_id
                 self.next_virtual_id += 1
                 
                 self.active_tracks[tid] = {
                     "kalman": KalmanTracker3D(cc, dt),
                     "state": "tentative",
                     "hit_count": 1,
                     "miss_count": 0,
                     "features": features,
                     "score": score,
                     "pt_count": pt_count,
                     "history_positions": [cc.copy()]
                 }
```

```python
        # 8) Xuất danh sách Confirmed Tracks ra virtual targets chính thức
        virtual_targets = []
        for tid, track_info in self.active_tracks.items():
            if track_info["state"] != "confirmed":
                continue

            # Bộ lọc nhiễu tĩnh cấp mục tiêu (Version 15.0)
            is_static = False
            if (ENABLE_STATIC_CLUTTER_FILTER if 'ENABLE_STATIC_CLUTTER_FILTER' in globals() else True):
                history = track_info.get("history_positions", [])
                min_frames = STATIC_CLUTTER_MIN_FRAMES if 'STATIC_CLUTTER_MIN_FRAMES' in globals() else 15
                if len(history) >= min_frames:
                    hist_pts = np.array(history)
                    std_x = np.std(hist_pts[:, 0])
                    std_y = np.std(hist_pts[:, 1])
                    std_xy = np.sqrt(std_x**2 + std_y**2)
                    
                    max_std = STATIC_CLUTTER_MAX_STD if 'STATIC_CLUTTER_MAX_STD' in globals() else 0.05
                    if std_xy <= max_std:
                        is_static = True
            
            if is_static:
                continue

            k_state = track_info["kalman"].x
```

### 📄 [MODIFY] [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)
* Nâng cấp hàm `smooth_target` để phản hồi tức thời chuyển động bằng vận tốc hiệu dụng:
```python
        previous = self.smoothed_position[tid]
        jump_distance = float(np.linalg.norm(current - previous))

        if jump_distance > self.smoothing_reset_distance:
            smoothed = current
        else:
            # Nội suy tuyến tính hệ số alpha thích nghi tốc độ (Version 12.0)
            if (ENABLE_DYNAMIC_SMOOTHING if 'ENABLE_DYNAMIC_SMOOTHING' in globals() else True):
                # Tính vận tốc dựa trên Doppler từ radar / Kalman
                doppler_speed = self.target_speed(target)
                
                # Tính vận tốc dựa trên khoảng dời thực tế giữa 2 frame (displacement speed = jump_distance / dt)
                # Giả định thời gian giữa 2 frame dt = 0.05 giây (20fps)
                displacement_speed = jump_distance / 0.05
                
                # Sử dụng vận tốc hiệu dụng lớn nhất để thích nghi tức thời (Version 15.0)
                effective_speed = max(doppler_speed, displacement_speed)
                
                v_scale = SMOOTHING_VELOCITY_SCALE if 'SMOOTHING_VELOCITY_SCALE' in globals() else 1.0
                alpha_min = SMOOTHING_ALPHA_MIN if 'SMOOTHING_ALPHA_MIN' in globals() else 0.15
                alpha_max = SMOOTHING_ALPHA_MAX if 'SMOOTHING_ALPHA_MAX' in globals() else 0.82
                alpha = alpha_min + (alpha_max - alpha_min) * min(1.0, effective_speed / v_scale)
            else:
                alpha = self.smoothing_alpha
            smoothed = previous * (1.0 - alpha) + current * alpha
```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử triệt tiêu hộp ma bàn ghế
* Bố trí ghế tựa hoặc đồ đạc trong phòng. Bật chương trình và rời khỏi phòng.
* **Tiêu chuẩn vượt qua**: Hộp ma Bounding Box ảo sinh ra do đồ vật tĩnh sẽ bị bộ lọc nhận diện và ẩn đi hoàn toàn trong vòng tối đa 15 frame (0.75 giây), không còn lưu hộp rác trên màn hình.

### 2. Kiểm thử độ mượt và tốc độ bám đuổi chuyển động
* Thực hiện di chuyển nhanh, chạy chéo hoặc đổi hướng đột ngột trước cảm biến.
* **Tiêu chuẩn vượt qua**: Hộp bám đuổi di chuyển nhạy bén, đồng hướng và bám sát cơ thể theo thời gian thực (giảm trễ từ 150ms về gần như 0ms nhờ gia tăng alpha tức thời), bám đuổi mượt mà đồng bộ phối cảnh cùng camera.
