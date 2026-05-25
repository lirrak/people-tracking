"""
Advanced point cloud human processing.

Pipeline:
1. ROI filter: keep only points in human area.
2. Quality filter: remove weak / invalid / outlier points.
3. DBSCAN clustering: split point cloud into human-sized clusters.
4. Human confidence score: score each cluster using point count, SNR, height,
   width, depth, center height, and Doppler/motion.
5. Target fusion: combine firmware target_list + target_index + clusters.

This file has no hard dependency on scikit-learn. If sklearn is not installed,
it uses a small built-in DBSCAN fallback.
"""

import numpy as np
from settings import *

try:
    from sklearn.cluster import DBSCAN as SklearnDBSCAN
    HAS_SKLEARN = True
except Exception:
    SklearnDBSCAN = None
    HAS_SKLEARN = False


# ============================================================
# SMALL HELPERS
# ============================================================

def empty_point_cloud():
    return np.empty((0, 5), dtype=np.float32)


def ensure_point_cloud_shape(points):
    """Return a safe Nx5 float32 point cloud."""
    if points is None:
        return empty_point_cloud()

    arr = np.asarray(points, dtype=np.float32)

    if arr.size == 0:
        return empty_point_cloud()

    if arr.ndim != 2:
        return empty_point_cloud()

    if arr.shape[1] < 5:
        padded = np.zeros((arr.shape[0], 5), dtype=np.float32)
        padded[:, :arr.shape[1]] = arr
        return padded

    return arr[:, :5]


# ============================================================
# TILT CALIBRATION & COORDINATE TRANSFORMATION
# ============================================================

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
    
    # Rotation around X-axis (pitch) and translation along Z (mount height)
    transformed[:, 1] = y_radar * np.cos(theta) - z_radar * np.sin(theta)
    transformed[:, 2] = y_radar * np.sin(theta) + z_radar * np.cos(theta) + h
    
    return transformed


def transform_target_to_room_coordinates(target):
    """Transform a firmware target's coordinates to room coordinates."""
    if not (ENABLE_COORD_TRANSFORM if 'ENABLE_COORD_TRANSFORM' in globals() else False):
        return target
        
    theta_deg = RADAR_TILT_ANGLE_DEG if 'RADAR_TILT_ANGLE_DEG' in globals() else 30.0
    h = RADAR_MOUNT_HEIGHT_M if 'RADAR_MOUNT_HEIGHT_M' in globals() else 0.60
    theta = np.radians(theta_deg)
    
    transformed = dict(target)
    y_radar = target.get("posY", 0.0)
    z_radar = target.get("posZ", 0.0)
    
    transformed["posY"] = float(y_radar * np.cos(theta) - z_radar * np.sin(theta))
    transformed["posZ"] = float(y_radar * np.sin(theta) + z_radar * np.cos(theta) + h)
    
    return transformed


# ============================================================
# ROI + QUALITY FILTER
# ============================================================

def build_human_point_mask(points):
    """
    Build mask for points that can realistically belong to a person.

    Columns expected:
        x, y, z, doppler, snr/intensity
    """
    points = ensure_point_cloud_shape(points)

    if len(points) == 0:
        return np.zeros((0,), dtype=bool)

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    doppler = points[:, 3]
    snr = points[:, 4]

    finite_mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(doppler) & np.isfinite(snr)

    roi_mask = (
        (x >= PC_ROI_X[0]) & (x <= PC_ROI_X[1]) &
        (y >= PC_ROI_Y[0]) & (y <= PC_ROI_Y[1]) &
        (z >= PC_ROI_Z[0]) & (z <= PC_ROI_Z[1])
    )

    mask = finite_mask & roi_mask

    if ENABLE_POINT_QUALITY_FILTER and len(points) > 0:
        # Some OOB / parser modes return SNR = 0 for every point.
        # In that case, do not apply the min SNR filter because it would delete everything.
        has_real_snr = bool(np.nanmax(np.abs(snr)) > 0.001)

        if has_real_snr:
            mask &= (snr >= MIN_POINT_SNR) & (snr <= MAX_POINT_SNR)

    if ENABLE_DOPPLER_OUTLIER_FILTER:
        mask &= np.abs(doppler) <= MAX_ABS_DOPPLER

    return mask


def filter_human_roi(points):
    """Return point cloud inside the configured human ROI and quality filters."""
    points = ensure_point_cloud_shape(points)

    if len(points) == 0:
        return empty_point_cloud()

    mask = build_human_point_mask(points)
    return points[mask]


def filter_human_roi_with_indices(points):
    """Return filtered points and the indices of those points in the original array."""
    points = ensure_point_cloud_shape(points)

    if len(points) == 0:
        return empty_point_cloud(), np.empty((0,), dtype=np.int64)

    mask = build_human_point_mask(points)
    indices = np.where(mask)[0]
    return points[mask], indices


# ============================================================
# DBSCAN CLUSTERING
# ============================================================

def _fallback_dbscan_labels(xyz, eps=0.45, min_samples=3):
    """Small DBSCAN implementation used when scikit-learn is unavailable."""
    n = len(xyz)
    labels = np.full(n, -1, dtype=np.int32)

    if n == 0:
        return labels

    visited = np.zeros(n, dtype=bool)
    cluster_id = 0

    def region_query(index):
        diff = xyz - xyz[index]
        dist = np.sqrt(np.sum(diff * diff, axis=1))
        return np.where(dist <= eps)[0]

    for i in range(n):
        if visited[i]:
            continue

        visited[i] = True
        neighbors = list(region_query(i))

        if len(neighbors) < min_samples:
            labels[i] = -1
            continue

        labels[i] = cluster_id
        j = 0

        while j < len(neighbors):
            p = neighbors[j]

            if not visited[p]:
                visited[p] = True
                p_neighbors = list(region_query(p))

                if len(p_neighbors) >= min_samples:
                    for item in p_neighbors:
                        if item not in neighbors:
                            neighbors.append(item)

            if labels[p] == -1:
                labels[p] = cluster_id

            j += 1

        cluster_id += 1

    return labels


def _adaptive_dbscan_labels(xyz, base_eps=0.20, k=0.06, min_samples=3):
    """Range-adaptive DBSCAN implementation where eps scales with target cự ly."""
    n = len(xyz)
    labels = np.full(n, -1, dtype=np.int32)

    if n == 0:
        return labels

    visited = np.zeros(n, dtype=bool)
    cluster_id = 0

    def region_query(index):
        pt = xyz[index]
        # Khoảng cách nằm ngang R = sqrt(X^2 + Y^2)
        r = float(np.sqrt(pt[0]**2 + pt[1]**2))
        adaptive_eps = base_eps + k * r
        
        diff = xyz - pt
        dist = np.sqrt(np.sum(diff * diff, axis=1))
        return np.where(dist <= adaptive_eps)[0]

    for i in range(n):
        if visited[i]:
            continue

        visited[i] = True
        neighbors = list(region_query(i))

        if len(neighbors) < min_samples:
            labels[i] = -1
            continue

        labels[i] = cluster_id
        j = 0

        while j < len(neighbors):
            p = neighbors[j]

            if not visited[p]:
                visited[p] = True
                p_neighbors = list(region_query(p))

                if len(p_neighbors) >= min_samples:
                    for item in p_neighbors:
                        if item not in neighbors:
                            neighbors.append(item)

            if labels[p] == -1:
                labels[p] = cluster_id

            j += 1

        cluster_id += 1

    return labels


def get_dynamic_min_points(range_r):
    """Tính toán số điểm tối thiểu của cụm người thật thích nghi theo khoảng cách R (mét)."""
    # Công thức: N_min = max(5, round(18 - 2.5 * R))
    min_pts = int(np.round(18.0 - 2.5 * range_r))
    return max(5, min_pts)


def cluster_pointcloud(points, eps=None, min_samples=None, min_points=None):
    """Cluster ROI point cloud and return a list of point arrays."""
    if eps is None:
        eps = CLUSTER_EPS
    if min_samples is None:
        min_samples = CLUSTER_MIN_SAMPLES
    if min_points is None:
        min_points = CLUSTER_MIN_POINTS

    points = ensure_point_cloud_shape(points)

    # Lọc sơ bộ số điểm tối thiểu
    if len(points) < min_points:
        return []

    xyz = points[:, 0:3]

    use_adaptive = ENABLE_ADAPTIVE_DBSCAN if 'ENABLE_ADAPTIVE_DBSCAN' in globals() else False

    if use_adaptive:
        base_eps = DBSCAN_BASE_EPS if 'DBSCAN_BASE_EPS' in globals() else 0.20
        k = DBSCAN_RANGE_SCALE_K if 'DBSCAN_RANGE_SCALE_K' in globals() else 0.06
        labels = _adaptive_dbscan_labels(xyz, base_eps=base_eps, k=k, min_samples=min_samples)
    else:
        if HAS_SKLEARN:
            labels = SklearnDBSCAN(eps=eps, min_samples=min_samples).fit_predict(xyz)
        else:
            labels = _fallback_dbscan_labels(xyz, eps=eps, min_samples=min_samples)

    clusters = []

    for label in sorted(set(labels)):
        if label == -1:
            continue

        cluster = points[labels == label]

        # Tính toán cự ly ngang từ radar đến tâm cụm
        center = np.mean(cluster[:, 0:3], axis=0)
        range_r = float(np.sqrt(center[0]**2 + center[1]**2))
        
        # Áp dụng bộ lọc mật độ điểm động thích nghi khoảng cách
        dynamic_min = get_dynamic_min_points(range_r)

        if len(cluster) >= dynamic_min:
            clusters.append(cluster)

    return clusters


# ============================================================
# HUMAN CONFIDENCE SCORE
# ============================================================

def score_human_cluster(points):
    """
    Return a human confidence score and feature dictionary.

    Score range is roughly 0-100. It is intentionally simple and tunable.
    """
    points = ensure_point_cloud_shape(points)

    if len(points) == 0:
        return 0.0, {
            "point_count": 0,
            "avg_snr": 0.0,
            "avg_motion": 0.0,
            "width_x": 0.0,
            "depth_y": 0.0,
            "height_z": 0.0,
            "min_z": 0.0,
            "max_z": 0.0,
            "center_z": 0.0,
            "is_shape_valid": False,
        }

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    doppler = points[:, 3]
    snr = points[:, 4]

    point_count = int(len(points))
    width_x = float(np.max(x) - np.min(x)) if point_count > 1 else 0.0
    depth_y = float(np.max(y) - np.min(y)) if point_count > 1 else 0.0
    height_z = float(np.max(z) - np.min(z)) if point_count > 1 else 0.0
    min_z = float(np.min(z))
    max_z = float(np.max(z))
    center_z = float(np.mean(z))
    avg_snr = float(np.mean(snr)) if point_count > 0 else 0.0
    avg_motion = float(np.mean(np.abs(doppler))) if point_count > 0 else 0.0

    is_shape_valid = True

    if height_z < HUMAN_CLUSTER_MIN_HEIGHT_Z:
        is_shape_valid = False
    if height_z > HUMAN_CLUSTER_MAX_HEIGHT_Z:
        is_shape_valid = False
    if width_x > HUMAN_CLUSTER_MAX_WIDTH_X:
        is_shape_valid = False
    if depth_y > HUMAN_CLUSTER_MAX_DEPTH_Y:
        is_shape_valid = False
    if center_z < HUMAN_CLUSTER_MIN_CENTER_Z or center_z > HUMAN_CLUSTER_MAX_CENTER_Z:
        is_shape_valid = False

    score = 0.0

    # Enough points in the cluster.
    score += min(point_count / 10.0, 1.0) * 30.0

    # Strong reflection. Cap at 25 because SNR may saturate at 255 in some formats.
    score += min(avg_snr / 25.0, 1.0) * 18.0

    # Motion/micro-motion. Human may stand still, so this should help but not dominate.
    score += min(avg_motion / 0.25, 1.0) * 12.0

    # Human-like vertical spread.
    if 0.50 <= height_z <= 2.10:
        score += 18.0
    elif HUMAN_CLUSTER_MIN_HEIGHT_Z <= height_z < 0.50:
        score += 8.0

    # Human-like width.
    if 0.15 <= width_x <= 1.00:
        score += 12.0
    elif HUMAN_CLUSTER_MIN_WIDTH_X <= width_x < 0.15 and point_count >= 6:
        score += 5.0
    elif 1.00 < width_x <= HUMAN_CLUSTER_MAX_WIDTH_X:
        score += 6.0

    # Human-like depth.
    if 0.05 <= depth_y <= 1.00:
        score += 6.0
    elif 1.00 < depth_y <= HUMAN_CLUSTER_MAX_DEPTH_Y:
        score += 3.0

    # Center height should not be on the floor.
    if 0.55 <= center_z <= 1.60:
        score += 4.0
    elif HUMAN_CLUSTER_MIN_CENTER_Z <= center_z < 0.55:
        score += 2.0

    # Strong penalty for invalid geometry.
    if not is_shape_valid:
        score *= 0.45

    features = {
        "point_count": point_count,
        "avg_snr": avg_snr,
        "avg_motion": avg_motion,
        "width_x": width_x,
        "depth_y": depth_y,
        "height_z": height_z,
        "min_z": min_z,
        "max_z": max_z,
        "center_z": center_z,
        "is_shape_valid": is_shape_valid,
    }

    return float(score), features


# ============================================================
# TARGET / POINT ASSOCIATION
# ============================================================

def points_near_target(points, target, rx=None, ry=None, rz=None):
    """Return points inside a box around a firmware target."""
    if rx is None:
        rx = TARGET_SUPPORT_RADIUS_X
    if ry is None:
        ry = TARGET_SUPPORT_RADIUS_Y
    if rz is None:
        rz = TARGET_SUPPORT_RADIUS_Z

    points = ensure_point_cloud_shape(points)

    if len(points) == 0:
        return empty_point_cloud()

    tx = target.get("posX", 0.0)
    ty = target.get("posY", 0.0)
    tz = target.get("posZ", 0.0)

    mask = (
        (np.abs(points[:, 0] - tx) <= rx) &
        (np.abs(points[:, 1] - ty) <= ry) &
        (np.abs(points[:, 2] - tz) <= rz)
    )

    return points[mask]


def points_from_target_index(point_cloud, target_index, target_id):
    """
    Use target_index TLV to get points associated with a target ID.

    Many TI builds use 253/254/255 for invalid/noise points, so those values are ignored.
    """
    point_cloud = ensure_point_cloud_shape(point_cloud)

    if len(point_cloud) == 0:
        return empty_point_cloud()

    if target_index is None or len(target_index) == 0:
        return empty_point_cloud()

    if len(target_index) != len(point_cloud):
        return empty_point_cloud()

    tid = int(target_id)
    idx = target_index.astype(np.int32)

    if tid < 0 or tid > 252:
        return empty_point_cloud()

    mask = idx == tid
    return point_cloud[mask]


def target_xy_distance(target_a, target_b):
    ax = target_a.get("posX", 0.0)
    ay = target_a.get("posY", 0.0)
    bx = target_b.get("posX", 0.0)
    by = target_b.get("posY", 0.0)
    return float(np.sqrt((ax - bx) ** 2 + (ay - by) ** 2))


def cluster_to_virtual_target(cluster, cluster_id):
    center = np.mean(cluster[:, 0:3], axis=0)
    score, features = score_human_cluster(cluster)

    return {
        "tid": int(VIRTUAL_TARGET_ID_BASE + cluster_id),
        "posX": float(center[0]),
        "posY": float(center[1]),
        "posZ": float(center[2]),
        "velX": 0.0,
        "velY": 0.0,
        "velZ": 0.0,
        "accX": 0.0,
        "accY": 0.0,
        "accZ": 0.0,
        "isVirtual": True,
        "source": "cluster",
        "supportPointCount": int(len(cluster)),
        "humanScore": score,
        "clusterFeatures": features,
    }


def cluster_xy_distance(cluster_a, cluster_b):
    """Distance between two cluster centers in the X-Y plane."""
    center_a = np.mean(cluster_a[:, 0:3], axis=0)
    center_b = np.mean(cluster_b[:, 0:3], axis=0)

    dx = float(center_a[0] - center_b[0])
    dy = float(center_a[1] - center_b[1])

    return float(np.sqrt(dx * dx + dy * dy))


def merge_nearby_clusters(clusters, merge_distance_xy=None):
    """
    Merge small point-cloud clusters that are likely parts of the same body.

    This prevents one real person from being split into many virtual boxes
    such as ID 1000, 1001, 1002, 1003.
    """
    if merge_distance_xy is None:
        merge_distance_xy = VIRTUAL_CLUSTER_MERGE_DISTANCE_XY

    if not clusters:
        return []

    used = [False] * len(clusters)
    merged_clusters = []

    for i, cluster in enumerate(clusters):
        if used[i]:
            continue

        used[i] = True
        group = [cluster]
        changed = True

        while changed:
            changed = False
            current_group_points = np.vstack(group)

            for j, other in enumerate(clusters):
                if used[j]:
                    continue

                distance_xy = cluster_xy_distance(current_group_points, other)

                if distance_xy <= merge_distance_xy:
                    used[j] = True
                    group.append(other)
                    changed = True

        merged_clusters.append(np.vstack(group))

    return merged_clusters




# ============================================================
# TEMPORAL POINT CLOUD STABILIZER
# ============================================================

class TemporalPointCloudStabilizer:
    """
    Stabilize sparse / flickering point cloud by keeping a short rolling window.

    The stabilizer groups points into small 3D voxels. Points inside voxels that
    appear across multiple recent frames are kept because they are more likely to
    belong to a real object/person. Current-frame points can also be kept so a
    new person does not appear too late.
    """

    def __init__(
        self,
        max_age_frames=None,
        voxel_size_x=None,
        voxel_size_y=None,
        voxel_size_z=None,
        min_voxel_hits=None,
        keep_current_frame=None,
        max_points=None,
    ):
        self.max_age_frames = POINTCLOUD_STABILIZER_MAX_AGE_FRAMES if max_age_frames is None else max_age_frames
        self.voxel_size_x = POINTCLOUD_STABILIZER_VOXEL_SIZE_X if voxel_size_x is None else voxel_size_x
        self.voxel_size_y = POINTCLOUD_STABILIZER_VOXEL_SIZE_Y if voxel_size_y is None else voxel_size_y
        self.voxel_size_z = POINTCLOUD_STABILIZER_VOXEL_SIZE_Z if voxel_size_z is None else voxel_size_z
        self.min_voxel_hits = POINTCLOUD_STABILIZER_MIN_VOXEL_HITS if min_voxel_hits is None else min_voxel_hits
        self.keep_current_frame = POINTCLOUD_STABILIZER_KEEP_CURRENT_FRAME if keep_current_frame is None else keep_current_frame
        self.max_points = POINTCLOUD_STABILIZER_MAX_POINTS if max_points is None else max_points
        self.buffer = []

    def reset(self):
        self.buffer.clear()

    def _voxel_keys(self, points):
        points = ensure_point_cloud_shape(points)
        if len(points) == 0:
            return np.empty((0, 3), dtype=np.int32)

        vx = max(float(self.voxel_size_x), 1e-6)
        vy = max(float(self.voxel_size_y), 1e-6)
        vz = max(float(self.voxel_size_z), 1e-6)

        keys = np.floor(points[:, 0:3] / np.array([vx, vy, vz], dtype=np.float32))
        return keys.astype(np.int32)

    def update(self, points, frame_number):
        points = ensure_point_cloud_shape(points)
        frame_number = int(frame_number)

        if len(points) > 0:
            self.buffer.append((frame_number, points.copy()))

        min_frame = frame_number - int(self.max_age_frames) + 1
        self.buffer = [item for item in self.buffer if item[0] >= min_frame]

        if not self.buffer:
            return empty_point_cloud()

        all_points_list = []
        all_frames_list = []
        all_keys_list = []

        for frame_id, frame_points in self.buffer:
            frame_points = ensure_point_cloud_shape(frame_points)
            if len(frame_points) == 0:
                continue

            keys = self._voxel_keys(frame_points)
            all_points_list.append(frame_points)
            all_frames_list.append(np.full((len(frame_points),), frame_id, dtype=np.int32))
            all_keys_list.append(keys)

        if not all_points_list:
            return empty_point_cloud()

        all_points = np.vstack(all_points_list)
        all_frames = np.concatenate(all_frames_list)
        all_keys = np.vstack(all_keys_list)

        # Count how many different frames each voxel appears in.
        voxel_frame_pairs = set()
        for key, frame_id in zip(all_keys, all_frames):
            voxel_frame_pairs.add((int(key[0]), int(key[1]), int(key[2]), int(frame_id)))

        voxel_hits = {}
        for kx, ky, kz, _frame_id in voxel_frame_pairs:
            key = (kx, ky, kz)
            voxel_hits[key] = voxel_hits.get(key, 0) + 1

        keep_mask = np.zeros((len(all_points),), dtype=bool)

        for i, key in enumerate(all_keys):
            voxel_key = (int(key[0]), int(key[1]), int(key[2]))
            if voxel_hits.get(voxel_key, 0) >= int(self.min_voxel_hits):
                keep_mask[i] = True

        if self.keep_current_frame:
            keep_mask |= (all_frames == frame_number)

        stable_points = all_points[keep_mask]
        stable_frames = all_frames[keep_mask]

        if len(stable_points) == 0:
            return empty_point_cloud()

        # Prefer newer points if the buffer becomes too large.
        if self.max_points is not None and len(stable_points) > int(self.max_points):
            order = np.argsort(stable_frames)
            keep_indices = order[-int(self.max_points):]
            stable_points = stable_points[keep_indices]

        return stable_points.astype(np.float32)


# ============================================================
# FUSION PIPELINE
# ============================================================

def build_human_targets(raw_targets, point_cloud, target_index=None):
    """
    Build final human targets from firmware targets + point cloud clusters.

    Returns:
        final_targets, display_point_cloud, cluster_debug
    """
    if raw_targets is None:
        raw_targets = []

    # Transform coordinates to flat room coordinates if enabled
    point_cloud = transform_to_room_coordinates(point_cloud)
    raw_targets = [transform_target_to_room_coordinates(t) for t in raw_targets]

    point_cloud = ensure_point_cloud_shape(point_cloud)
    roi_points, roi_original_indices = filter_human_roi_with_indices(point_cloud)
    clusters = cluster_pointcloud(roi_points)

    final_targets = []
    cluster_debug = []

    # --------------------------------------------------------
    # 1) Score firmware targets using target_index or radius support.
    # --------------------------------------------------------
    for target in raw_targets:
        target = dict(target)
        tid = target.get("tid", -1)
        tz = target.get("posZ", 0.0)

        # Loại bỏ các target có vị trí tâm phi vật lý (như phản xạ sâu dưới sàn Z = -0.41m)
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

        # Firmware target is allowed to pass with a lower score because the tracker
        # already did part of the association work. However, require either support
        # points or a score that is not purely noise.
        if score >= HUMAN_SCORE_TARGET_THRESHOLD or len(associated_points) >= GHOST_MIN_SUPPORT_POINTS:
            final_targets.append(target)

    # --------------------------------------------------------
    # 2) Add virtual targets from point cloud clusters.
    # --------------------------------------------------------
    allow_virtual_targets = ENABLE_VIRTUAL_CLUSTER_TARGETS

    if VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS and len(final_targets) > 0:
        allow_virtual_targets = False

    merged_clusters = merge_nearby_clusters(clusters)
    virtual_candidates = []

    for cluster_id, cluster in enumerate(merged_clusters):
        score, features = score_human_cluster(cluster)
        cluster_center = np.mean(cluster[:, 0:3], axis=0)

        cluster_debug.append({
            "cluster_id": cluster_id,
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

        virtual_target = cluster_to_virtual_target(cluster, cluster_id)
        virtual_target["source"] = "merged_cluster"

        too_close_to_existing = False
        for target in final_targets:
            if target_xy_distance(virtual_target, target) < CLUSTER_TO_TARGET_MIN_DISTANCE_XY:
                too_close_to_existing = True
                break

        if not too_close_to_existing:
            virtual_candidates.append(virtual_target)

    virtual_candidates.sort(
        key=lambda t: (t.get("humanScore", 0.0), t.get("supportPointCount", 0)),
        reverse=True
    )

    final_targets.extend(virtual_candidates[:VIRTUAL_CLUSTER_MAX_TARGETS])
    
    # Triệt tiêu các Ghost Target sinh ra do dội sóng đa đường
    final_targets = suppress_multipath_ghosts(final_targets)
    
    final_targets.sort(key=lambda t: t.get("tid", 0))

    display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

    return final_targets, display_point_cloud, cluster_debug


def suppress_multipath_ghosts(candidates):
    """Quét và triệt tiêu các Ghost Target sinh ra do dội sóng gương qua tường."""
    if len(candidates) <= 1:
        return candidates
        
    # Sắp xếp các ứng viên theo Y tăng dần (gần radar trước, xa sau)
    candidates = list(candidates)
    candidates.sort(key=lambda t: t["posY"])
    kept_candidates = []
    
    for target in candidates:
        tx = target["posX"]
        ty = target["posY"]
        is_ghost = False
        
        # So sánh với các target thật ở gần radar hơn
        for primary in kept_candidates:
            px = primary["posX"]
            py = primary["posY"]
            
            # Tính góc azimuth (radian) của từng target
            angle_p = np.arctan2(px, py)
            angle_t = np.arctan2(tx, ty)
            
            # Tính độ lệch góc nằm trong khoảng [-pi, pi]
            angle_diff = (angle_t - angle_p + np.pi) % (2 * np.pi) - np.pi
            
            # Nếu nằm cùng góc quét Azimuth (lệch nhau ít < 10 độ = 0.1745 rad) nhưng khoảng cách xa hơn
            same_angle = abs(angle_diff) < np.radians(10.0)
            further_away = ty > py + 0.80
            
            if same_angle and further_away:
                # Kiểm tra xem có phải dội gương (độ mạnh phản xạ thấp hơn nhiều target chính)
                primary_pts = primary.get("supportPointCount", 10)
                target_pts = target.get("supportPointCount", 0)
                
                is_virtual = target.get("isVirtual", False) or target.get("source") in ("cluster", "merged_cluster")
                pts_ratio = 1.10 if is_virtual else 0.75
                
                if target_pts < primary_pts * pts_ratio:
                    is_ghost = True
                    break
                    
        if not is_ghost:
            kept_candidates.append(target)
            
    return kept_candidates


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

        # Transform coordinates to flat room coordinates if enabled
        point_cloud = transform_to_room_coordinates(point_cloud)
        raw_targets = [transform_target_to_room_coordinates(t) for t in raw_targets]

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
            
            # Áp dụng bán kính so khớp liên khung độc lập để bảo toàn ID ổn định
            assoc_radius = VIRTUAL_TRACKER_ASSOCIATION_RADIUS if 'VIRTUAL_TRACKER_ASSOCIATION_RADIUS' in globals() else VIRTUAL_CLUSTER_MERGE_DISTANCE_XY
            
            # Liên kết tham lam (Greedy Association)
            for dist_xy, c_idx, tid in pairs:
                if c_idx not in matched_cluster_ids and tid not in matched_tids:
                    if dist_xy <= assoc_radius:
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
        
        # Triệt tiêu các Ghost Target sinh ra do dội sóng đa đường
        final_targets = suppress_multipath_ghosts(final_targets)
        
        final_targets.sort(key=lambda t: t.get("tid", 0))

        display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

        return final_targets, display_point_cloud, cluster_debug

