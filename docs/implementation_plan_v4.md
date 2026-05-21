# Kế Hoạch Triển Khai Giải Quyết Lỗi Nhận Diện Loạn & Lọc Nhiễu Radar IWR6843AOP (Version 4)

Tài liệu này phân tích chi tiết nguyên nhân gốc rễ của hiện tượng nhận diện bị loạn (erratic detection) trong không gian test và đề xuất phương án cải tiến thuật toán nâng cấp hệ thống lên **Version 4**.

---

## 1. Phân Tích Nguyên Nhân Gốc Rễ (Noise & Erratic Detection Root Cause Analysis)

Qua việc phân tích sâu các logs chạy thực tế của hệ thống ở Version 3, chúng tôi đã phát hiện ra **3 nguồn gây nhiễu và gây loạn nhận diện chính**:

### A. Lỗi Nhảy Mã Định Danh Target Ảo (Virtual Target ID Instability - **Nguyên nhân cốt lõi**)
* **Hiện tượng:** Hộp nhận diện bị nhảy loạn vị trí giữa các frame (jumping box) hoặc bị nhấp nháy liên tục (blinking box).
* **Nguyên nhân:** 
  * Hiện tại trong [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py), các target ảo tạo ra từ Point Cloud được gán mã định danh dựa vào index của cụm trong mảng DBSCAN: `tid = VIRTUAL_TARGET_ID_BASE + cluster_id`.
  * Thuật toán DBSCAN trả về danh sách cụm theo thứ tự các điểm dữ liệu xuất hiện trong frame. Thứ tự này thay đổi ngẫu nhiên giữa các frame. 
  * *Ví dụ:* Ở Frame A, người đứng ở `(1.8, 6.4)` được xếp thứ nhất (nhận ID `1000`), người đứng ở `(-1.0, 5.8)` xếp thứ hai (nhận ID `1001`). Ở Frame B, thứ tự đảo ngược, người ở `(-1.0, 5.8)` lại nhận ID `1000` và người ở `(1.8, 6.4)` nhận ID `1001`.
  * **Hậu quả cực kỳ nghiêm trọng:** 
    * [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py) (`GhostTargetFilter`) bị đánh lừa là các target nhảy cóc tức thời qua lại giữa 2 đầu phòng. 
    * `TARGET_SMOOTHING_RESET_DISTANCE` bị kích hoạt liên tục khiến bộ lọc làm mượt (smoothing) bị mất tác dụng, các hộp bị giật cục dữ dội.
    * Khi một ID bị nhảy liên tiếp, các bộ lọc đệm đếm khung hình bị reset liên tục làm hộp bị biến mất và hiện lại (chớp nháy).

### B. Nhiễu Phản Xạ Cố Định / Đồ Vật (Static Clutter & Furniture Ghost Targets)
* **Hiện tượng:** Xuất hiện các hộp ảo cố định tại một số vị trí không có người (như cạnh bàn, ghế sofa, hoặc mảng tường dội tín hiệu mạnh).
* **Nguyên nhân:**
  * Thuật toán DBSCAN và bộ lọc ROI hiện tại lọc ra các cụm điểm tương đối ổn định. Do đồ vật bằng kim loại hoặc gỗ phản xạ tốt, chúng tạo ra các cụm điểm ổn định, đủ số điểm và có chiều cao/rộng tương đối giống người.
  * Mặc dù các vật này hoàn toàn đứng yên (vận tốc Doppler bằng $0$), bộ chấm điểm `score_human_cluster` chỉ trừ $12$ điểm motion, chúng vẫn có thể đạt $60$ - $70$ điểm (vượt ngưỡng `HUMAN_SCORE_THRESHOLD = 52.0`), từ đó sinh ra hộp ảo tồn tại vĩnh viễn trên màn hình.

### C. Hiện Tượng Kéo Vết Do Bộ Ổn Định Thời Gian (Stabilizer Ghost Smearing)
* **Hiện tượng:** Khi người đi qua một vị trí, hộp nhận diện có xu hướng bị kéo dài ra hoặc để lại một hộp ảo "bóng ma" ở vị trí cũ khoảng 0.5s.
* **Nguyên nhân:**
  * `POINTCLOUD_STABILIZER_MAX_AGE_FRAMES = 5` giữ các điểm cũ quá lâu.
  * Voxel size của stabilizer quá lớn (`0.38`m x `0.38`m) tạo điều kiện cho các điểm nhiễu ngẫu nhiên bị gộp lại và tồn tại lâu hơn bình ứng.

---

## 2. Giải Pháp Khắc Phục Đề Xuất (Proposed Solutions)

Chúng tôi đề xuất nâng cấp hệ thống lên **Version 4** với hai vũ khí thuật toán cực kỳ mạnh mẽ:

### Lớp 1: Thiết kế bộ liên kết không gian thời gian (Simple Spatial Tracking Association)
* Thay thế hàm tự do `build_human_targets` bằng một lớp lưu trạng thái **`VirtualTargetTracker`**.
* Mỗi khi phát hiện các cụm điểm DBSCAN trong frame mới, tracker sẽ tiến hành so khớp khoảng cách hình học 2D (XY plane) với các target ảo hoạt động ở frame trước đó.
* **Quy tắc liên kết:**
  * Tìm các cặp cụm - target cũ có khoảng cách nhỏ nhất. Nếu khoảng cách $\le$ `VIRTUAL_CLUSTER_MERGE_DISTANCE_XY` (ví dụ `0.85m`), cụm mới sẽ được kế thừa chính xác ID cũ.
  * Nếu cụm mới không khớp với bất kỳ target cũ nào, nó sẽ được cấp một ID mới tăng dần (bảo toàn tính duy nhất).
  * Giữ lại các target ảo tạm thời biến mất trong bộ nhớ đệm `active_targets` khoảng 15 frame để nếu người đó xuất hiện lại thì vẫn giữ nguyên ID (chống đứt gãy vết).

### Lớp 2: Bộ lọc vật thể tĩnh (Static Clutter Filter)
* `VirtualTargetTracker` sẽ lưu giữ rolling history vị trí (X, Y) và vận tốc Doppler tuyệt đối của các target ảo trong 30 frame gần nhất (~3 giây).
* **Quy tắc nhận diện clutter tĩnh:**
  * Nếu độ lệch chuẩn vị trí của target qua 30 frame cực nhỏ ($\text{std}(X) < 0.05$ m và $\text{std}(Y) < 0.05$ m).
  * Vận tốc Doppler trung bình cực thấp ($\text{mean}(|\text{Doppler}|) < 0.04$ m/s).
  * Hệ thống sẽ xác định đây là **vật thể tĩnh nhiễu** (bàn, ghế, tường) và tiến hành **ẩn hoàn toàn** hộp nhận diện này khỏi màn hình hiển thị. Người đứng im thực tế luôn có micro-motion (thở, dịch chuyển nhỏ) tạo ra độ lệch chuẩn $> 0.06$m và Doppler $> 0.06$m/s nên sẽ không bị ẩn.

---

## 3. Chi Tiết Các Thay Đổi Sẽ Thực Hiện (Review Proposed Code)

Chúng tôi tiếp tục cam kết **KHÔNG xóa bất kỳ file nào** và **tạo preview trước khi sửa code**. Dưới đây là chi tiết các dòng code đề xuất thay đổi:

### 📄 Cấu hình mới đề xuất trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)

```diff
# ============================================================
# POINT CLOUD HUMAN DETECTION SETTINGS
# ============================================================
...
# ID bắt đầu cho các target ảo sinh ra từ point cloud cluster.
VIRTUAL_TARGET_ID_BASE = 1000

+# ============================================================
+# STATIC CLUTTER FILTER SETTINGS (Version 4)
+# ============================================================
+ENABLE_STATIC_CLUTTER_FILTER = True
+STATIC_CLUTTER_MIN_FRAMES = 30
+STATIC_CLUTTER_MAX_STD = 0.05       # Độ lệch chuẩn XY tối đa để coi là đứng im hoàn toàn (đồ vật)
+STATIC_CLUTTER_MAX_DOPPLER = 0.04   # Vận tốc Doppler trung bình tối đa của vật thể tĩnh (m/s)
```

### 📄 Cấu trúc bộ lọc mới trong [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

Chúng tôi sẽ bổ sung lớp `VirtualTargetTracker` vào cuối file để thay thế chức năng của hàm `build_human_targets` bằng cơ chế stateful:

```python
class VirtualTargetTracker:
    """
    Stateful tracker cho các target ảo sinh ra từ Point Cloud.
    Giải quyết triệt để lỗi nhảy ID ngẫu nhiên của DBSCAN và lọc sạch vật thể tĩnh (bàn ghế).
    """
    def __init__(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE # 1000
        self.active_targets = {} # tid -> { "center": np.array, "history_positions": [], "history_dopplers": [], "last_seen_frame": frame }

    def reset(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE
        self.active_targets.clear()

    def track_and_build(self, raw_targets, point_cloud, target_index=None, frame_number=0):
        """
        Gom cụm điểm mây -> So khớp ID ổn định -> Lọc vật thể tĩnh -> Trả về final targets.
        """
        if raw_targets is None:
            raw_targets = []

        point_cloud = ensure_point_cloud_shape(point_cloud)
        roi_points, roi_original_indices = filter_human_roi_with_indices(point_cloud)
        clusters = cluster_pointcloud(roi_points)

        final_targets = []
        cluster_debug = []

        # 1) Đánh giá và lọc target phần cứng (Firmware Targets)
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

        # 2) Xử lý đa mục tiêu ảo song song (Virtual Targets)
        allow_virtual_targets = ENABLE_VIRTUAL_CLUSTER_TARGETS
        if VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS and len(final_targets) > 0:
            allow_virtual_targets = False

        merged_clusters = merge_nearby_clusters(clusters)
        virtual_candidates = []

        # Dọn dẹp các target ảo đã biến mất quá lâu (> 15 frame) trong tracker
        for tid in list(self.active_targets.keys()):
            if frame_number - self.active_targets[tid]["last_seen_frame"] > 15:
                self.active_targets.pop(tid, None)

        cluster_centers = []
        cluster_scores = []
        cluster_features = []
        cluster_point_counts = []
        cluster_dopplers = []
        valid_indices = []

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

            cluster_centers.append(cluster_center)
            cluster_scores.append(score)
            cluster_features.append(features)
            cluster_point_counts.append(len(cluster))
            cluster_dopplers.append(features.get("avg_motion", 0.0))
            valid_indices.append(cid)

        # Tiến hành so khớp không gian thời gian (Spatial Association Matcher)
        matched_cluster_ids = set()
        matched_tids = set()
        assignments = {} # cluster_index -> tid

        if self.active_targets and cluster_centers:
            pairs = []
            for c_idx, cc in enumerate(cluster_centers):
                for tid, target_info in self.active_targets.items():
                    tc = target_info["center"]
                    dist_xy = float(np.sqrt((cc[0] - tc[0])**2 + (cc[1] - tc[1])**2))
                    pairs.append((dist_xy, c_idx, tid))
            
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

        # Tạo target ảo từ các cụm đã gán ID ổn định
        for c_idx, cc in enumerate(cluster_centers):
            score = cluster_scores[c_idx]
            features = cluster_features[c_idx]
            pt_count = cluster_point_counts[c_idx]
            avg_motion = cluster_dopplers[c_idx]
            orig_cid = valid_indices[c_idx]

            if c_idx in assignments:
                tid = assignments[c_idx]
                target_info = self.active_targets[tid]
                target_info["center"] = cc
                target_info["last_seen_frame"] = frame_number
            else:
                # Cấp phát ID mới duy nhất nếu xuất hiện cụm mới hoàn toàn
                tid = self.next_virtual_id
                self.next_virtual_id += 1
                target_info = {
                    "center": cc,
                    "history_positions": [],
                    "history_dopplers": [],
                    "last_seen_frame": frame_number
                }
                self.active_targets[tid] = target_info

            # Ghi nhận lịch sử vị trí và Doppler để phân tích vật thể tĩnh
            target_info["history_positions"].append(cc[:2])
            target_info["history_dopplers"].append(avg_motion)

            if len(target_info["history_positions"]) > STATIC_CLUTTER_MIN_FRAMES:
                target_info["history_positions"] = target_info["history_positions"][-STATIC_CLUTTER_MIN_FRAMES:]
                target_info["history_dopplers"] = target_info["history_dopplers"][-STATIC_CLUTTER_MIN_FRAMES:]

            # Áp dụng bộ lọc vật thể tĩnh
            is_clutter = False
            if ENABLE_STATIC_CLUTTER_FILTER and len(target_info["history_positions"]) >= STATIC_CLUTTER_MIN_FRAMES:
                pos_history = np.array(target_info["history_positions"])
                std_x = float(np.std(pos_history[:, 0]))
                std_y = float(np.std(pos_history[:, 1]))
                mean_doppler = float(np.mean(target_info["history_dopplers"]))

                # Nếu biến thiên vị trí < 5cm và Doppler < 0.04m/s -> Nhiễu bàn ghế tĩnh
                if std_x < STATIC_CLUTTER_MAX_STD and std_y < STATIC_CLUTTER_MAX_STD and mean_doppler < STATIC_CLUTTER_MAX_DOPPLER:
                    is_clutter = True

            if is_clutter:
                continue # Bỏ qua, không đưa vật thể tĩnh vào danh sách target hiển thị

            virtual_target = {
                "tid": int(tid),
                "posX": float(cc[0]),
                "posY": float(cc[1]),
                "posZ": float(cc[2]),
                "velX": 0.0,
                "velY": 0.0,
                "velZ": 0.0,
                "accX": 0.0,
                "accY": 0.0,
                "accZ": 0.0,
                "isVirtual": True,
                "source": "cluster",
                "supportPointCount": int(pt_count),
                "humanScore": score,
                "clusterFeatures": features,
            }

            # Tránh tạo trùng hộp ảo nếu đã có target phần cứng ở sát bên
            too_close_to_existing = False
            for target in final_targets:
                if target_xy_distance(virtual_target, target) < CLUSTER_TO_TARGET_MIN_DISTANCE_XY:
                    too_close_to_existing = True
                    break

            if not too_close_to_existing:
                virtual_candidates.append(virtual_target)

        # Sắp xếp và giới hạn số lượng target ảo hiển thị song song
        virtual_candidates.sort(
            key=lambda t: (t.get("humanScore", 0.0), t.get("supportPointCount", 0)),
            reverse=True
        )

        final_targets.extend(virtual_candidates[:VIRTUAL_CLUSTER_MAX_TARGETS])
        final_targets.sort(key=lambda t: t.get("tid", 0))

        display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

        return final_targets, display_point_cloud, cluster_debug
```

### 📄 Thay đổi đề xuất trong [main.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/main.py)

```diff
-from pointcloud_processing import build_human_targets, HAS_SKLEARN, TemporalPointCloudStabilizer
+from pointcloud_processing import VirtualTargetTracker, HAS_SKLEARN, TemporalPointCloudStabilizer
```

*(Khởi tạo tracker ở đầu hàm `main()`)*
```diff
     parser = AutoRadarUARTParser()
     track_history = TrackHistory(max_len=80, max_missing_frames=12)
     pointcloud_stabilizer = TemporalPointCloudStabilizer()
+    virtual_tracker = VirtualTargetTracker()
```

*(Gọi hàm so khớp của tracker trong radar loop)*
```diff
-                if ENABLE_POINTCLOUD_HUMAN_PROCESSOR:
-                    candidate_targets, display_point_cloud, cluster_debug = build_human_targets(
-                        raw_targets=raw_targets,
-                        point_cloud=point_cloud_for_detection,
-                        target_index=target_index
-                    )
+                if ENABLE_POINTCLOUD_HUMAN_PROCESSOR:
+                    candidate_targets, display_point_cloud, cluster_debug = virtual_tracker.track_and_build(
+                        raw_targets=raw_targets,
+                        point_cloud=point_cloud_for_detection,
+                        target_index=target_index,
+                        frame_number=frame_number
+                    )
```

---

## 4. Kế Hoạch Xác Minh & Thử Nghiệm (Verification Plan)

Sau khi nhận được quyết định và phê duyệt từ bạn, chúng tôi sẽ thực hiện các bước sau:

1. **Kiểm tra cú pháp độc lập (Syntax Verification):**
   * Sử dụng lệnh `python -m py_compile` để kiểm tra lỗi biên dịch của `settings.py`, `pointcloud_processing.py`, và `main.py`.
2. **Kiểm thử thời gian thực (Real-time Run Verification):**
   * Chạy `python -u main.py` để quan sát:
     * Sự ổn định ID của target ảo (kiểm tra xem ID có được giữ cố định khi người đứng im hoặc di chuyển bình thường không).
     * Bộ lọc tĩnh (kiểm tra xem các vật thể đứng im như bàn ghế có bị ẩn hoàn toàn sau 3 giây không).
     * Độ mượt của các hộp người (đảm bảo không còn hiện tượng nhảy vọt hay chớp nháy).
3. **Lập tài liệu kết quả kiểm thử (Walkthrough):**
   * Lưu trữ log chạy thử nghiệm và tổng hợp kết quả chi tiết trong [walkthrough.md](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar Project/IWR6843AOP/People Tracking/docs/walkthrough.md).
