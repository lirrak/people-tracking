import numpy as np
import time
import os

class TargetMotionHistory:
    def __init__(self, capacity=40):
        self.capacity = capacity
        self.z_history = []         # Lịch sử posZ
        self.vz_history = []        # Lịch sử velZ (vận tốc đứng dọc)
        self.timestamps = []        # Lịch sử mốc thời gian
        self.postures = []          # Lịch sử tư thế tĩnh
        self.pc_history = []        # Lịch sử mây điểm phục vụ Deep Learning (Version 28.0)
        self.state = "NORMAL"       # Trạng thái ngã: "NORMAL", "FALLING", "FALLEN"
        self.fall_detected_time = None
        self.last_update_time = time.time()

    def update(self, pos_z, vel_z, posture, points=None):
        now = time.time()
        self.z_history.append(pos_z)
        self.vz_history.append(vel_z)
        self.timestamps.append(now)
        self.postures.append(posture)
        if points is not None:
            self.pc_history.append(points)
        self.last_update_time = now

        if len(self.z_history) > self.capacity:
            self.z_history.pop(0)
            self.vz_history.pop(0)
            self.timestamps.pop(0)
            self.postures.pop(0)
            
        if len(self.pc_history) > self.capacity:
            self.pc_history.pop(0)

class FallDetector:
    def __init__(self):
        self.histories = {} # tid -> TargetMotionHistory
        self.use_deep_learning = False
        self.ort_session = None
        
        # Thử nạp cấu hình và mô hình Deep Learning (Version 28.0)
        try:
            from settings import (
                ENABLE_DEEP_FALL_DETECTION, 
                DEEP_FALL_MODEL_PATH, 
                DEEP_FALL_SEQ_LEN, 
                DEEP_FALL_NUM_POINTS
            )
            self.enable_deep = ENABLE_DEEP_FALL_DETECTION
            self.model_path = DEEP_FALL_MODEL_PATH
            self.seq_len = DEEP_FALL_SEQ_LEN
            self.num_points = DEEP_FALL_NUM_POINTS
            
            if self.enable_deep:
                if os.path.exists(self.model_path):
                    import onnxruntime as ort
                    # Cấu hình providers chạy tăng tốc phần cứng NPU
                    available_providers = ort.get_available_providers()
                    providers = []
                    if 'QnnExecutionProvider' in available_providers:
                        providers.append(('QnnExecutionProvider', {
                            'backend_path': '/usr/lib/libQnnHtp.so',
                            'profiling_level': 'off'
                        }))
                    providers.append('CPUExecutionProvider')
                    
                    self.ort_session = ort.InferenceSession(self.model_path, providers=providers)
                    self.use_deep_learning = True
                    print(f"[INFO] Loaded Fall Detection deep learning model from: {self.model_path} with providers {providers}")
                else:
                    print(f"[WARNING] Deep learning model file not found at: {self.model_path}. Fallback to rule-based.")
        except Exception as e:
            print(f"[WARNING] Failed to load deep learning model: {e}. Fallback to rule-based.")

    def reset(self):
        self.histories.clear()

    def resample_points(self, points, target_num_points=32):
        """
        Quy chuẩn cụm điểm về kích thước cố định (target_num_points = 32).
        """
        if points is None or len(points) == 0:
            return np.zeros((target_num_points, 5), dtype=np.float32)
            
        m = len(points)
        if m == target_num_points:
            return points.astype(np.float32)
        elif m < target_num_points:
            # Padding: nhân bản ngẫu nhiên các điểm hiện có
            indices = np.random.choice(m, target_num_points, replace=True)
            return points[indices].astype(np.float32)
        else:
            # Downsampling: Lấy các điểm có SNR lớn nhất (cột index 4) để giữ đặc trưng tốt nhất
            if points.shape[1] > 4:
                order = np.argsort(points[:, 4])
                indices = order[-target_num_points:]
                return points[indices].astype(np.float32)
            else:
                indices = np.random.choice(m, target_num_points, replace=False)
                return points[indices].astype(np.float32)

    def normalize_spatial(self, points):
        """
        Chuẩn hóa không gian: đưa X, Y về tương đối so với trọng tâm, giữ nguyên Z, V, SNR.
        """
        if points is None or len(points) == 0:
            return points
            
        points_norm = points.copy()
        x_c = np.mean(points[:, 0])
        y_c = np.mean(points[:, 1])
        
        points_norm[:, 0] = points[:, 0] - x_c
        points_norm[:, 1] = points[:, 1] - y_c
        return points_norm

    def _extract_target_points(self, target, point_cloud, target_index=None):
        """
        Trích xuất các điểm mây thuộc về target hiện tại dựa trên ID hoặc khoảng cách.
        Tránh import từ pointcloud_processing để ngăn lỗi import vòng.
        """
        if point_cloud is None or len(point_cloud) == 0:
            return np.empty((0, 5), dtype=np.float32)
            
        tid = target.get("tid")
        source = target.get("source", "")
        tx = target.get("posX", 0.0)
        ty = target.get("posY", 0.0)
        tz = target.get("posZ", 0.0)
        
        # 1. Dùng target_index TLV cho target phần cứng
        if source == "firmware_target" and target_index is not None and len(target_index) == len(point_cloud) and tid is not None:
            mask = target_index == tid
            associated = point_cloud[mask]
            if len(associated) >= 3:
                return associated
                
        # 2. Dự phòng: lấy các điểm trong hình hộp chữ nhật xung quanh tâm target
        rx, ry, rz = 0.85, 0.85, 1.20
        mask = (
            (np.abs(point_cloud[:, 0] - tx) <= rx) &
            (np.abs(point_cloud[:, 1] - ty) <= ry) &
            (np.abs(point_cloud[:, 2] - tz) <= rz)
        )
        return point_cloud[mask]

    def update(self, targets, point_cloud=None, target_index=None):
        """
        Cập nhật lịch sử di chuyển và phân loại trạng thái ngã cho các mục tiêu.
        Hỗ trợ cả Deep Learning cục bộ (Phương án 1) và Rule-based fallback.
        """
        now = time.time()
        active_tids = set()

        for target in targets:
            tid = target.get("tid")
            if tid is None:
                continue
            active_tids.add(tid)

            pos_z = target.get("posZ", 1.7)
            vel_z = target.get("velZ", 0.0)
            posture = target.get("posture", "STANDING")

            # Khởi tạo lịch sử nếu chưa tồn tại
            if tid not in self.histories:
                self.histories[tid] = TargetMotionHistory()

            history = self.histories[tid]

            # 0. Bỏ qua kiểm tra té ngã nếu hình thể không hợp lệ (nhiễu sàn/clutter)
            cluster_features = target.get("clusterFeatures", {})
            is_shape_valid = cluster_features.get("is_shape_valid", True)
            if not is_shape_valid:
                history.state = "NORMAL"
                history.fall_detected_time = None
                target["fall_status"] = "NORMAL"
                target["fall_alert"] = False
                continue

            # Tính toán vận tốc ngang để khóa cảnh báo ngã khi di chuyển ngang tốc độ cao (chạy nhanh)
            vel_x = target.get("velX", 0.0)
            vel_y = target.get("velY", 0.0)
            v_xy = np.sqrt(vel_x**2 + vel_y**2)

            # Trích xuất mây điểm tương ứng với target
            pts_resampled = None
            if point_cloud is not None:
                pts_curr = self._extract_target_points(target, point_cloud, target_index)
                pts_norm = self.normalize_spatial(pts_curr)
                resample_size = getattr(self, "num_points", 32)
                pts_resampled = self.resample_points(pts_norm, resample_size)

            history.update(pos_z, vel_z, posture, pts_resampled)

            z_hist = history.z_history
            vz_hist = history.vz_history
            postures_hist = history.postures

            # Thực thi mô hình Deep Learning nếu được bật và đủ số frame tích lũy
            run_dl = False
            if self.use_deep_learning and point_cloud is not None and len(history.pc_history) >= self.seq_len:
                try:
                    # input_data: (1, seq_len, num_points, 5)
                    input_data = np.array(history.pc_history[-self.seq_len:], dtype=np.float32)
                    input_data = np.expand_dims(input_data, axis=0) # (1, T, N, C)
                    
                    input_name = self.ort_session.get_inputs()[0].name
                    output_name = self.ort_session.get_outputs()[0].name
                    
                    logits = self.ort_session.run([output_name], {input_name: input_data})[0]
                    
                    # Softmax
                    exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
                    probs = exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)
                    pred_class = np.argmax(probs[0])
                    
                    # 0: NORMAL, 1: FALLING, 2: FALLEN
                    if pred_class == 1:
                        if history.state != "FALLING":
                            history.state = "FALLING"
                            history.fall_detected_time = now
                    elif pred_class == 2:
                        history.state = "FALLEN"
                    else:
                        history.state = "NORMAL"
                        history.fall_detected_time = None
                        
                    run_dl = True
                except Exception as e:
                    # Gặp lỗi khi chạy DL thì tự động lùi về Rule-based cho frame này
                    run_dl = False

            if not run_dl:
                # ==========================================
                # RULE-BASED FALL DETECTION (FALLBACK LOGIC)
                # ==========================================
                # 1. Phát hiện phục hồi (Đang ngã/nằm nhưng đứng lên hoặc ngồi lên)
                has_recovered_posture = (len(postures_hist) >= 3 and all(p in ("STANDING", "SITTING") for p in postures_hist[-3:]))
                if history.state in ("FALLING", "FALLEN") and (pos_z >= 0.95 or has_recovered_posture):
                    history.state = "NORMAL"
                    history.fall_detected_time = None

                # 2. Phát hiện sự kiện ngã (NORMAL -> FALLING)
                if history.state == "NORMAL":
                    if len(z_hist) >= 5:
                        lookback = min(10, len(z_hist))
                        height_drop = z_hist[-1] - z_hist[-lookback]
                        
                        # Lấy vận tốc đi xuống lớn nhất trong cửa sổ lookback (vz < 0 là đi xuống)
                        max_downward_vz = min(vz_hist[-lookback:])

                        # Điều kiện ngã nhanh:
                        if (height_drop < -0.55 and max_downward_vz < -0.90) or (posture == "LYING/FALLEN"):
                            if v_xy <= 0.85:
                                history.state = "FALLING"
                                history.fall_detected_time = now

                # 3. Chuyển tiếp trạng thái ngã hẳn (FALLING -> FALLEN)
                if history.state == "FALLING":
                    is_lying_still = (pos_z < 0.65 and abs(vel_z) < 0.45)
                    has_lying_posture = (len(postures_hist) >= 3 and all(p == "LYING/FALLEN" for p in postures_hist[-3:]))
                    
                    time_since_fall = now - (history.fall_detected_time or now)
                    
                    # Nếu nằm im hẳn hoặc tư thế được phân loại là nằm sàn kéo dài
                    if (is_lying_still or has_lying_posture) and (time_since_fall >= 0.15):
                        if v_xy <= 0.85:
                            history.state = "FALLEN"

                # 4. Phát hiện ngã chậm (Không qua sự kiện va đập nhanh, ví dụ bò hoặc trượt từ từ)
                if history.state == "NORMAL" and posture == "LYING/FALLEN":
                    if len(postures_hist) >= 5 and all(p == "LYING/FALLEN" for p in postures_hist[-5:]):
                        if v_xy <= 0.85:
                            history.state = "FALLEN"

            # Gán kết quả vào target dict
            target["fall_status"] = history.state
            target["fall_alert"] = (history.state == "FALLEN")

        # Dọn dẹp các target đã biến mất khỏi danh sách hoạt động
        for tid in list(self.histories.keys()):
            if tid not in active_tids:
                if now - self.histories[tid].last_update_time > 10.0:
                    self.histories.pop(tid, None)

        return targets
