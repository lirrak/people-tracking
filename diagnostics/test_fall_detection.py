import sys
import os
import numpy as np
import time

# Thêm các thư mục cần thiết vào PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import settings
settings.ENABLE_COORD_TRANSFORM = False

from pointcloud_processing import VirtualTargetTracker

def test_fall():
    print("=" * 60)
    print("BẮT ĐẦU GIẢ LẬP KIỂM THỬ PHÁT HIỆN NGÃ")
    print("=" * 60)
    
    tracker = VirtualTargetTracker()
    
    frames = []
    
    # 1. Trạng thái Đứng bình thường (Frame 0-4)
    # Target ở Z=1.5m, Point Cloud co cụm đứng
    for i in range(5):
        raw_targets = [{"tid": 1, "posX": 0.0, "posY": 2.0, "posZ": 1.5, "velX": 0.0, "velY": 0.0, "velZ": 0.0}]
        pc_x = np.random.normal(0.0, 0.1, 20)
        pc_y = np.random.normal(2.0, 0.1, 20)
        pc_z = np.random.uniform(0.5, 1.8, 20) # Phân bố dọc đều từ 0.5 đến 1.8m
        pc_v = np.random.normal(0.0, 0.05, 20)
        pc_snr = np.random.normal(15.0, 1.0, 20)
        pc = np.column_stack((pc_x, pc_y, pc_z, pc_v, pc_snr))
        frames.append((raw_targets, pc))
        
    # 2. Trạng thái Đang rơi cực nhanh (Frame 5-8)
    # Z giảm nhanh, Vz đạt âm lớn
    z_coords = [1.2, 0.8, 0.4, 0.2]
    vz_coords = [-1.2, -1.8, -1.5, -0.4]
    for z, vz in zip(z_coords, vz_coords):
        raw_targets = [{"tid": 1, "posX": 0.0, "posY": 2.0, "posZ": z, "velX": 0.0, "velY": 0.0, "velZ": vz}]
        pc_x = np.random.normal(0.0, 0.15, 20)
        pc_y = np.random.normal(2.0, 0.15, 20)
        pc_z = np.random.normal(z, 0.1, 20)
        pc_v = np.random.normal(vz, 0.1, 20)
        pc_snr = np.random.normal(15.0, 1.0, 20)
        pc = np.column_stack((pc_x, pc_y, pc_z, pc_v, pc_snr))
        frames.append((raw_targets, pc))
        
    # 3. Trạng thái Nằm im dưới sàn (Frame 9-14)
    # Z=0.2m, Vz=0, mây điểm bẹt ngang
    for i in range(6):
        raw_targets = [{"tid": 1, "posX": 0.0, "posY": 2.0, "posZ": 0.2, "velX": 0.0, "velY": 0.0, "velZ": 0.0}]
        pc_x = np.random.uniform(-0.6, 0.6, 25) # Phân tán ngang rộng
        pc_y = np.random.uniform(1.4, 2.6, 25)
        pc_z = np.random.uniform(0.05, 0.35, 25) # Bẹt sát sàn
        pc_v = np.random.normal(0.0, 0.01, 25)
        pc_snr = np.random.normal(15.0, 1.0, 25)
        pc = np.column_stack((pc_x, pc_y, pc_z, pc_v, pc_snr))
        frames.append((raw_targets, pc))
        
    # Chạy mô phỏng
    for idx, (raw_targets, pc) in enumerate(frames):
        time.sleep(0.05) # Giữ dt ~ 50ms
        targets, _, _ = tracker.track_and_build(raw_targets, pc, frame_number=idx)
        print(f"Khung hình {idx:02d}: Target(s) = {len(targets)}")
        for t in targets:
            print(f"  [ID {t['tid']}] Z={t['posZ']:.2f}m, Vz={t['velZ']:.2f}m/s | Tư thế: {t.get('posture')} | Trạng thái ngã: {t.get('fall_status')} | Cảnh báo ngã: {t.get('fall_alert')}")

    print("=" * 60)
    print("KIỂM THỬ PHỤC HỒI (RECOVERY)")
    print("=" * 60)
    # 4. Giả lập hồi phục đứng dậy (Z tăng lên 1.5m)
    for i in range(3):
        raw_targets = [{"tid": 1, "posX": 0.0, "posY": 2.0, "posZ": 1.5, "velX": 0.0, "velY": 0.0, "velZ": 1.0}]
        pc_x = np.random.normal(0.0, 0.1, 20)
        pc_y = np.random.normal(2.0, 0.1, 20)
        pc_z = np.random.uniform(0.5, 1.8, 20)
        pc_v = np.random.normal(0.0, 0.05, 20)
        pc_snr = np.random.normal(15.0, 1.0, 20)
        pc = np.column_stack((pc_x, pc_y, pc_z, pc_v, pc_snr))
        time.sleep(0.05)
        targets, _, _ = tracker.track_and_build(raw_targets, pc, frame_number=15+i)
        for t in targets:
            print(f"  [ID {t['tid']}] Z={t['posZ']:.2f}m, Vz={t['velZ']:.2f}m/s | Tư thế: {t.get('posture')} | Trạng thái ngã: {t.get('fall_status')} | Cảnh báo ngã: {t.get('fall_alert')}")
    print("=" * 60)

def test_run_protection_and_noise_filtering():
    print("=" * 60)
    print("BẮT ĐẦU GIẢ LẬP KIỂM THỬ RUN PROTECTION & NOISE FILTERING")
    print("=" * 60)
    
    tracker = VirtualTargetTracker()
    
    # 1. Giả lập một người chạy nhanh (V_xy = 1.0 m/s > 0.85 m/s)
    # Dù chiều cao có giảm nhất thời hoặc bị nhận diện tư thế nhầm là LYING/FALLEN,
    # bộ phát hiện ngã không được kích hoạt trạng thái FALLEN/FALLING
    print("\n--- KỊCH BẢN 1: NGƯỜI CHẠY NHANH (RUN PROTECTION) ---")
    for i in range(10):
        # velX = 0.8m/s, velY = 0.6m/s -> v_xy = 1.0 m/s
        raw_targets = [{"tid": 2, "posX": i * 0.05, "posY": 2.0 + i * 0.05, "posZ": 1.2, "velX": 0.8, "velY": 0.6, "velZ": -0.2}]
        # Mây điểm hơi co cụm nhưng giãn ngang do chạy
        pc_x = np.random.normal(i * 0.05, 0.3, 20)
        pc_y = np.random.normal(2.0 + i * 0.05, 0.3, 20)
        pc_z = np.random.uniform(0.1, 1.3, 20) # Giả lập chiều cao bị tụt và kéo dẹt
        pc_v = np.random.normal(0.0, 0.1, 20)
        pc_snr = np.random.normal(15.0, 1.0, 20)
        pc = np.column_stack((pc_x, pc_y, pc_z, pc_v, pc_snr))
        
        targets, _, _ = tracker.track_and_build(raw_targets, pc, frame_number=i)
        print(f"Khung hình {i:02d}: Target(s) = {len(targets)}")
        for t in targets:
            v_xy = np.sqrt(t.get("velX", 0.0)**2 + t.get("velY", 0.0)**2)
            print(f"  [ID {t['tid']}] Z={t['posZ']:.2f}m, V_xy={v_xy:.2f}m/s | Tư thế: {t.get('posture')} | Trạng thái ngã: {t.get('fall_status')} | Cảnh báo ngã: {t.get('fall_alert')}")
            # Mong đợi: fall_alert luôn là False, fall_status luôn là NORMAL
            assert t.get("fall_status") == "NORMAL", f"LỖI: Chạy nhanh vẫn báo trạng thái ngã: {t.get('fall_status')}"
            assert not t.get("fall_alert"), "LỖI: Chạy nhanh kích hoạt cảnh báo ngã giả!"

    # 2. Giả lập nhiễu cụm sàn tĩnh (3 điểm tĩnh sát đất, z cực thấp)
    # Kỳ vọng: Cụm này bị loại bỏ hoàn toàn khỏi final_targets và không bao giờ báo ngã
    print("\n--- KỊCH BẢN 2: NHIỄU CỤM SÀN TĨNH (FLOOR CLUTTER FILTERING) ---")
    tracker.reset()
    for i in range(5):
        # Target nhiễu phần cứng có Z thấp, vel thấp
        raw_targets = [{"tid": 1020, "posX": 1.0, "posY": 1.0, "posZ": 0.05, "velX": 0.0, "velY": 0.0, "velZ": 0.0}]
        # Chỉ có 3 điểm hỗ trợ sát sàn
        pc_x = np.array([1.0, 1.05, 0.95])
        pc_y = np.array([1.0, 0.95, 1.05])
        pc_z = np.array([0.02, 0.04, 0.03])
        pc_v = np.array([0.0, 0.0, 0.0])
        pc_snr = np.array([6.0, 7.0, 6.5])
        pc = np.column_stack((pc_x, pc_y, pc_z, pc_v, pc_snr))
        
        targets, _, _ = tracker.track_and_build(raw_targets, pc, frame_number=i)
        print(f"Khung hình {i:02d}: Target(s) = {len(targets)}")
        for t in targets:
            print(f"  [ID {t['tid']}] Z={t['posZ']:.2f}m | Source: {t.get('source')} | Cảnh báo ngã: {t.get('fall_alert')}")
        
        # Kiểm tra xem target nhiễu TID 1020 có bị lọc sạch không
        has_clutter = any(t.get("tid") == 1020 for t in targets)
        assert not has_clutter, "LỖI: Nhiễu cụm sàn tĩnh TID 1020 không bị lọc sạch!"

    print("\n=> TẤT CẢ CÁC BÀI KIỂM THỬ GIẢ LẬP ĐÃ THÀNH CÔNG!")
    print("=" * 60)

if __name__ == "__main__":
    test_fall()
    test_run_protection_and_noise_filtering()
