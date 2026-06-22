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

import time
import numpy as np
from settings import *
from fall_detector import FallDetector

try:
    from sklearn.cluster import DBSCAN as SklearnDBSCAN
    HAS_SKLEARN = True
except Exception:
    SklearnDBSCAN = None
    HAS_SKLEARN = False

try:
    from scipy.optimize import linear_sum_assignment as scipy_linear_sum_assignment
    HAS_SCIPY = True
except Exception:
    scipy_linear_sum_assignment = None
    HAS_SCIPY = False

def numpy_linear_sum_assignment(cost_matrix):
    """
    Bản triển khai Kuhn-Munkres (Hungarian) hoàn toàn bằng pure-NumPy.
    Tìm gán ghép cặp tối ưu toàn cục với tổng chi phí nhỏ nhất.
    """
    cost_matrix = np.atleast_2d(cost_matrix).astype(float)
    h, w = cost_matrix.shape
    transposed = False
    if h > w:
        cost_matrix = cost_matrix.T
        h, w = cost_matrix.shape
        transposed = True

    # 1. Trừ giá trị nhỏ nhất của mỗi hàng/cột
    C = cost_matrix.copy()
    for i in range(h):
        C[i] -= np.min(C[i])
    for j in range(w):
        C[:, j] -= np.min(C[:, j])

    # Khởi tạo ma trận đánh dấu (1: Star - gán, 2: Prime - nháp)
    marked = np.zeros((h, w), dtype=int)
    row_covered = np.zeros(h, dtype=bool)
    col_covered = np.zeros(w, dtype=bool)

    # Đánh dấu Star các số không độc lập ban đầu
    for i in range(h):
        for j in range(w):
            if C[i, j] == 0 and not row_covered[i] and not col_covered[j]:
                marked[i, j] = 1
                row_covered[i] = True
                col_covered[j] = True

    row_covered[:] = False
    col_covered[:] = False

    def clear_covers():
        row_covered[:] = False
        col_covered[:] = False

    # Vòng lặp các bước Hungarian
    while True:
        # Che phủ các cột chứa Star zero
        for i in range(h):
            for j in range(w):
                if marked[i, j] == 1:
                    col_covered[j] = True

        # Nếu tất cả các hàng đều có Star (đã che đủ cột), đạt gán tối ưu
        if np.sum(col_covered) >= h:
            break

        # Tìm các số không chưa che phủ để gán Prime
        finished = False
        while not finished:
            zero_row, zero_col = -1, -1
            for i in range(h):
                if not row_covered[i]:
                    for j in range(w):
                        if not col_covered[j] and C[i, j] == 0:
                            zero_row, zero_col = i, j
                            break
                if zero_row != -1:
                    break

            # Nếu không còn số không chưa bị che phủ, tìm min giá trị chưa che phủ để điều chỉnh
            if zero_row == -1:
                min_val = np.inf
                for i in range(h):
                    if not row_covered[i]:
                        for j in range(w):
                            if not col_covered[j] and C[i, j] < min_val:
                                min_val = C[i, j]

                if np.isinf(min_val) or min_val == 0:
                    finished = True
                    break

                for i in range(h):
                    if row_covered[i]:
                        C[i] += min_val
                for j in range(w):
                    if not col_covered[j]:
                        C[:, j] -= min_val
                continue

            # Đánh dấu Prime số không tìm được
            marked[zero_row, zero_col] = 2

            # Tìm xem hàng này có Star zero nào không
            star_col = -1
            for j in range(w):
                if marked[zero_row, j] == 1:
                    star_col = j
                    break

            if star_col != -1:
                row_covered[zero_row] = True
                col_covered[star_col] = False
            else:
                # Nếu hàng không có Star zero, xây dựng đường đi xen kẽ (Augmenting Path)
                path = [(zero_row, zero_col)]
                while True:
                    # Tìm Star zero trong cột của Prime zero cuối cùng
                    r_star = -1
                    c_star = path[-1][1]
                    for i in range(h):
                        if marked[i, c_star] == 1:
                            r_star = i
                            break
                    if r_star == -1:
                        break
                    path.append((r_star, c_star))

                    # Tìm Prime zero trong hàng của Star zero vừa tìm
                    c_prime = -1
                    r_prime = path[-1][0]
                    for j in range(w):
                        if marked[r_prime, j] == 2:
                            c_prime = j
                            break
                    path.append((r_prime, c_prime))

                # Đảo ngược dấu: Star -> Unstar, Prime -> Star
                for r, c in path:
                    if marked[r, c] == 1:
                        marked[r, c] = 0
                    elif marked[r, c] == 2:
                        marked[r, c] = 1

                marked[marked == 2] = 0
                clear_covers()
                break

    # Trích xuất chỉ số gán cặp
    row_ind, col_ind = [], []
    for i in range(h):
        for j in range(w):
            if marked[i, j] == 1:
                row_ind.append(i)
                col_ind.append(j)

    row_ind = np.array(row_ind)
    col_ind = np.array(col_ind)

    if transposed:
        return col_ind, row_ind
    else:
        return row_ind, col_ind

def linear_sum_assignment(cost_matrix):
    """Bọc bộ giải Hungarian toàn cục thích ứng tự động."""
    if HAS_SCIPY:
        try:
            return scipy_linear_sum_assignment(cost_matrix)
        except Exception:
            pass
    return numpy_linear_sum_assignment(cost_matrix)



# ============================================================
# 3D CONSTANT VELOCITY KALMAN FILTER (Version 8.0)
# ============================================================

class KalmanTracker3D:
    def __init__(self, init_pos, dt=0.05):
        self.dt = dt
        # Trạng thái x = [px, py, pz, vx, vy, vz]^T
        self.x = np.array([init_pos[0], init_pos[1], init_pos[2], 0.0, 0.0, 0.0], dtype=np.float32)
        
        # Ma trận hiệp phương sai sai số trạng thái P
        self.P = np.eye(6, dtype=np.float32) * 0.1
        self.P[3:, 3:] *= 1.0  # Tăng độ bất định ban đầu của vận tốc
        
        # Ma trận chuyển trạng thái F
        self.F = np.eye(6, dtype=np.float32)
        
        # Ma trận đo lường H (Chỉ đo vị trí 3D từ Centroid)
        self.H = np.zeros((3, 6), dtype=np.float32)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0
        
        # Cấu hình nhiễu đo lường R
        r_xy = KALMAN_MEASUREMENT_NOISE_XY if 'KALMAN_MEASUREMENT_NOISE_XY' in globals() else 0.08
        r_z = KALMAN_MEASUREMENT_NOISE_Z if 'KALMAN_MEASUREMENT_NOISE_Z' in globals() else 0.15
        self.R = np.diag([r_xy**2, r_xy**2, r_z**2]).astype(np.float32)
        
        # Cấu hình nhiễu hệ thống Q
        self.q_acc = KALMAN_PROCESS_NOISE_ACC if 'KALMAN_PROCESS_NOISE_ACC' in globals() else 0.20
        
        self.update_dt(dt)


    def update_dt(self, dt):
        self.dt = dt
        self.F[0, 3] = dt
        self.F[1, 4] = dt
        self.F[2, 5] = dt
        self._calc_Q()

    def _calc_Q(self):
        dt = self.dt
        q = self.q_acc ** 2
        Q_pos = (dt**3)/3.0 * q
        Q_vel = dt * q
        Q_cross = (dt**2)/2.0 * q
        
        self.Q = np.zeros((6, 6), dtype=np.float32)
        for i in range(3):
            self.Q[i, i] = Q_pos
            self.Q[i+3, i+3] = Q_vel
            self.Q[i, i+3] = Q_cross
            self.Q[i+3, i] = Q_cross

    def predict(self):
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return self.x[:3]

    def update(self, measurement):
        z = np.array(measurement, dtype=np.float32)
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        
        self.x = self.x + np.dot(K, y)
        self.P = np.dot(np.eye(6, dtype=np.float32) - np.dot(K, self.H), self.P)
        return self.x


# ============================================================
# STATIONARY PEOPLE TRACKING HELPER FUNCTIONS (Version 20.0)
# ============================================================

def calculate_cluster_doppler_std(cluster_points):
    """
    Tính toán độ lệch chuẩn của Doppler (Doppler Variance) trong một cụm.
    Sử dụng để phát hiện dao động sinh học do nhịp thở (micro-motion) của người đứng yên.
    """
    if cluster_points is None or len(cluster_points) == 0:
        return 0.0
    # Doppler nằm ở cột thứ 4 (chỉ số 3) của mây điểm [x, y, z, doppler, snr]
    return float(np.std(cluster_points[:, 3]))

def calculate_breathing_likelihood_boost(doppler_std, base_boost=1.5):
    """
    Trả về hệ số nhân khuếch đại cho Stop Model nếu biến thiên Doppler
    nằm trong khoảng hô hấp sinh học thực tế (0.02 đến 0.09 m/s).
    """
    if 0.02 <= doppler_std <= 0.09:
        return base_boost
    return 1.0

def apply_zero_velocity_update(state_vector, threshold=0.06):
    """
    Áp dụng Zero Velocity Update (ZUPT) để khóa cứng vận tốc về 0.0
    nếu vận tốc tổng hợp của mục tiêu thấp hơn ngưỡng threshold.
    """
    vx, vy, vz = state_vector[3], state_vector[4], state_vector[5]
    speed = np.sqrt(vx**2 + vy**2 + vz**2)
    if speed < threshold:
        state_vector[3:6] = 0.0
        return True
    return False


# ============================================================
# 3D INTERACTING MULTIPLE MODEL (IMM) FILTER (Version 18.0)
# ============================================================

class IMMTracker3D:
    def __init__(self, init_pos, dt=0.05):
        self.dt = dt
        
        # Model 0: Constant Velocity (CV) - nhiễu hệ thống cao cho vận động chuyển động
        self.cv_filter = KalmanTracker3D(init_pos, dt)
        self.cv_filter.q_acc = KALMAN_PROCESS_NOISE_ACC if 'KALMAN_PROCESS_NOISE_ACC' in globals() else 0.20
        self.cv_filter.update_dt(dt)
        
        # Model 1: Stop Model (Zero-Velocity) - nhiễu hệ thống siêu thấp để khóa im vị trí
        self.stop_filter = KalmanTracker3D(init_pos, dt)
        self.stop_filter.q_acc = 0.01  # Nhiễu hệ thống cực bé để tránh nhảy rung hộp
        self.stop_filter.update_dt(dt)
        
        # Giảm ảnh hưởng vận tốc của stop filter lên vị trí để chống trôi hoàn toàn
        self.stop_filter.F[0, 3] = dt * 0.05
        self.stop_filter.F[1, 4] = dt * 0.05
        self.stop_filter.F[2, 5] = dt * 0.05
        self.stop_filter._calc_Q()
        
        self.filters = [self.cv_filter, self.stop_filter]
        
        # Xác suất ban đầu cho mỗi mô hình [CV, STOP]
        self.mu = np.array([0.5, 0.5], dtype=np.float32)
        
        # Ma trận xác suất chuyển đổi giữa các mô hình (M1: CV, M2: Stop)
        if 'IMM_TRANSITION_MATRIX' in globals():
            self.p_trans = np.array(IMM_TRANSITION_MATRIX, dtype=np.float32)
        else:
            self.p_trans = np.array([[0.92, 0.08], [0.12, 0.88]], dtype=np.float32)
            
        # Trạng thái kết hợp tổng hợp đầu ra (để tương thích ngược với Kalman single)
        self.x = self.cv_filter.x.copy()
        self.P = self.cv_filter.P.copy()
        
    def update_dt(self, dt):
        self.dt = dt
        for f in self.filters:
            f.update_dt(dt)
        
        # Khóa chặn thêm ma trận F của Stop filter
        self.stop_filter.F[0, 3] = dt * 0.05
        self.stop_filter.F[1, 4] = dt * 0.05
        self.stop_filter.F[2, 5] = dt * 0.05
        self.stop_filter._calc_Q()
        
    def predict(self):
        # 1. IMM Interaction (Mixing)
        # Normalization factor: c_j = sum_{i} p_ij * mu_i
        c = np.dot(self.p_trans.T, self.mu)
        c = np.where(c < 1e-5, 1e-5, c)
        
        # Mixing probability: mu_{i|j} = p_ij * mu_i / c_j
        mu_mix = np.zeros((2, 2), dtype=np.float32)
        for j in range(2):
            mu_mix[:, j] = self.p_trans[:, j] * self.mu / c[j]
            
        # Trộn các trạng thái x0 và P0
        x_mixed = []
        P_mixed = []
        
        for j in range(2):
            xj = np.zeros(6, dtype=np.float32)
            for i in range(2):
                xj += mu_mix[i, j] * self.filters[i].x
            x_mixed.append(xj)
            
            Pj = np.zeros((6, 6), dtype=np.float32)
            for i in range(2):
                diff = self.filters[i].x - xj
                Pj += mu_mix[i, j] * (self.filters[i].P + np.outer(diff, diff))
            P_mixed.append(Pj)
            
        # Cập nhật trạng thái trộn trước khi chạy Predict
        for j in range(2):
            self.filters[j].x = x_mixed[j]
            self.filters[j].P = P_mixed[j]
            
        # 2. Dự báo song song (Prediction)
        for f in self.filters:
            f.predict()
            
        # Kết hợp trạng thái dự báo chung
        self.x = np.zeros(6, dtype=np.float32)
        for j in range(2):
            self.x += c[j] * self.filters[j].x
            
        self.P = np.zeros((6, 6), dtype=np.float32)
        for j in range(2):
            diff = self.filters[j].x - self.x
            self.P += c[j] * (self.filters[j].P + np.outer(diff, diff))
            
        return self.x[:3]
        
    def update(self, measurement, doppler_std=None):
        z = np.array(measurement, dtype=np.float32)
        likelihood = np.zeros(2, dtype=np.float32)
        
        # 3. Cập nhật song song từng Kalman & tính Likelihood Gaussian
        for j in range(2):
            H = self.filters[j].H
            R = self.filters[j].R
            
            # Innovation vector: nu = z - H*x
            nu = z - np.dot(H, self.filters[j].x)
            
            # Innovation Covariance: S = H*P*H^T + R
            S = np.dot(np.dot(H, self.filters[j].P), H.T) + R
            
            # Cập nhật Kalman chính thức
            self.filters[j].update(measurement)
            
            # Likelihood L_j = 1/sqrt((2pi)^3 * |S|) * exp(-0.5 * nu^T * S^-1 * nu)
            det_S = np.linalg.det(S)
            if det_S < 1e-9:
                det_S = 1e-9
                
            inv_S = np.linalg.inv(S)
            exponent = -0.5 * np.dot(np.dot(nu.T, inv_S), nu)
            exponent = np.clip(exponent, -50.0, 0.0) # Tránh tràn số mũ
            
            likelihood[j] = (1.0 / np.sqrt(((2.0 * np.pi) ** 3) * det_S)) * np.exp(exponent)
            
        # Áp dụng Doppler Variance Breathing Boost cho Stop Model (Model 1) (Version 20.0)
        if doppler_std is not None:
            boost_factor = calculate_breathing_likelihood_boost(doppler_std)
            likelihood[1] *= boost_factor
            
        # 4. Cập nhật xác suất mô hình (Probability Update)
        c = np.dot(self.p_trans.T, self.mu)
        c = np.where(c < 1e-5, 1e-5, c)
        
        numerator = c * likelihood
        sum_numerator = np.sum(numerator)
        
        if sum_numerator > 1e-15:
            self.mu = numerator / sum_numerator
        else:
            self.mu = c / np.sum(c)
            
        # Giới hạn mu trong dải an toàn để phản ứng nhanh, tránh bão hòa mô hình
        self.mu = np.clip(self.mu, 0.01, 0.99)
        self.mu /= np.sum(self.mu)
        
        # 5. Kết hợp trạng thái tổng hợp đầu ra (Combination)
        self.x = np.zeros(6, dtype=np.float32)
        for j in range(2):
            self.x += self.mu[j] * self.filters[j].x
            
        # Áp dụng ZUPT (Zero Velocity Update) để khóa trôi dạt vận tốc (Version 20.0)
        if apply_zero_velocity_update(self.x):
            for f in self.filters:
                apply_zero_velocity_update(f.x)
            
        self.P = np.zeros((6, 6), dtype=np.float32)
        for j in range(2):
            diff = self.filters[j].x - self.x
            self.P += self.mu[j] * (self.filters[j].P + np.outer(diff, diff))
            
        return self.x


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
    
    # Flip X perspective if enabled (User Right = Screen Right)
    if FLIP_X_PERSPECTIVE if 'FLIP_X_PERSPECTIVE' in globals() else False:
        transformed[:, 0] = -points[:, 0]
    
    # Rotation around X-axis (pitch) and translation along Z (mount height) - Pitch DOWN (Version 16.0)
    transformed[:, 1] = y_radar * np.cos(theta) + z_radar * np.sin(theta)
    transformed[:, 2] = -y_radar * np.sin(theta) + z_radar * np.cos(theta) + h
    
    return transformed


def transform_target_to_room_coordinates(target):
    """Transform a firmware target's coordinates to room coordinates."""
    if not (ENABLE_COORD_TRANSFORM if 'ENABLE_COORD_TRANSFORM' in globals() else False):
        return target
        
    transformed = dict(target)
    
    # Tự động đảo ngược trục X của mục tiêu và vận tốc, gia tốc tương ứng (X-flip)
    if FLIP_X_PERSPECTIVE if 'FLIP_X_PERSPECTIVE' in globals() else False:
        transformed["posX"] = -target.get("posX", 0.0)
        transformed["velX"] = -target.get("velX", 0.0)
        transformed["accX"] = -target.get("accX", 0.0)
        
    # Do radar chip đã thực hiện phép xoay tọa độ nghiêng và tịnh tiến chiều cao trực tiếp ở tầng phần cứng
    # (thông qua lệnh cấu hình động sensorPosition), ta không áp dụng lại phép quay trong Python nữa
    # để tránh sai lệch xoay kép (double transformation).
    transformed["posY"] = float(target.get("posY", 0.0))
    transformed["posZ"] = float(target.get("posZ", 0.0))
    
    return transformed




# ============================================================
# ROI + QUALITY FILTER
# ============================================================

def build_human_point_mask(points, confirmed_track_positions=[]):
    """
    Build mask for points that can realistically belong to a person.

    Columns expected:
        x, y, z, doppler, snr/intensity
    """
    points = ensure_point_cloud_shape(points)

    if len(points) == 0:
        return np.zeros((0,), dtype=bool)

    # Chuẩn hóa danh sách bảo vệ: chấp nhận cả [pos] và [(pos, radius)] (Version 22.0)
    normalized_tracks = []
    default_r = STATIC_CLUTTER_POINT_PROTECTION_RADIUS if 'STATIC_CLUTTER_POINT_PROTECTION_RADIUS' in globals() else 1.2
    for item in confirmed_track_positions:
        if isinstance(item, tuple) and len(item) == 2 and not isinstance(item[0], (int, float, np.floating)):
            normalized_tracks.append(item)
        else:
            normalized_tracks.append((item, default_r))

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
            # Thuật toán bù độ nhạy rìa quét biên (Version 13.0)
            if ENABLE_ANTENNA_EDGE_COMPENSATION if 'ENABLE_ANTENNA_EDGE_COMPENSATION' in globals() else True:
                azimuth_rad = np.abs(np.arctan2(x, y))
                azimuth_deg = np.degrees(azimuth_rad)
                
                edge_boundary = ANTENNA_EDGE_BOUNDARY_DEG if 'ANTENNA_EDGE_BOUNDARY_DEG' in globals() else 40.0
                max_comp = ANTENNA_EDGE_MAX_COMP_SCALE if 'ANTENNA_EDGE_MAX_COMP_SCALE' in globals() else 0.6
                
                comp_factor = 1.0 + max_comp * np.clip((azimuth_deg - edge_boundary) / 20.0, 0.0, 1.0)
                snr_compensated = snr * comp_factor
            else:
                snr_compensated = snr

            if ENABLE_DISTANCE_ADAPTIVE_SNR if 'ENABLE_DISTANCE_ADAPTIVE_SNR' in globals() else True:
                boundary = SNR_BOUNDARY_DISTANCE if 'SNR_BOUNDARY_DISTANCE' in globals() else 1.5
                near_snr = SNR_MIN_NEAR if 'SNR_MIN_NEAR' in globals() else 6.0
                far_snr = SNR_MIN_FAR if 'SNR_MIN_FAR' in globals() else 4.0
                dynamic_min_snr = np.where(y < boundary, near_snr, far_snr)
                min_snr_limit = dynamic_min_snr
            else:
                min_snr_limit = MIN_POINT_SNR

            if (ENABLE_MICRO_MOTION_ZONE if 'ENABLE_MICRO_MOTION_ZONE' in globals() else True) and len(normalized_tracks) > 0:
                in_protection_zone = np.zeros(len(points), dtype=bool)
                prot_r = MICRO_MOTION_ZONE_RADIUS if 'MICRO_MOTION_ZONE_RADIUS' in globals() else 0.80
                for track_pos, _ in normalized_tracks:
                    dist_xy = np.sqrt((x - track_pos[0])**2 + (y - track_pos[1])**2)
                    in_protection_zone |= (dist_xy <= prot_r)
                
                micro_snr = MICRO_MOTION_MIN_SNR if 'MICRO_MOTION_MIN_SNR' in globals() else 1.0
                if isinstance(min_snr_limit, np.ndarray):
                    effective_min_snr = np.where(in_protection_zone, micro_snr, min_snr_limit)
                else:
                    effective_min_snr = np.where(in_protection_zone, micro_snr, float(min_snr_limit))
            else:
                effective_min_snr = min_snr_limit

            mask &= (snr_compensated >= effective_min_snr) & (snr_compensated <= MAX_POINT_SNR)

    if ENABLE_DOPPLER_OUTLIER_FILTER:
        mask &= np.abs(doppler) <= MAX_ABS_DOPPLER

    # Doppler static clutter suppression at point level (Version 22.0 - Adaptive radius per track)
    if ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER if 'ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER' in globals() else True:
        dop_thresh = STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD if 'STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD' in globals() else 0.015
        near_zero_doppler = np.abs(doppler) < dop_thresh
        if len(normalized_tracks) > 0 and np.any(near_zero_doppler):
            keep_static_point = np.zeros(len(points), dtype=bool)
            for track_pos, custom_r in normalized_tracks:
                dist_xy = np.sqrt((x - track_pos[0])**2 + (y - track_pos[1])**2)
                keep_static_point |= (dist_xy <= custom_r)
            mask &= (~near_zero_doppler | keep_static_point)
        elif np.any(near_zero_doppler):
            mask &= ~near_zero_doppler

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

    # Cluster validation: SNR check
    min_avg_snr = MIN_AVG_SNR if 'MIN_AVG_SNR' in globals() else 5.0
    if avg_snr < min_avg_snr:
        is_shape_valid = False

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


def profile_target_posture(cluster):
    """
    Phân tích tư thế con người (Đứng, Ngồi, Nằm/Ngã sàn) dọc trục Z của mây điểm.
    Chạy ở chế độ hiển thị thử nghiệm trên đồ thị 3D.
    """
    cluster = ensure_point_cloud_shape(cluster)
    if len(cluster) == 0:
        return "STANDING"
        
    z = cluster[:, 2]
    x = cluster[:, 0]
    y = cluster[:, 1]
    
    min_z = float(np.min(z))
    max_z = float(np.max(z))
    
    # Tính toán phân tán ngang (width X, depth Y)
    width_x = float(np.max(x) - np.min(x)) if len(cluster) > 1 else 0.0
    depth_y = float(np.max(y) - np.min(y)) if len(cluster) > 1 else 0.0
    horizontal_spread = max(width_x, depth_y)
    
    # Chia cụm điểm thành 3 phân vùng dọc trục Z:
    # 1. Lower Zone: 0.15m -> 0.60m (Chân/Sàn)
    # 2. Middle Zone: 0.60m -> 1.20m (Bụng/Thân)
    # 3. Upper Zone: 1.20m -> 2.20m (Ngực/Đầu)
    lower_mask = (z >= 0.15) & (z < 0.60)
    middle_mask = (z >= 0.60) & (z < 1.20)
    upper_mask = (z >= 1.20) & (z <= 2.20)
    
    lower_pts = cluster[lower_mask]
    middle_pts = cluster[middle_mask]
    upper_pts = cluster[upper_mask]
    
    lower_count = len(lower_pts)
    middle_count = len(middle_pts)
    upper_count = len(upper_pts)
    total_count = len(cluster)
    
    # 1. Thử nghiệm tư thế Nằm/Ngã (LYING/FALLEN):
    # Đa phần điểm mây bẹt dưới thấp Z < 0.60m và dải phân bố ngang rộng > 0.85m
    # HOẶC chiều cao cực đại quá thấp Z < 0.60m (không thể là đứng hay ngồi)
    if ((lower_count / total_count > 0.85 or max_z < 0.70) and horizontal_spread > 0.85) or (max_z < 0.60):
        return "LYING/FALLEN"
        
    # 2. Thử nghiệm tư thế Ngồi (SITTING):
    # Cụm điểm chủ yếu ở phân vùng thấp & giữa, rỗng phần cao và chiều cao tối đa trung bình [0.60m - 1.30m]
    if 0.60 <= max_z < 1.30 and upper_count / total_count < 0.10:
        return "SITTING"
        
    # 3. Thử nghiệm tư thế Đứng (STANDING):
    # Chiều cao cao (>1.30m) và mây điểm thẳng đứng tương đối chặt chẽ
    if max_z >= 1.30:
        if lower_count >= 2 and middle_count >= 2 and upper_count >= 1:
            lower_center = np.mean(lower_pts[:, 0:2], axis=0)
            middle_center = np.mean(middle_pts[:, 0:2], axis=0)
            upper_center = np.mean(upper_pts[:, 0:2], axis=0)
            
            # Tính độ lệch trục đứng giữa các phân vùng
            dev_low_mid = np.sqrt(np.sum((lower_center - middle_center)**2))
            dev_mid_up = np.sqrt(np.sum((middle_center - upper_center)**2))
            
            if max(dev_low_mid, dev_mid_up) < 0.45:
                return "STANDING"
            else:
                return "SITTING"
        return "STANDING"
        
    if max_z < 0.60:
        return "LYING/FALLEN"
    return "STANDING"


def cluster_to_virtual_target(cluster, cluster_id):
    center = np.mean(cluster[:, 0:3], axis=0)
    score, features = score_human_cluster(cluster)
    posture = profile_target_posture(cluster)

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
        "posture": posture,
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
    Giải quyết triệt để lỗi nhảy ID ngẫu nhiên của DBSCAN, tích hợp bộ lọc 3D IMM/Kalman và quản lý trạng thái.
    """
    def __init__(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE # 1000
        self.active_tracks = {} # tid -> { "kalman": IMMTracker3D|KalmanTracker3D, "state": "tentative"|"confirmed", "hit_count": int, "miss_count": int, "features": dict }
        self.last_time = None
        self.track_motion_history = {} # tid -> has_moved (bool) (Version 24.0)
        self.hw_track_scores = {} # tid -> last_human_score (float) (Version 24.0)
        self.hw_track_postures = {} # tid -> last_posture (str)
        self.fall_detector = FallDetector()

    def reset(self):
        self.next_virtual_id = VIRTUAL_TARGET_ID_BASE
        self.active_tracks.clear()
        self.last_time = None
        self.track_motion_history.clear()
        self.hw_track_scores.clear()
        self.hw_track_postures.clear()
        self.fall_detector.reset()

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

        # Quyết định cổng bảo vệ thích nghi dựa trên Dynamic State Locking (v24.0)
        confirmed_positions = []
        
        # A. Xử lý Virtual Tracks
        for tid, track_info in self.active_tracks.items():
            if track_info["state"] == "confirmed":
                k_state = track_info["kalman"].x
                pos = k_state[:2]
                speed = np.sqrt(k_state[3]**2 + k_state[4]**2 + k_state[5]**2)
                score = track_info.get("score", 0.0)
                posture = track_info.get("posture", "STANDING")
                
                # Cập nhật và lưu giữ trạng thái đã từng di chuyển
                if speed >= 0.15:
                    self.track_motion_history[tid] = True
                
                has_moved = self.track_motion_history.get(tid, False)
                is_confident_human = has_moved or (score > 40.0)
                
                # Quyết định bán kính bảo vệ điểm tĩnh
                if posture == "LYING/FALLEN" or k_state[2] < 0.95:
                    r_prot = 1.30
                    confirmed_positions.append((pos, r_prot))
                elif speed >= 0.15:
                    r_prot = 0.85
                    confirmed_positions.append((pos, r_prot))
                elif is_confident_human:
                    r_prot = 0.45
                    confirmed_positions.append((pos, r_prot))
                else:
                    # Đóng cổng bảo vệ cho vật thể tĩnh hoặc không đáng tin cậy
                    pass
                    
        # B. Xử lý Hardware Raw Targets
        for target in raw_targets:
            if "posX" in target and "posY" in target:
                tid = target.get("tid", -1)
                vx = target.get("velX", 0.0)
                vy = target.get("velY", 0.0)
                vz = target.get("velZ", 0.0)
                speed = np.sqrt(vx**2 + vy**2 + vz**2)
                score = self.hw_track_scores.get(tid, 0.0)
                pos = np.array([target["posX"], target["posY"]], dtype=np.float32)
                posture = self.hw_track_postures.get(tid, "STANDING")
                
                if speed >= 0.15:
                    self.track_motion_history[tid] = True
                    
                has_moved = self.track_motion_history.get(tid, False)
                is_confident_human = has_moved or (score > 40.0)
                
                tz = target.get("posZ", 1.2)
                if posture == "LYING/FALLEN" or tz < 0.95:
                    r_prot = 1.30
                    confirmed_positions.append((pos, r_prot))
                elif speed >= 0.15:
                    r_prot = 0.85
                    confirmed_positions.append((pos, r_prot))
                elif is_confident_human:
                    r_prot = 0.45
                    confirmed_positions.append((pos, r_prot))


        point_cloud = ensure_point_cloud_shape(point_cloud)
        roi_mask = build_human_point_mask(point_cloud, confirmed_positions)
        roi_points = point_cloud[roi_mask]
        clusters = cluster_pointcloud(roi_points)

        final_targets = []
        cluster_debug = []
        current_frame_tids = set() # (Version 24.0)

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
            
            # Tính toán biến động Doppler của cụm độc lập cho target phần cứng (Version 20.0)
            doppler_std = calculate_cluster_doppler_std(associated_points)
            features["doppler_std"] = doppler_std
            
            target["supportPointCount"] = int(len(associated_points))
            target["humanScore"] = score
            target["clusterFeatures"] = features
            target["source"] = "firmware_target"
            target["posture"] = profile_target_posture(associated_points)

            # Lưu thông tin độ tin cậy và theo dõi ID phần cứng (Version 24.0)
            self.hw_track_scores[tid] = score
            current_frame_tids.add(tid)

            # Lọc nhiễu cụm sàn dựa trên đặc trưng hình học và điểm tin cậy (is_shape_valid)
            height_z = features.get("height_z", 0.0)
            max_z = features.get("max_z", 0.0)
            is_shape_valid = features.get("is_shape_valid", False)
            
            # Nếu cụm quá thấp hoặc quá dẹt sát sàn, loại bỏ hoàn toàn để tránh nhiễu mặt đất/vật dụng
            if height_z < 0.12 or max_z < 0.08:
                continue

            # Quyết định giữ lại target phần cứng dựa trên tính hợp lệ của hình thể
            if is_shape_valid:
                # Nếu hình thể hợp lệ, giữ lại theo ngưỡng cấu hình thông thường
                keep_target = (score >= HUMAN_SCORE_TARGET_THRESHOLD) or (len(associated_points) >= GHOST_MIN_SUPPORT_POINTS)
            else:
                # Nếu hình thể không hợp lệ, yêu cầu điểm tin cậy cao hơn hẳn (>= 42.0) để loại bỏ nhiễu lốm đốm
                keep_target = (score >= 42.0)
                
            if keep_target:
                final_targets.append(target)

        # 3) Dự báo trạng thái Kalman/IMM (Predict Step)
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
            
            # Tính toán biến động Doppler của cụm độc lập (Version 20.0)
            doppler_std = calculate_cluster_doppler_std(cluster)
            features["doppler_std"] = doppler_std

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

        # 5) Data Association sử dụng Hungarian tối ưu toàn cục (hoặc GNN fallback)
        matched_cluster_indices = set()
        matched_tids = set()
        assignments = {}

        use_hungarian = ENABLE_HUNGARIAN_ASSOCIATION if 'ENABLE_HUNGARIAN_ASSOCIATION' in globals() else True

        if self.active_tracks and valid_centroids:
            if use_hungarian:
                track_tids = list(self.active_tracks.keys())
                num_tracks = len(track_tids)
                num_centroids = len(valid_centroids)
                
                # Khởi tạo ma trận chi phí
                cost_matrix = np.zeros((num_tracks, num_centroids), dtype=np.float32)
                
                w_dist = HUNGARIAN_DIST_WEIGHT if 'HUNGARIAN_DIST_WEIGHT' in globals() else 0.70
                w_vel = HUNGARIAN_VEL_WEIGHT if 'HUNGARIAN_VEL_WEIGHT' in globals() else 0.20
                w_maha = HUNGARIAN_MAHALANOBIS_WEIGHT if 'HUNGARIAN_MAHALANOBIS_WEIGHT' in globals() else 0.10
                
                for i, tid in enumerate(track_tids):
                    track_info = self.active_tracks[tid]
                    pred_pos = predictions[tid]
                    
                    for j, cc in enumerate(valid_centroids):
                        # a. Khoảng cách hình học 2D XY
                        dist_xy = float(np.sqrt((cc[0] - pred_pos[0])**2 + (cc[1] - pred_pos[1])**2))
                        
                        # b. Trọng số sai lệch vận tốc dự kiến (chỉ tính XY)
                        t_vel = track_info["kalman"].x[3:5]
                        prev_pos = track_info["kalman"].x[:2]
                        est_displacement = cc[:2] - prev_pos
                        expected_displacement = t_vel * dt
                        vel_diff = float(np.sqrt(np.sum((est_displacement - expected_displacement)**2)))
                        
                        # c. Khoảng cách Mahalanobis sử dụng Innovation Covariance S của bộ lọc (chỉ tính XY)
                        nu = cc[:2] - pred_pos[:2]
                        P_pos = track_info["kalman"].P[:2, :2]
                        R = track_info["kalman"].filters[0].R[:2, :2] if isinstance(track_info["kalman"], IMMTracker3D) else track_info["kalman"].R[:2, :2]
                        S = P_pos + R
                        try:
                            inv_S = np.linalg.inv(S)
                            maha_dist = float(np.sqrt(np.dot(np.dot(nu.T, inv_S), nu)))
                        except Exception:
                            maha_dist = dist_xy
                            
                        cost_matrix[i, j] = w_dist * dist_xy + w_vel * vel_diff + w_maha * maha_dist
                
                # Giải thuật Hungarian optimal assignment
                row_ind, col_ind = linear_sum_assignment(cost_matrix)
                assoc_radius = VIRTUAL_TRACKER_ASSOCIATION_RADIUS
                
                for r, c in zip(row_ind, col_ind):
                    tid = track_tids[r]
                    cc = valid_centroids[c]
                    pred_pos = predictions[tid]
                    dist_xy = float(np.sqrt((cc[0] - pred_pos[0])**2 + (cc[1] - pred_pos[1])**2))
                    
                    if dist_xy <= assoc_radius:
                        matched_cluster_indices.add(c)
                        matched_tids.add(tid)
                        assignments[c] = tid
            else:
                # Fallback GNN: Nearest Neighbor tham lam giống version cũ
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

        # 6) Tạo mới hoặc cập nhật bộ lọc IMM/Kalman (Update Step)
        for c_idx, cc in enumerate(valid_centroids):
            score = valid_scores[c_idx]
            features = valid_features[c_idx]
            pt_count = valid_counts[c_idx]

            # Dùng IMM cao cấp nếu bật trong cấu hình
            use_imm = ENABLE_IMM_FILTER if 'ENABLE_IMM_FILTER' in globals() else True

            if c_idx in assignments:
                tid = assignments[c_idx]
                track_info = self.active_tracks[tid]
                
                # Cập nhật IMM / Kalman có kèm theo doppler_std (Version 20.0)
                dop_std = features.get("doppler_std", 0.0)
                if isinstance(track_info["kalman"], IMMTracker3D):
                    track_info["kalman"].update(cc, doppler_std=dop_std)
                else:
                    track_info["kalman"].update(cc)
                track_info["hit_count"] += 1
                track_info["miss_count"] = 0
                track_info["score"] = score
                track_info["features"] = features
                track_info["pt_count"] = pt_count
                track_info["posture"] = profile_target_posture(merged_clusters[c_idx])
                
                # Nâng cấp lên confirmed nếu đủ số frame tích lũy
                if track_info["state"] == "tentative" and track_info["hit_count"] >= TARGET_CONFIRM_FRAMES:
                    track_info["state"] = "confirmed"
            else:
                tid = self.next_virtual_id
                self.next_virtual_id += 1
                
                # Khởi tạo bộ bám vết mới tùy theo cấu hình IMM/Kalman
                tracker_obj = IMMTracker3D(cc, dt) if use_imm else KalmanTracker3D(cc, dt)
                
                self.active_tracks[tid] = {
                    "kalman": tracker_obj,
                    "state": "tentative",
                    "hit_count": 1,
                    "miss_count": 0,
                    "features": features,
                    "score": score,
                    "pt_count": pt_count,
                    "posture": profile_target_posture(merged_clusters[c_idx])
                }

        # 7) Quản lý các track bị mất tích (Dead Reckoning & Deletion)
        for tid in list(self.active_tracks.keys()):
            if tid not in matched_tids:
                track_info = self.active_tracks[tid]
                track_info["miss_count"] += 1
                
                max_miss = GHOST_MAX_MISSING_FRAMES
                if track_info["state"] == "tentative":
                    max_miss = 1  # Tentative biến mất 1 frame là xóa ngay lập tức
                elif track_info["state"] == "confirmed":
                    posture = track_info.get("posture", "STANDING")
                    in_fall_state = False
                    if tid in self.fall_detector.histories:
                        if self.fall_detector.histories[tid].state == "FALLING":
                            in_fall_state = True
                    
                    if posture == "LYING/FALLEN" or in_fall_state:
                        # Tăng mạnh timeout cho target nằm/ngã/đang ngã để tránh mất dấu
                        max_miss = 150 if posture == "LYING/FALLEN" else 50
                    elif ENABLE_ADAPTIVE_TIMEOUT if 'ENABLE_ADAPTIVE_TIMEOUT' in globals() else True:
                        # Nếu tốc độ thấp (đang đứng im), tăng thời gian chờ thích nghi (Version 12.0)
                        k_state = track_info["kalman"].x
                        vx, vy, vz = k_state[3], k_state[4], k_state[5]
                        speed = np.sqrt(vx**2 + vy**2 + vz**2)
                        if speed < 0.25:
                            max_miss = ADAPTIVE_TIMEOUT_STATIONARY_FRAMES if 'ADAPTIVE_TIMEOUT_STATIONARY_FRAMES' in globals() else 35
                
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
                "kalmanTracked": True,
                "posture": track_info.get("posture", "STANDING")
            }

            # Đính kèm xác suất mô hình IMM phục vụ log/debug bên ngoài nếu dùng IMM
            if isinstance(track_info["kalman"], IMMTracker3D):
                virtual_target["immMu"] = [float(val) for val in track_info["kalman"].mu]

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
        
        # Dọn dẹp trạng thái các track đã biến mất hoàn toàn (Version 24.0)
        active_tids = set(self.active_tracks.keys()) | current_frame_tids
        for tid in list(self.track_motion_history.keys()):
            if tid not in active_tids:
                self.track_motion_history.pop(tid, None)
        for tid in list(self.hw_track_scores.keys()):
            if tid not in active_tids:
                self.hw_track_scores.pop(tid, None)
        for tid in list(self.hw_track_postures.keys()):
            if tid not in active_tids:
                self.hw_track_postures.pop(tid, None)

        # Lưu lại tư thế hiện tại của các target phần cứng phục vụ cho frame sau
        for target in final_targets:
            if target.get("source") == "firmware_target":
                tid = target.get("tid")
                if tid is not None:
                    self.hw_track_postures[tid] = target.get("posture", "STANDING")

        # Chạy thuật toán phát hiện ngã (Fall Detection) dựa trên động học và tư thế (kèm mây điểm)
        final_targets = self.fall_detector.update(final_targets, point_cloud, target_index)

        final_targets.sort(key=lambda t: t.get("tid", 0))
        display_point_cloud = roi_points if SHOW_FILTERED_POINT_CLOUD_ONLY else point_cloud

        return final_targets, display_point_cloud, cluster_debug



