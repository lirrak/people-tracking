"""
Advanced point cloud human processing.

Pipeline:
1. ROI filter: keep only points in human area.
2. DBSCAN clustering: split point cloud into human-sized clusters.
3. Human confidence score: score each cluster using point count, SNR, height,
   width, depth, and Doppler/motion.
4. Target fusion: combine firmware target_list + target_index + clusters.

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
# ROI FILTER
# ============================================================

def filter_human_roi(points):
    """Return point cloud inside the configured human ROI."""
    if points is None or len(points) == 0:
        return np.empty((0, 5), dtype=np.float32)

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]

    mask = (
        (x >= PC_ROI_X[0]) & (x <= PC_ROI_X[1]) &
        (y >= PC_ROI_Y[0]) & (y <= PC_ROI_Y[1]) &
        (z >= PC_ROI_Z[0]) & (z <= PC_ROI_Z[1])
    )

    return points[mask]


def filter_human_roi_with_indices(points):
    """Return ROI points and the indices of those points in the original array."""
    if points is None or len(points) == 0:
        return np.empty((0, 5), dtype=np.float32), np.empty((0,), dtype=np.int64)

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]

    mask = (
        (x >= PC_ROI_X[0]) & (x <= PC_ROI_X[1]) &
        (y >= PC_ROI_Y[0]) & (y <= PC_ROI_Y[1]) &
        (z >= PC_ROI_Z[0]) & (z <= PC_ROI_Z[1])
    )

    indices = np.where(mask)[0]
    return points[mask], indices


# ============================================================
# DBSCAN CLUSTERING
# ============================================================

def _fallback_dbscan_labels(xyz, eps=0.50, min_samples=3):
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


def cluster_pointcloud(points, eps=None, min_samples=None, min_points=None):
    """Cluster ROI point cloud and return a list of point arrays."""
    if eps is None:
        eps = CLUSTER_EPS
    if min_samples is None:
        min_samples = CLUSTER_MIN_SAMPLES
    if min_points is None:
        min_points = CLUSTER_MIN_POINTS

    if points is None or len(points) == 0:
        return []

    if len(points) < min_points:
        return []

    xyz = points[:, 0:3]

    if HAS_SKLEARN:
        labels = SklearnDBSCAN(eps=eps, min_samples=min_samples).fit_predict(xyz)
    else:
        labels = _fallback_dbscan_labels(xyz, eps=eps, min_samples=min_samples)

    clusters = []

    for label in sorted(set(labels)):
        if label == -1:
            continue

        cluster = points[labels == label]

        if len(cluster) >= min_points:
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
    if points is None or len(points) == 0:
        return 0.0, {
            "point_count": 0,
            "avg_snr": 0.0,
            "avg_motion": 0.0,
            "width_x": 0.0,
            "depth_y": 0.0,
            "height_z": 0.0,
        }

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]
    doppler = points[:, 3] if points.shape[1] >= 4 else np.zeros(len(points))
    snr = points[:, 4] if points.shape[1] >= 5 else np.zeros(len(points))

    point_count = int(len(points))
    width_x = float(np.max(x) - np.min(x)) if point_count > 1 else 0.0
    depth_y = float(np.max(y) - np.min(y)) if point_count > 1 else 0.0
    height_z = float(np.max(z) - np.min(z)) if point_count > 1 else 0.0
    avg_snr = float(np.mean(snr)) if point_count > 0 else 0.0
    avg_motion = float(np.mean(np.abs(doppler))) if point_count > 0 else 0.0

    score = 0.0

    # Enough points in the cluster.
    score += min(point_count / 8.0, 1.0) * 35.0

    # Strong reflection.
    score += min(avg_snr / 20.0, 1.0) * 20.0

    # Motion/micro-motion.
    score += min(avg_motion / 0.25, 1.0) * 15.0

    # Human-like vertical spread.
    if 0.30 <= height_z <= 2.30:
        score += 15.0
    elif 0.15 <= height_z < 0.30:
        score += 6.0

    # Human-like width.
    if 0.15 <= width_x <= 1.60:
        score += 10.0
    elif width_x < 0.15 and point_count >= 5:
        score += 4.0

    # Human-like depth.
    if 0.05 <= depth_y <= 1.80:
        score += 5.0

    features = {
        "point_count": point_count,
        "avg_snr": avg_snr,
        "avg_motion": avg_motion,
        "width_x": width_x,
        "depth_y": depth_y,
        "height_z": height_z,
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

    if points is None or len(points) == 0:
        return np.empty((0, 5), dtype=np.float32)

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
    if point_cloud is None or len(point_cloud) == 0:
        return np.empty((0, 5), dtype=np.float32)

    if target_index is None or len(target_index) == 0:
        return np.empty((0, 5), dtype=np.float32)

    if len(target_index) != len(point_cloud):
        return np.empty((0, 5), dtype=np.float32)

    tid = int(target_id)
    idx = target_index.astype(np.int32)

    if tid < 0 or tid > 252:
        return np.empty((0, 5), dtype=np.float32)

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

        associated_points = np.empty((0, 5), dtype=np.float32)

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
        # already did part of the association work.
        if score >= HUMAN_SCORE_TARGET_THRESHOLD or len(associated_points) >= GHOST_MIN_SUPPORT_POINTS:
            final_targets.append(target)

    # --------------------------------------------------------
    # 2) Add virtual targets from point cloud clusters.
    #
    # Important:
    # A single real person can generate several separated point clusters
    # from chest / arm / leg reflections. Therefore, do not convert every
    # raw DBSCAN cluster directly to a human box. Merge nearby clusters first,
    # then score the merged body candidate.
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

    final_targets.sort(key=lambda t: t.get("tid", 0))

    display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

    return final_targets, display_point_cloud, cluster_debug
