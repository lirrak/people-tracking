# KẾ HOẠCH TRIỂN KHAI v10.0 - BẢO TOÀN DỮ LIỆU RADAR VẬT LÝ, GIỮ LẠI X-FLIP VÀ SỬA CHIỀU CAO SENSOR

Tài liệu này trình bày kế hoạch nâng cấp lên **Version 10.0** nhằm **loại bỏ hoàn toàn giải pháp Stateful Static Hold và Point Cloud Memory Caching & Injection** khỏi thuật toán bám đuổi ảo. Hệ thống sẽ quay trở lại hiển thị thuần túy dữ liệu phản xạ vật thực tế thời gian thực thu được từ cảm biến (Raw Real-Time Data), nhưng vẫn **giữ lại và duy trì cấu hình sửa đổi đảo gương Trái/Phải (X-Flip)** và **điều chỉnh chiều cao đặt radar lên 1.15m** đã chạy thành công trước đó.

> [!WARNING]
> Theo yêu cầu của người dùng, **tuyệt đối không chạy hoặc thử nghiệm mã nguồn** cho đến khi kế hoạch này được xem xét và phê duyệt.

---

## 🔍 PHÂN TÍCH THUẬT TOÁN ĐỀ XUẤT TRONG VERSION 10.0

Dựa trên yêu cầu tối giản thuật toán bám đuổi phần mềm và tôn trọng tính chân thực tuyệt đối của mây điểm vật lý phản xạ trực tiếp từ chip:

### 1. Loại bỏ Stateful Static Hold & Point Cloud Caching
* **Hành vi loại bỏ**:
  * Loại bỏ thuộc tính `cached_points` (bộ nhớ mây điểm) và logic tính toán mây điểm tương đối khỏi `VirtualTargetTracker`.
  * Loại bỏ cơ chế bơm ngược (inject) mây điểm ảo vào `display_point_cloud`. Màn hình sẽ chỉ vẽ các điểm phản xạ thực tế thu được ở frame hiện tại từ radar.
  * Loại bỏ cơ chế giữ vết Static Hold kéo dài 120 frame (~6.0 giây). Hộp Bounding Box ảo sẽ tuân thủ thời gian chờ biến mất nghiêm ngặt ban đầu của bộ lọc `GHOST_MAX_MISSING_FRAMES` (mặc định 5 frame) ngay khi người đứng im làm biến mất mây điểm.
  * Loại bỏ hệ số giảm chấn vận tốc `0.85` của Kalman khi mất dấu. Kalman sẽ tiếp tục duy trì dự báo chuyển động thẳng đều (Dead Reckoning tự nhiên) trong thời gian chờ ngắn của bộ lọc mà không bị hãm phanh chủ động.

### 2. Duy trì và Giữ lại các cải tiến cốt lõi của v9.0
* **X-Flip Perspective (`FLIP_X_PERSPECTIVE = True`)**: Giữ lại giải pháp đảo dấu trục X ($X_{room} = -X_{radar}$, $velX_{room} = -velX_{radar}$) trong `transform_to_room_coordinates` và `transform_target_to_room_coordinates`. Đảm bảo góc nhìn đối diện của người dùng khớp hoàn toàn với màn hình 3D (di chuyển sang phải $\rightarrow$ box sang phải).
* **Radar Mount Height (`RADAR_MOUNT_HEIGHT_M = 1.15`)**: Giữ lại chiều cao đặt radar $1.15\text{ m}$ để đảm bảo các thuật toán xoay tọa độ quanh góc nghiêng 30 độ hoạt động chính xác tuyệt đối theo mặt phẳng sàn thực tế.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Xóa bỏ cấu hình bộ nhớ thời gian tĩnh `STATIC_HOLD_MAX_MISSING_FRAMES`:
```diff
 # ============================================================
 # RADAR INSTALLATION & COORDINATE TRANSFORMATION
 # ============================================================
 ENABLE_COORD_TRANSFORM = True
 RADAR_TILT_ANGLE_DEG = 30.0   # Góc nghiêng chĩa xuống của radar (độ)
 RADAR_MOUNT_HEIGHT_M = 1.15   # Chiều cao lắp đặt radar so với mặt đất (mét) - đã điều chỉnh theo thực tế kẹp màn hình
 FLIP_X_PERSPECTIVE = True     # Đảo trục X để đồng bộ góc nhìn đối diện (Trải nghiệm người dùng bên phải = Màn hình bên phải)
 
-# ============================================================
-# STATIC HOLD & POINT CLOUD CACHING (Version 9.0)
-# ============================================================
-STATIC_HOLD_MAX_MISSING_FRAMES = 120  # Giữ track confirmed tối đa 6.0 giây khi người đứng yên hoàn toàn
```

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* Đơn giản hóa lại lớp `VirtualTargetTracker` loại bỏ caching và giữ tĩnh:
```python
class VirtualTargetTracker:
    """
    Stateful tracker cho các target ảo sinh ra từ Point Cloud.
    Giải quyết triệt để lỗi nhảy ID ngẫu nhiên của DBSCAN, tích hợp bộ lọc 3D Kalman và quản lý trạng thái.
    """
    def __init__(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE # 1000
        self.active_tracks = {} # tid -> { "kalman": KalmanTracker3D, "state": "tentative"|"confirmed", "hit_count": int, "miss_count": int, "features": dict }
        self.last_time = None

    def reset(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE
        self.active_tracks.clear()
        self.last_time = None

    def track_and_build(self, raw_targets, point_cloud, target_index=None, frame_number=0):
        # 1) Tính toán dt thực tế giữa các frame
        current_time = time.time()
        dt = 0.05
        if self.last_time is not None:
            dt = max(0.01, min(0.20, current_time - self.last_time))
        self.last_time = current_time

        if raw_targets is None:
            raw_targets = []

        # Transform coordinates to flat room coordinates if enabled
        point_cloud = transform_to_room_coordinates(point_cloud)
        raw_targets = [transform_target_to_room_coordinates(t) for t in raw_targets]

        # Lấy danh sách vị trí confirmed tracks để bảo vệ điểm tĩnh
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

        # 2) Đánh giá và lọc target phần cứng (Firmware Targets)
        for target in raw_targets:
            target = dict(target)
            tid = target.get("tid", -1)
            tz = target.get("posZ", 0.0)

            if tz < TARGET_ROI_Z[0] or tz > TARGET_ROI_Z[1]:
                continue

            associated_points = empty_point_cloud()

            if USE_TARGET_INDEX_ASSOCIATION:
                associated_points = points_from_target_index(point_cloud, target_index, tid)
                associated_points = filter_human_roi(associated_points)
                target["targetIndexPointCount"] = int(len(associated_points))

            if len(associated_points) < GHOST_MIN_SUPPORT_POINTS:
                associated_points = points_near_target(roi_points, target)
                target["radiusSupportUsed"] = True
            else:
                target["radiusSupportUsed"] = False

            score, features = score_human_cluster(associated_points)
            target["supportPointCount"] = int(len(associated_points))
            target["humanScore"] = score
            target["clusterFeatures"] = features
            target["source"] = "firmware_target"

            if score >= HUMAN_SCORE_TARGET_THRESHOLD or len(associated_points) >= GHOST_MIN_SUPPORT_POINTS:
                final_targets.append(target)

        # 3) Dự báo trạng thái Kalman (Kalman Predict Step)
        predictions = {}
        for tid, track_info in self.active_tracks.items():
            track_info["kalman"].update_dt(dt)
            pred_pos = track_info["kalman"].predict()
            predictions[tid] = pred_pos

        # 4) Phân nhóm mây điểm ảo thành các cụm người hợp lệ
        allow_virtual_targets = ENABLE_VIRTUAL_CLUSTER_TARGETS
        if VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS and len(final_targets) > 0:
            allow_virtual_targets = False

        merged_clusters = merge_nearby_clusters(clusters)
        valid_centroids = []
        valid_scores = []
        valid_features = []
        valid_counts = []

        for cid, cluster in enumerate(merged_clusters):
            score, features = score_human_cluster(cluster)
            cluster_center = np.mean(cluster[:, 0:3], axis=0)

            cluster_debug.append({
                "cluster_id": cid,
                "point_count": int(len(cluster)),
                "score": float(score),
                "center": tuple(float(v) for v in cluster_center),
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

        # 5) Data Association dựa trên Nearest Neighbor so với Prediction
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

        # 6) Tạo mới hoặc cập nhật bộ lọc Kalman (Update Step)
        for c_idx, cc in enumerate(valid_centroids):
            score = valid_scores[c_idx]
            features = valid_features[c_idx]
            pt_count = valid_counts[c_idx]

            if c_idx in assignments:
                tid = assignments[c_idx]
                track_info = self.active_tracks[tid]
                track_info["kalman"].update(cc)
                track_info["hit_count"] += 1
                track_info["miss_count"] = 0
                track_info["score"] = score
                track_info["features"] = features
                track_info["pt_count"] = pt_count
                
                # Nâng cấp lên confirmed nếu đủ số frame tích lũy
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
                    "pt_count": pt_count
                }

        # 7) Quản lý các track bị mất tích (Dead Reckoning & Deletion)
        for tid in list(self.active_tracks.keys()):
            if tid not in matched_tids:
                track_info = self.active_tracks[tid]
                track_info["miss_count"] += 1
                
                max_miss = GHOST_MAX_MISSING_FRAMES
                if track_info["state"] == "tentative":
                    max_miss = 1  # Tentative biến mất 1 frame là xóa ngay lập tức
                
                if track_info["miss_count"] > max_miss:
                    self.active_tracks.pop(tid, None)

        # 8) Xuất danh sách Confirmed Tracks ra virtual targets chính thức
        virtual_targets = []
        for tid, track_info in self.active_tracks.items():
            if track_info["state"] != "confirmed":
                continue

            k_state = track_info["kalman"].x

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
                "kalmanTracked": True
            }

            # Lọc chống gộp trùng với target phần cứng
            too_close_to_existing = False
            for hw_target in final_targets:
                if target_xy_distance(virtual_target, hw_target) < CLUSTER_TO_TARGET_MIN_DISTANCE_XY:
                    too_close_to_existing = True
                    break

            if not too_close_to_existing:
                virtual_targets.append(virtual_target)

        # Sắp xếp và giới hạn số lượng mục tiêu ảo song song
        virtual_targets.sort(
            key=lambda t: (t.get("humanScore", 0.0), t.get("supportPointCount", 0)),
            reverse=True
        )

        final_targets.extend(virtual_targets[:VIRTUAL_CLUSTER_MAX_TARGETS])
        
        # Triệt tiêu các Ghost Target dội sóng gương qua tường
        final_targets = suppress_multipath_ghosts(final_targets)
        
        final_targets.sort(key=lambda t: t.get("tid", 0))

        display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

        return final_targets, display_point_cloud, cluster_debug
```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử mô phỏng ngoại tuyến (Offline Validation)
* Xây dựng kịch bản kiểm thử tĩnh trong `preview_tracking_v10.py`:
  * Người di chuyển sang bên phải màn hình làm việc $\rightarrow$ Kiểm tra Bounding Box hiển thị tương ứng bên phải màn hình 3D (trục X dương).
  * **Tiêu chuẩn vượt qua**:
    * Biên dịch và chạy hoàn tất mà không phát sinh lỗi cú pháp.
    * Tọa độ hiển thị của điểm và hộp không bị đảo ngược nữa.

### 2. Kiểm thử chạy thực tế (Real-time Validation)
* Cắm cảm biến và khởi chạy chương trình:
  ```powershell
  python main.py
  ```
* **Tiêu chuẩn vượt qua**:
  * Hướng di chuyển Trái / Phải trùng khớp 100% hướng cơ thể bạn.
  * Khi bạn đứng yên hoàn toàn và mây điểm biến mất, Bounding Box biến mất tự nhiên sau 5 frame theo đúng dữ liệu gốc từ radar mà không có mây điểm ảo nhân tạo.
