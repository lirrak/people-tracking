"""
Track history and ghost target filtering.
"""

import numpy as np


# ============================================================
# TRACK HISTORY
# ============================================================

class TrackHistory:
    def __init__(self, max_len=80, max_missing_frames=30):
        self.max_len = max_len
        self.max_missing_frames = max_missing_frames
        self.history = {}
        self.missing_count = {}

    def update(self, targets):
        current_ids = set()

        for target in targets:
            tid = target["tid"]
            current_ids.add(tid)

            point = np.array(
                [
                    target["posX"],
                    target["posY"],
                    target["posZ"]
                ],
                dtype=np.float32
            )

            if tid not in self.history:
                self.history[tid] = []

            self.history[tid].append(point)

            if len(self.history[tid]) > self.max_len:
                self.history[tid] = self.history[tid][-self.max_len:]

            self.missing_count[tid] = 0

        old_ids = list(self.history.keys())

        for tid in old_ids:
            if tid not in current_ids:
                self.missing_count[tid] = self.missing_count.get(tid, 0) + 1

                if self.missing_count[tid] > self.max_missing_frames:
                    self.history.pop(tid, None)
                    self.missing_count.pop(tid, None)

    def get(self, tid):
        return self.history.get(tid, [])

# ============================================================
# GHOST TARGET FILTER
# ============================================================

class GhostTargetFilter:
    """
    Lọc target ảo / target cũ trước khi vẽ human box.

    Chức năng chính:
    1. Kiểm tra target có còn point cloud hỗ trợ hay không.
    2. Xóa target cũ sau vài frame nếu người đã rời khỏi radar.
    3. Merge các target quá gần nhau để tránh lỗi 1 người hiện 2 box.
    """

    def __init__(
        self,
        max_missing_frames=6,
        min_support_points=2,
        support_radius_x=0.75,
        support_radius_y=0.75,
        support_radius_z=1.30,
        duplicate_distance_xy=0.75,
        drop_unsupported_immediately=False
    ):
        self.max_missing_frames = max_missing_frames
        self.min_support_points = min_support_points
        self.support_radius_x = support_radius_x
        self.support_radius_y = support_radius_y
        self.support_radius_z = support_radius_z
        self.duplicate_distance_xy = duplicate_distance_xy
        self.drop_unsupported_immediately = drop_unsupported_immediately

        self.missing_count = {}
        self.last_seen_frame = {}

    def reset(self):
        self.missing_count.clear()
        self.last_seen_frame.clear()

    def count_support_points(self, target, point_cloud):
        if point_cloud is None or len(point_cloud) == 0:
            return 0

        tx = target.get("posX", 0.0)
        ty = target.get("posY", 0.0)
        tz = target.get("posZ", 0.0)

        x = point_cloud[:, 0]
        y = point_cloud[:, 1]
        z = point_cloud[:, 2]

        mask = (
            (np.abs(x - tx) <= self.support_radius_x) &
            (np.abs(y - ty) <= self.support_radius_y) &
            (np.abs(z - tz) <= self.support_radius_z)
        )

        return int(np.sum(mask))

    def target_speed(self, target):
        vx = target.get("velX", 0.0)
        vy = target.get("velY", 0.0)
        vz = target.get("velZ", 0.0)

        return float(np.sqrt(vx * vx + vy * vy + vz * vz))

    def is_target_supported(self, target, point_cloud):
        support_points = self.count_support_points(target, point_cloud)
        speed = self.target_speed(target)

        target["supportPointCount"] = support_points
        target["speed"] = speed

        if support_points >= self.min_support_points:
            return True

        # Target đang di chuyển nhẹ vẫn có thể là thật, vì point cloud có thể thưa.
        if speed >= 0.08:
            return True

        return False

    def remove_duplicates(self, targets):
        if len(targets) <= 1:
            return targets

        # Ưu tiên target có nhiều point support hơn.
        # Nếu bằng nhau, ưu tiên target có tốc độ cao hơn vì thường là target mới/thật hơn.
        sorted_targets = sorted(
            targets,
            key=lambda t: (
                t.get("supportPointCount", 0),
                t.get("speed", 0.0)
            ),
            reverse=True
        )

        kept_targets = []

        for target in sorted_targets:
            tx = target.get("posX", 0.0)
            ty = target.get("posY", 0.0)

            is_duplicate = False

            for kept in kept_targets:
                kx = kept.get("posX", 0.0)
                ky = kept.get("posY", 0.0)

                distance_xy = float(np.sqrt((tx - kx) ** 2 + (ty - ky) ** 2))

                if distance_xy < self.duplicate_distance_xy:
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept_targets.append(target)

        # Sắp xếp lại theo ID để hiển thị ổn định hơn
        kept_targets.sort(key=lambda t: t.get("tid", 0))

        return kept_targets

    def update(self, targets, point_cloud, frame_number=None):
        if targets is None:
            targets = []

        filtered_targets = []
        current_ids = set()

        for target in targets:
            tid = target.get("tid", -1)
            current_ids.add(tid)

            supported = self.is_target_supported(target, point_cloud)
            target["ghostFiltered"] = not supported

            if supported:
                self.missing_count[tid] = 0
                if frame_number is not None:
                    self.last_seen_frame[tid] = frame_number
                filtered_targets.append(target)
            else:
                self.missing_count[tid] = self.missing_count.get(tid, 0) + 1
                target["missingFrames"] = self.missing_count[tid]

                if not self.drop_unsupported_immediately:
                    if self.missing_count[tid] <= self.max_missing_frames:
                        filtered_targets.append(target)

        # Tăng missing count cho target đã biến mất khỏi target list firmware
        old_ids = list(self.missing_count.keys())

        for tid in old_ids:
            if tid not in current_ids:
                self.missing_count[tid] = self.missing_count.get(tid, 0) + 1

                if self.missing_count[tid] > self.max_missing_frames:
                    self.missing_count.pop(tid, None)
                    self.last_seen_frame.pop(tid, None)

        filtered_targets = self.remove_duplicates(filtered_targets)

        return filtered_targets
