import sys
import os
import numpy as np
import time

# Thêm các thư mục cần thiết vào PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import settings
from fall_detector import FallDetector, TargetMotionHistory

def test_preprocessing():
    print("=" * 60)
    print("KIỂM THỬ CÁC HÀM TIỀN XỬ LÝ MÂY ĐIỂM (PREPROCESSING)")
    print("=" * 60)
    
    detector = FallDetector()
    
    # 1. Kiểm thử Resampling
    print("\n1. Kiểm thử Resample điểm:")
    # Tạo cụm điểm thưa (10 điểm, mỗi điểm 5 đặc trưng x,y,z,v,SNR)
    sparse_points = np.random.normal(0, 1, (10, 5))
    resampled_sparse = detector.resample_points(sparse_points, target_num_points=32)
    print(f"  - Cụm điểm gốc thưa: {sparse_points.shape} -> Sau Resample: {resampled_sparse.shape}")
    assert resampled_sparse.shape == (32, 5), "Lỗi Resample cụm thưa!"
    
    # Tạo cụm điểm dày (50 điểm)
    dense_points = np.random.normal(0, 1, (50, 5))
    # Gán cột SNR (index 4) giá trị ngẫu nhiên lớn
    dense_points[:, 4] = np.arange(50)
    resampled_dense = detector.resample_points(dense_points, target_num_points=32)
    print(f"  - Cụm điểm gốc dày: {dense_points.shape} -> Sau Resample: {resampled_dense.shape}")
    assert resampled_dense.shape == (32, 5), "Lỗi Resample cụm dày!"
    
    # 2. Kiểm thử Chuẩn hóa không gian (Spatial Normalization)
    print("\n2. Kiểm thử Chuẩn hóa không gian (Tịnh tiến gốc XY):")
    mock_cluster = np.array([
        [1.0, 2.0, 1.5, 0.0, 10.0],
        [1.2, 2.2, 1.4, 0.1, 12.0],
        [0.8, 1.8, 1.6, -0.1, 8.0]
    ])
    mean_x_orig = np.mean(mock_cluster[:, 0]) # 1.0
    mean_y_orig = np.mean(mock_cluster[:, 1]) # 2.0
    
    normalized = detector.normalize_spatial(mock_cluster)
    mean_x_norm = np.mean(normalized[:, 0])
    mean_y_norm = np.mean(normalized[:, 1])
    
    print(f"  - Trọng tâm ban đầu: X_c={mean_x_orig:.2f}, Y_c={mean_y_orig:.2f}")
    print(f"  - Trọng tâm sau chuẩn hóa: X_c={mean_x_norm:.2f}, Y_c={mean_y_norm:.2f}")
    assert abs(mean_x_norm) < 1e-5 and abs(mean_y_norm) < 1e-5, "Lỗi chuẩn hóa không gian!"
    # Trục Z (chiều cao) và các đặc trưng khác phải được giữ nguyên
    assert np.allclose(normalized[:, 2:], mock_cluster[:, 2:]), "Lỗi: Trục Z/V/SNR bị thay đổi sai lệch!"
    print("  - Trục Z, V, SNR được giữ nguyên chính xác.")

    # 3. Kiểm thử Trích xuất điểm thuộc Target (Extract Target Points)
    print("\n3. Kiểm thử Trích xuất điểm thuộc Target:")
    target = {"tid": 1, "posX": 2.0, "posY": 3.0, "posZ": 1.0, "source": "cluster"}
    # Tạo point cloud gồm 100 điểm ngẫu nhiên
    pc = np.random.uniform(-5.0, 5.0, (100, 5))
    # Đặt 5 điểm chắc chắn nằm trong bán kính của target (2.0, 3.0, 1.0)
    pc[0:5, 0:3] = np.array([
        [2.1, 3.1, 1.0],
        [1.9, 2.9, 1.1],
        [2.0, 3.0, 0.9],
        [2.05, 3.05, 1.05],
        [1.95, 2.95, 0.95]
    ])
    
    extracted = detector._extract_target_points(target, pc)
    print(f"  - Tổng số điểm trong phòng: {len(pc)} -> Điểm trích xuất thuộc về Target: {len(extracted)}")
    assert len(extracted) >= 5, "Lỗi trích xuất điểm thuộc target!"

    print("\n=> CÁC BÀI KIỂM THỬ TIỀN XỬ LÝ ĐÃ THÀNH CÔNG!")
    print("=" * 60)

def test_safe_fallback():
    print("=" * 60)
    print("KIỂM THỬ CƠ CHẾ SAFE FALLBACK KHI KHÔNG CÓ MODEL / ORT")
    print("=" * 60)
    
    # Thiết lập cấu hình giả định bật Deep Learning nhưng file model không tồn tại
    settings.ENABLE_DEEP_FALL_DETECTION = True
    settings.DEEP_FALL_MODEL_PATH = "non_existent_model_file.onnx"
    
    detector = FallDetector()
    print(f"  - Cấu hình ENABLE_DEEP_FALL_DETECTION = {getattr(detector, 'enable_deep', None)}")
    print(f"  - Tệp mô hình khai báo: '{getattr(detector, 'model_path', None)}'")
    print(f"  - Trạng thái use_deep_learning sau khởi tạo: {detector.use_deep_learning}")
    
    assert not detector.use_deep_learning, "Lỗi: Lẽ ra use_deep_learning phải là False do không tìm thấy file model!"
    print("  - Xác nhận: Hệ thống đã tự động fallback về Rule-based thành công.")
    
    # Mô phỏng một cú ngã để đảm bảo logic rule-based vẫn chạy mượt mà
    print("\n  - Chạy mô phỏng cú ngã để test logic fallback:")
    
    # Gửi 5 frame đứng im để tích lũy đủ lịch sử (z_hist >= 5)
    for i in range(5):
        targets = [{"tid": 1, "posX": 0.0, "posY": 2.0, "posZ": 1.7, "velX": 0.0, "velY": 0.0, "velZ": 0.0, "posture": "STANDING"}]
        targets = detector.update(targets)
        print(f"    Frame {i+1} (Đứng): Trạng thái ngã = {targets[0]['fall_status']}, Cảnh báo = {targets[0]['fall_alert']}")
    
    # Gửi frame ngã
    targets = [{"tid": 1, "posX": 0.0, "posY": 2.0, "posZ": 0.3, "velX": 0.0, "velY": 0.0, "velZ": -1.5, "posture": "LYING/FALLEN"}]
    targets = detector.update(targets)
    print(f"    Frame 6 (Ngã): Trạng thái ngã = {targets[0]['fall_status']}, Cảnh báo = {targets[0]['fall_alert']}")
    
    assert targets[0]["fall_status"] in ("FALLING", "FALLEN"), "Lỗi: Logic Fallback rule-based không phát hiện được ngã!"
    print("\n=> KIỂM THỬ SAFE FALLBACK ĐÃ THÀNH CÔNG!")
    print("=" * 60)

if __name__ == "__main__":
    test_preprocessing()
    test_safe_fallback()
