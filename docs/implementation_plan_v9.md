# KẾ HOẠCH TRIỂN KHAI v9.0 - STATEFUL STATIC HOLD, POINT CLOUD CACHING & ĐỒNG BỘ GÓC NHÌN X-FLIP

Tài liệu này đề xuất phương án nâng cấp hệ thống lên **Version 9.0** nhằm giải quyết triệt để 2 vấn đề lớn được phản hồi qua video/hình ảnh chạy thực tế:
1. **Lỗi mất mục tiêu và point cloud khi đứng im (Static Lost)**: Radar triệt tiêu các điểm có vận tốc Doppler bằng 0 dẫn đến người đứng im bị biến mất khỏi màn hình.
2. **Lỗi đảo ngược gương Trái/Phải (Left-Right Mirroring)**: Khi người dùng đứng bên phải màn hình thì mục tiêu hiển thị bên trái, do hệ tọa độ của radar ngược chiều góc nhìn của người dùng đối diện. Đồng thời điều chỉnh chiều cao đặt radar lên trên màn hình máy tính thực tế.

> [!WARNING]
> Theo yêu cầu của người dùng, **tuyệt đối không chạy hoặc thử nghiệm mã nguồn** cho đến khi kế hoạch này được xem xét và phê duyệt.

---

## 🔍 PHÂN TÍCH SÂU VÀ GIẢI PHÁP TRIỂN KHAI (ROOT CAUSE & DESIGN)

### 1. Hiện tượng Mất Mục Tiêu Khi Đứng Yên & Giải pháp Caching Point Cloud
* **Nguyên nhân**: FMCW Radar hoạt động dựa trên hiệu ứng Doppler. Khi người đứng im hoàn toàn, tần số Doppler dịch chuyển về $0$. Cả bộ lọc CFAR phần cứng lẫn bộ lọc Clutter động của chúng ta sẽ coi đây là vật thể tĩnh (tường/bàn ghế) và lọc bỏ hoàn toàn các điểm phản xạ này.
* **Giải pháp 1: Stateful Static Hold**:
  * Khi một Track đã được xác nhận (`Confirmed Track`) rơi vào trạng thái mất liên kết (không có cluster nào khớp), thay vì xóa ngay sau 5 frame (`GHOST_MAX_MISSING_FRAMES`), ta sẽ chuyển nó sang trạng thái **Tạm giữ tĩnh (Static Hold)**.
  * Trong trạng thái Static Hold, ta cho phép giữ Track sống lâu hơn rất nhiều (mặc định **120 frame ~ 6.0 giây** `STATIC_HOLD_MAX_MISSING_FRAMES`).
  * Đồng thời, ta thực hiện **Dead Reckoning Deceleration**: Ở mỗi frame bị mất, ta nhân vận tốc ước lượng từ Kalman với hệ số giảm chấn `0.85` (giảm 15% mỗi frame). Vận tốc mục tiêu sẽ nhanh chóng tiệm cận về đúng $0.0\text{ m/s}$, giữ chiếc hộp Bounding Box khóa chặt tại vị trí người đứng im.
* **Giải pháp 2: Point Cloud Memory Caching & Injection**:
  * Mỗi Track sẽ duy trì một bộ đệm lưu vết các điểm phản xạ tương đối của nó ở frame hoạt động gần nhất (`relative_points = absolute_points - centroid`).
  * Nếu Track bị mất dấu (khi người đứng im và radar không trả điểm), ta sẽ sử dụng bộ đệm này để tái tạo lại mây điểm ảo dựa trên tọa độ dự báo hiện tại của Kalman:
    $$\text{Points}_{abs} = \text{Points}_{relative} + \mathbf{x}_{Kalman}$$
  * Bơm ngược (inject) mây điểm ảo này vào bộ đệm `display_point_cloud` gửi ra visualizer. Kết quả là mây điểm của người đứng im sẽ liên tục hiển thị sáng rõ quanh Bounding Box ngay cả khi radar bị mù!

### 2. Hiện tượng Đảo Gương Trái/Phải & Chiều cao cảm biến thực tế
* **Nguyên nhân 1 (Đảo gương)**: Khi người dùng đối diện màn hình, bên phải của người dùng chính là bên trái của radar (X âm). Do đó, khi bạn đứng bên phải, tọa độ radar đo được là $X < 0$ và hiển thị bên trái cửa sổ 3D.
* **Giải pháp 1 (X-Flip)**: Thêm hằng số cấu hình `FLIP_X_PERSPECTIVE = True` trong `settings.py`. Khi kích hoạt, hàm biến đổi tọa độ `transform_to_room_coordinates` và `transform_target_to_room_coordinates` sẽ tự động đảo ngược trục X:
  $$X_{room} = -X_{radar}$$
  $$velX_{room} = -velX_{radar}$$
  Điều này đồng bộ hoàn hảo 100% góc nhìn thực tế: Bạn đứng bên phải, box đi theo bên phải!
* **Nguyên nhân 2 (Chiều cao đặt radar)**: radar được kẹp trên nóc màn hình máy tính (như hình ảnh thực tế bạn gửi). Chiều cao chuẩn từ mặt đất đến nóc màn hình trên bàn làm việc dao động từ $1.10\text{ m} \rightarrow 1.20\text{ m}$. Tuy nhiên cấu hình cũ đang để `0.60 m` (quá thấp).
* **Giải pháp 2**: Thay đổi mặc định `RADAR_MOUNT_HEIGHT_M = 1.15` trong `settings.py` để phép quay tọa độ Z-Limit chính xác tuyệt đối, tránh hiện tượng người bị chìm dưới sàn nhà ảo.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Cập nhật chiều cao, kích hoạt lật trục X và cấu hình bộ nhớ thời gian tĩnh:
```diff
 # ============================================================
 # RADAR INSTALLATION & COORDINATE TRANSFORMATION
 # ============================================================
 ENABLE_COORD_TRANSFORM = True
 RADAR_TILT_ANGLE_DEG = 30.0   # Góc nghiêng chĩa xuống của radar (độ)
-RADAR_MOUNT_HEIGHT_M = 0.60   # Chiều cao lắp đặt radar so với mặt đất (mét)
+RADAR_MOUNT_HEIGHT_M = 1.15   # Điều chỉnh lên 1.15m (radar đặt trên nóc màn hình máy tính thực tế)
+
+FLIP_X_PERSPECTIVE = True     # Đảo trục X để đồng bộ góc nhìn đối diện (Trải nghiệm người dùng bên phải = Màn hình bên phải)
 
+# ============================================================
+# STATIC HOLD & POINT CLOUD CACHING (Version 9.0)
+# ============================================================
+STATIC_HOLD_MAX_MISSING_FRAMES = 120  # Giữ track confirmed tối đa 6.0 giây khi người đứng yên hoàn toàn
```

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

#### 1. Cập nhật `transform_to_room_coordinates` đảo ngược trục X:
```python
def transform_to_room_coordinates(points):
    """Transform radar points to flat room coordinates if enabled."""
    if not (ENABLE_COORD_TRANSFORM if 'ENABLE_COORD_TRANSFORM' in globals() else False):
        return points
    
    points = ensure_point_cloud_shape(points)
    if len(points) == 0:
        return points
        
    theta_deg = RADAR_TILT_ANGLE_DEG if 'RADAR_TILT_ANGLE_DEG' in globals() else 30.0
    h = RADAR_MOUNT_HEIGHT_M if 'RADAR_MOUNT_HEIGHT_M' in globals() else 0.60
    theta = np.radians(theta_deg)
    
    transformed = points.copy()
    y_radar = points[:, 1]
    z_radar = points[:, 2]
    
    # Tự động đảo ngược trục X nếu cấu hình FLIP_X_PERSPECTIVE = True
    if FLIP_X_PERSPECTIVE if 'FLIP_X_PERSPECTIVE' in globals() else False:
        transformed[:, 0] = -points[:, 0]
    
    # Rotation around X-axis (pitch) and translation along Z (mount height)
    transformed[:, 1] = y_radar * np.cos(theta) - z_radar * np.sin(theta)
    transformed[:, 2] = y_radar * np.sin(theta) + z_radar * np.cos(theta) + h
    
    return transformed
```

#### 2. Cập nhật `transform_target_to_room_coordinates` đảo ngược trục X mục tiêu:
```python
def transform_target_to_room_coordinates(target):
    """Transform a firmware target's coordinates to room coordinates."""
    if not (ENABLE_COORD_TRANSFORM if 'ENABLE_COORD_TRANSFORM' in globals() else False):
        return target
        
    theta_deg = RADAR_TILT_ANGLE_DEG if 'RADAR_TILT_ANGLE_DEG' in globals() else 30.0
    h = RADAR_MOUNT_HEIGHT_M if 'RADAR_MOUNT_HEIGHT_M' in globals() else 0.60
    theta = np.radians(theta_deg)
    
    transformed = dict(target)
    
    # Tự động đảo ngược trục X của mục tiêu và vận tốc, gia tốc tương ứng
    if FLIP_X_PERSPECTIVE if 'FLIP_X_PERSPECTIVE' in globals() else False:
        transformed["posX"] = -target.get("posX", 0.0)
        transformed["velX"] = -target.get("velX", 0.0)
        transformed["accX"] = -target.get("accX", 0.0)
        
    y_radar = target.get("posY", 0.0)
    z_radar = target.get("posZ", 0.0)
    
    transformed["posY"] = float(y_radar * np.cos(theta) - z_radar * np.sin(theta))
    transformed["posZ"] = float(y_radar * np.sin(theta) + z_radar * np.cos(theta) + h)
    
    return transformed
```

#### 3. Nâng cấp `VirtualTargetTracker` tích hợp bộ đệm mây điểm `cached_points` và giảm chấn vận tốc tĩnh:
```python
class VirtualTargetTracker:
    """
    Stateful tracker cho các target ảo sinh ra từ Point Cloud.
    Giải quyết triệt để lỗi nhảy ID ngẫu nhiên của DBSCAN, tích hợp bộ lọc 3D Kalman, Static Hold và Caching.
    """
    def __init__(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE # 1000
        self.active_tracks = {} # tid -> { "kalman": KalmanTracker3D, "state", "hit_count", "miss_count", "cached_points", ... }
        self.last_time = None

    def reset(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE
        self.active_tracks.clear()
        self.last_time = None

    def track_and_build(self, raw_targets, point_cloud, target_index=None, frame_number=0):
        current_time = time.time()
        dt = 0.05
        if self.last_time is not None:
            dt = max(0.01, min(0.20, current_time - self.last_time))
        self.last_time = current_time

        if raw_targets is None:
            raw_targets = []

        point_cloud = transform_to_room_coordinates(point_cloud)
        raw_targets = [transform_target_to_room_coordinates(t) for t in raw_targets]

        confirmed_positions = [
            track_info["kalman"].x[:2] 
            for track_info in self.active_tracks.values() 
            if track_info["state"] == "confirmed"
        ]

        point_cloud = ensure_point_cloud_shape(point_cloud)
        roi_mask = build_human_point_mask(point_cloud, confirmed_positions)
        roi_points = point_cloud[roi_mask]
        clusters = cluster_pointcloud(roi_points)

        final_targets = []
        cluster_debug = []

        # (Logic Firmware Targets giữ nguyên)
        # ...

        # 3) Dự báo trạng thái Kalman
        predictions = {}
        for tid, track_info in self.active_tracks.items():
            track_info["kalman"].update_dt(dt)
            pred_pos = track_info["kalman"].predict()
            predictions[tid] = pred_pos

        allow_virtual_targets = ENABLE_VIRTUAL_CLUSTER_TARGETS
        if VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS and len(final_targets) > 0:
            allow_virtual_targets = False

        merged_clusters = merge_nearby_clusters(clusters)
        valid_centroids = []
        valid_scores = []
        valid_features = []
        valid_counts = []
        valid_clusters = []

        for cid, cluster in enumerate(merged_clusters):
            score, features = score_human_cluster(cluster)
            cluster_center = np.mean(cluster[:, 0:3], axis=0)

            cluster_debug.append({
                "cluster_id": cid,
                "point_count": len(cluster),
                "score": score,
                "center": tuple(cluster_center),
                "features": features,
                "merged": True,
            })

            if not allow_virtual_targets:
                continue
            if len(cluster) < VIRTUAL_CLUSTER_MIN_POINTS:
                continue
            if not features.get("is_shape_valid", False):
                continue
            if score < VIRTUAL_CLUSTER_SCORE_THRESHOLD:
                continue

            valid_centroids.append(cluster_center)
            valid_scores.append(score)
            valid_features.append(features)
            valid_counts.append(len(cluster))
            valid_clusters.append(cluster)

        # 5) Data Association
        matched_cluster_indices = set()
        matched_tids = set()
        assignments = {}

        if self.active_tracks and valid_centroids:
            pairs = []
            for c_idx, cc in enumerate(valid_centroids):
                for tid, pred_pos in predictions.items():
                    dist_xy = float(np.sqrt((cc[0] - pred_pos[0])**2 + (cc[1] - pred_pos[1])**2))
                    pairs.append((dist_xy, c_idx, tid))
            
            pairs.sort(key=lambda x: x[0])
            assoc_radius = VIRTUAL_TRACKER_ASSOCIATION_RADIUS
            
            for dist_xy, c_idx, tid in pairs:
                if c_idx not in matched_cluster_indices and tid not in matched_tids:
                    if dist_xy <= assoc_radius:
                        matched_cluster_indices.add(c_idx)
                        matched_tids.add(tid)
                        assignments[c_idx] = tid

        # 6) Tạo mới hoặc cập nhật bộ lọc Kalman + Caching Point Cloud
        for c_idx, cc in enumerate(valid_centroids):
            score = valid_scores[c_idx]
            features = valid_features[c_idx]
            pt_count = valid_counts[c_idx]
            cluster_pts = valid_clusters[c_idx]

            # Tính toán mây điểm tương đối so với tâm để lưu vết
            relative_pts = cluster_pts.copy()
            relative_pts[:, 0:3] = cluster_pts[:, 0:3] - cc[0:3]

            if c_idx in assignments:
                tid = assignments[c_idx]
                track_info = self.active_tracks[tid]
                track_info["kalman"].update(cc)
                track_info["hit_count"] += 1
                track_info["miss_count"] = 0
                track_info["score"] = score
                track_info["features"] = features
                track_info["pt_count"] = pt_count
                track_info["cached_points"] = relative_pts  # Lưu bộ đệm mây điểm mới nhất
                
                if track_info["state"] == "tentative" and track_info["hit_count"] >= TARGET_CONFIRM_FRAMES:
                    track_info["state"] = "confirmed"
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
                    "cached_points": relative_pts
                }

        # 7) Quản lý các track bị mất tích (Dead Reckoning, Static Hold & Deletion)
        for tid in list(self.active_tracks.keys()):
            if tid not in matched_tids:
                track_info = self.active_tracks[tid]
                track_info["miss_count"] += 1
                
                # Giảm chấn vận tốc động học (Velocity Deceleration) khi mất dấu để hộp đứng im
                track_info["kalman"].x[3:] *= 0.85
                
                max_miss = GHOST_MAX_MISSING_FRAMES
                if track_info["state"] == "tentative":
                    max_miss = 1
                elif track_info["state"] == "confirmed":
                    # Kéo dài tuổi thọ của confirmed track khi đứng im (Static Hold)
                    max_miss = STATIC_HOLD_MAX_MISSING_FRAMES if 'STATIC_HOLD_MAX_MISSING_FRAMES' in globals() else 120
                
                if track_info["miss_count"] > max_miss:
                    self.active_tracks.pop(tid, None)

        # 8) Xuất danh sách Confirmed Tracks
        virtual_targets = []
        injected_points_list = [roi_points]

        for tid, track_info in self.active_tracks.items():
            if track_info["state"] != "confirmed":
                continue

            k_state = track_info["kalman"].x
            
            # Tái tạo mây điểm ảo từ bộ nhớ nếu track đang ở trạng thái Static Hold (mất tích)
            is_missing = tid not in matched_tids
            if is_missing and "cached_points" in track_info and len(track_info["cached_points"]) > 0:
                abs_pts = track_info["cached_points"].copy()
                abs_pts[:, 0:3] = track_info["cached_points"][:, 0:3] + k_state[0:3]
                injected_points_list.append(abs_pts)

            virtual_target = {
                "tid": int(tid),
                "posX": float(k_state[0]),
                "posY": float(k_state[1]),
                "posZ": float(k_state[2]),
                "velX": float(k_state[3]),
                "velY": float(k_state[4]),
                "velZ": float(k_state[5]),
                "accX": 0.0,
                "accY": 0.0,
                "accZ": 0.0,
                "isVirtual": True,
                "source": "cluster",
                "supportPointCount": int(track_info["pt_count"]),
                "humanScore": float(track_info["score"]),
                "clusterFeatures": track_info["features"],
                "kalmanTracked": True,
                "staticHold": is_missing
            }

            too_close_to_existing = False
            for hw_target in final_targets:
                if target_xy_distance(virtual_target, hw_target) < CLUSTER_TO_TARGET_MIN_DISTANCE_XY:
                    too_close_to_existing = True
                    break

            if not too_close_to_existing:
                virtual_targets.append(virtual_target)

        # Gộp các mây điểm ảo được tái tạo vào display cloud gửi ra ngoài
        if len(injected_points_list) > 1:
            roi_points = np.vstack(injected_points_list)

        virtual_targets.sort(
            key=lambda t: (t.get("humanScore", 0.0), t.get("supportPointCount", 0)),
            reverse=True
        )

        final_targets.extend(virtual_targets[:VIRTUAL_CLUSTER_MAX_TARGETS])
        final_targets = suppress_multipath_ghosts(final_targets)
        final_targets.sort(key=lambda t: t.get("tid", 0))

        display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

        return final_targets, display_point_cloud, cluster_debug
```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử mô phỏng ngoại tuyến (Offline Validation)
* Xây dựng kịch bản kiểm thử tĩnh trong `preview_tracking_v9.py`:
  * Người di chuyển từ cự ly $2.0\text{m}$ đến $3.0\text{m}$, sau đó đứng im hoàn toàn. Mây điểm thô bị giảm dần từ 20 điểm về 0 điểm.
  * **Tiêu chuẩn vượt qua**:
    * Trong suốt quá trình đứng yên (trong vòng 6.0 giây), hộp Bounding Box phải được khóa chặt ở đúng tọa độ cuối cùng, vận tốc hội tụ về 0.
    * Mây điểm ảo lưu đệm của người phải được vẽ sáng rõ liên tục xung quanh hộp mục tiêu dù radar không trả điểm.
    * Khi người di chuyển sang bên phải màn hình làm việc, tọa độ hiển thị trên GUI 3D bắt buộc phải đi theo trục X dương (bên phải).

### 2. Kiểm thử chạy thực tế (Real-time Validation)
* Cắm cảm biến và khởi chạy chương trình:
  ```powershell
  python main.py
  ```
* **Tiêu chuẩn vượt qua**:
  * Khi đứng trước camera/radar và dịch chuyển sang phải/trái, hộp box di chuyển đồng bộ hoàn toàn theo chiều cơ thể bạn.
  * Khi bạn dừng và đứng yên hoàn toàn, hộp Bounding Box và mây điểm đệm vẫn hiển thị cố định sáng rõ trên GUI trong suốt 6 giây tiếp theo, không bị biến mất lập tức.
