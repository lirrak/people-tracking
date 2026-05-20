"""
Track history and ghost target filtering.

This version adds:
- multi-frame confirmation for new targets
- faster ghost removal
- duplicate target removal
- exponential moving average smoothing for human boxes
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
    2. Xác nhận target mới qua nhiều frame để giảm false detect.
    3. Xóa target cũ sau vài frame nếu người đã rời khỏi radar.
    4. Merge các target quá gần nhau để tránh lỗi 1 người hiện 2 box.
    5. Smooth vị trí box để không bị giật.
    """

    def __init__(
        self,
        max_missing_frames=3,
        min_support_points=3,
        support_radius_x=0.70,
        support_radius_y=0.70,
        support_radius_z=1.20,
        duplicate_distance_xy=0.85,
        drop_unsupported_immediately=False,
        confirm_frames=2,
        apply_confirmation_to_firmware_targets=False,
        enable_smoothing=True,
        smoothing_alpha=0.35,
        smoothing_reset_distance=1.50,
    ):
        self.max_missing_frames = max_missing_frames
        self.min_support_points = min_support_points
        self.support_radius_x = support_radius_x
        self.support_radius_y = support_radius_y
        self.support_radius_z = support_radius_z
        self.duplicate_distance_xy = duplicate_distance_xy
        self.drop_unsupported_immediately = drop_unsupported_immediately
        self.confirm_frames = max(1, int(confirm_frames))
        self.apply_confirmation_to_firmware_targets = apply_confirmation_to_firmware_targets
        self.enable_smoothing = enable_smoothing
        self.smoothing_alpha = float(np.clip(smoothing_alpha, 0.01, 1.0))
        self.smoothing_reset_distance = smoothing_reset_distance

        self.missing_count = {}
        self.last_seen_frame = {}
        self.confirm_count = {}
        self.smoothed_position = {}

    def reset(self):
        self.missing_count.clear()
        self.last_seen_frame.clear()
        self.confirm_count.clear()
        self.smoothed_position.clear()

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

        # Nếu build_human_targets đã tính supportPointCount, lấy giá trị lớn hơn.
        # Điều này giúp không bị mất support khi target_index hoạt động tốt.
        previous_support = int(target.get("supportPointCount", 0))
        support_points = max(support_points, previous_support)

        target["supportPointCount"] = support_points
        target["speed"] = speed

        if support_points >= self.min_support_points:
            return True

        # Target đang di chuyển nhẹ vẫn có thể là thật, vì point cloud có thể thưa.
        # Tuy nhiên không cho điều kiện này quá mạnh để tránh giữ ghost target quá lâu.
        if support_points >= 1 and speed >= 0.10:
            return True

        return False

    def should_apply_confirmation(self, target):
        is_virtual = bool(target.get("isVirtual", False))
        source = target.get("source", "")

        if is_virtual or source in ("cluster", "merged_cluster"):
            return True

        return bool(self.apply_confirmation_to_firmware_targets)

    def is_confirmed(self, target, supported):
        tid = target.get("tid", -1)

        if not supported:
            return False

        self.confirm_count[tid] = self.confirm_count.get(tid, 0) + 1
        target["confirmFrames"] = self.confirm_count[tid]

        if not self.should_apply_confirmation(target):
            return True

        return self.confirm_count[tid] >= self.confirm_frames

    def smooth_target(self, target):
        if not self.enable_smoothing:
            return target

        tid = target.get("tid", -1)
        current = np.array(
            [
                target.get("posX", 0.0),
                target.get("posY", 0.0),
                target.get("posZ", 0.0),
            ],
            dtype=np.float32
        )

        if tid not in self.smoothed_position:
            self.smoothed_position[tid] = current
            target["rawPosX"] = float(current[0])
            target["rawPosY"] = float(current[1])
            target["rawPosZ"] = float(current[2])
            return target

        previous = self.smoothed_position[tid]
        jump_distance = float(np.linalg.norm(current - previous))

        if jump_distance > self.smoothing_reset_distance:
            smoothed = current
        else:
            alpha = self.smoothing_alpha
            smoothed = previous * (1.0 - alpha) + current * alpha

        self.smoothed_position[tid] = smoothed

        target["rawPosX"] = float(current[0])
        target["rawPosY"] = float(current[1])
        target["rawPosZ"] = float(current[2])
        target["posX"] = float(smoothed[0])
        target["posY"] = float(smoothed[1])
        target["posZ"] = float(smoothed[2])
        target["smoothed"] = True

        return target

    def remove_duplicates(self, targets):
        if len(targets) <= 1:
            return targets

        # Ưu tiên target có nhiều point support hơn.
        # Nếu bằng nhau, ưu tiên target có humanScore cao hơn, sau đó tốc độ cao hơn.
        sorted_targets = sorted(
            targets,
            key=lambda t: (
                t.get("supportPointCount", 0),
                t.get("humanScore", 0.0),
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

    def cleanup_missing_ids(self, current_ids):
        old_ids = set(self.missing_count.keys()) | set(self.confirm_count.keys()) | set(self.smoothed_position.keys())

        for tid in list(old_ids):
            if tid in current_ids:
                continue

            self.missing_count[tid] = self.missing_count.get(tid, 0) + 1

            if self.missing_count[tid] > self.max_missing_frames:
                self.missing_count.pop(tid, None)
                self.last_seen_frame.pop(tid, None)
                self.confirm_count.pop(tid, None)
                self.smoothed_position.pop(tid, None)

    def update(self, targets, point_cloud, frame_number=None):
        if targets is None:
            targets = []

        filtered_targets = []
        current_ids = set()

        for target in targets:
            target = dict(target)
            tid = target.get("tid", -1)
            current_ids.add(tid)

            supported = self.is_target_supported(target, point_cloud)
            target["ghostFiltered"] = not supported

            if supported:
                self.missing_count[tid] = 0
                if frame_number is not None:
                    self.last_seen_frame[tid] = frame_number

                if self.is_confirmed(target, supported):
                    target = self.smooth_target(target)
                    filtered_targets.append(target)
            else:
                self.confirm_count[tid] = 0
                self.missing_count[tid] = self.missing_count.get(tid, 0) + 1
                target["missingFrames"] = self.missing_count[tid]

                if not self.drop_unsupported_immediately:
                    if self.missing_count[tid] <= self.max_missing_frames:
                        # Vẫn giữ tạm target cũ nhưng dùng vị trí đã smooth nếu có.
                        target = self.smooth_target(target)
                        filtered_targets.append(target)
                    else:
                        self.smoothed_position.pop(tid, None)

        self.cleanup_missing_ids(current_ids)
        filtered_targets = self.remove_duplicates(filtered_targets)

        return filtered_targets
