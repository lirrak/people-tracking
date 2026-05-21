# Lập Kế Hoạch Lọc Nhiễu & Tối Ưu Hóa Ổn Định Radar IWR6843AOP (Version 1)

Tài liệu này trình bày phân tích chuyên sâu về các nguồn gây nhiễu trên radar IWR6843AOP (đặc biệt trong demo 3D People Tracking) và đề xuất kế hoạch cải tiến thuật toán lọc nhiễu ở cả 2 cấp độ: **Cảm biến (Firmware/Config)** và **Phần mềm (Python processing)**.

---

## 1. Phân Tích Các Nguồn Nhiễu Trên Radar IWR6843AOP

Trong quá trình vận hành radar FMCW (đặc biệt là IWR6843AOP trong môi trường trong nhà), các nguồn nhiễu chính bao gồm:
1. **Nhiễu sàn nhà và trần nhà (Ground/Ceiling Clutter):** Phản xạ từ sàn nhà, thảm, trần nhà hoặc vật liệu sàn khi góc đặt radar bị nghiêng.
2. **Nhiễu tĩnh vật lý (Static Clutter):** Các vật thể đứng yên như bàn ghế, tủ, cột nhà tạo ra các điểm phản xạ mạnh liên tục.
3. **Nhiễu phản xạ đa đường (Multi-path Reflections / Ghost targets):** Sóng radar phản xạ từ cơ thể người vào tường rồi quay lại radar, tạo ra một target "ma" (ghost) nằm phía sau bức tường hoặc ở khoảng cách xa hơn.
4. **Nhiễu tức thời (Transient Noise):** Các điểm nhiễu ngẫu nhiên xuất hiện trong 1-2 frame do nhiễu nhiệt hoặc biến động môi trường.

---

## 2. Giải Pháp Lọc Nhiễu Đề Xuất (2 Lớp Bảo Vệ)

Chúng tôi thiết lập hệ thống lọc nhiễu kép (Double-Layer Filtering System) nhằm loại bỏ tối đa nhiễu nhưng vẫn giữ nguyên tính ổn định khi tracking người thật.

### Lớp 1: Lọc Nhiễu Tại Cảm Biến (Firmware / File Config .cfg)
Chúng tôi sẽ tinh chỉnh các tham số phát hiện điểm (CFAR) của radar để ngăn chặn nhiễu được gửi qua cổng UART ngay từ đầu:
*   **Tăng ngưỡng CFAR động (`dynamicRACfarCfg`):** Tăng ngưỡng phát hiện biên độ tín hiệu động từ `4.80` và `7.50` lên `6.00` và `8.50`. Điều này giúp loại bỏ các điểm phản xạ động yếu (như nhiễu không khí, rung động nhẹ).
*   **Tăng ngưỡng CFAR tĩnh (`staticRACfarCfg`):** Tăng ngưỡng phát hiện tĩnh từ `7.20` và `12.50` lên `8.50` và `14.00`. Điều này giúp loại bỏ triệt để điểm nhiễu tĩnh từ các góc phòng/bàn ghế.

### Lớp 2: Lọc Nhiễu Tại Phần Mềm (Python Processing Pipeline)
Chúng tôi tinh chỉnh các bộ lọc phần mềm trong `settings.py` để xử lý các điểm nhiễu lọt qua lớp 1:
1. **Thu hẹp vùng ROI độ cao (`PC_ROI_Z`):** Tăng giới hạn dưới của Z từ `0.05m` lên `0.20m` để triệt tiêu hoàn toàn nhiễu phản xạ từ mặt sàn (sàn nhà/giày kéo lê) mà vẫn giữ được box chân người.
2. **Lọc chất lượng SNR điểm (`MIN_POINT_SNR`):** Tăng SNR tối thiểu của mỗi điểm từ `0.5` lên `1.5` để loại bỏ các điểm mờ nhạt, không ổn định.
3. **Lọc nhiễu tức thời qua ổn định hóa thời gian (`Temporal Stabilizer`):**
    *   Tăng `POINTCLOUD_STABILIZER_MIN_VOXEL_HITS` từ `1` lên `2`. Điều này cực kỳ quan trọng: một điểm voxel phải xuất hiện **ít nhất trong 2 frame** trong cửa sổ 5 frame gần nhất mới được giữ lại. Các điểm nhiễu ngẫu nhiên xuất hiện 1 frame sẽ bị triệt tiêu lập tức!
4. **Tối ưu hóa DBSCAN Clustering:**
    *   Giảm `CLUSTER_EPS` từ `0.65` xuống `0.50` (50cm) để tránh việc gộp các điểm nhiễu rời rạc vào cụm người.
    *   Tăng `CLUSTER_MIN_SAMPLES` và `CLUSTER_MIN_POINTS` từ `2` lên `3`. Một cụm phải có **ít nhất 3 điểm liên kết** mới được coi là cluster, ngăn chặn các cặp điểm nhiễu tạo thành hộp ma.
5. **Thắt chặt bộ lọc Ghost Target:**
    *   Tăng `TARGET_CONFIRM_FRAMES` từ `1` lên `2`. Target ảo cần được duy trì ổn định qua 2 frame liên tiếp mới bắt đầu vẽ hộp, loại bỏ hiện tượng nháy hộp tức thời.
    *   Tăng `GHOST_MIN_SUPPORT_POINTS` từ `1` lên `3` điểm hỗ trợ để giữ hộp sống.
    *   Bật `GHOST_DROP_UNSUPPORTED_IMMEDIATELY = True` giúp xóa hộp ngay lập tức khi người rời đi, tránh hộp ma bị đơ lại.
    *   Tăng ngưỡng điểm số hình học người `HUMAN_SCORE_THRESHOLD` và `VIRTUAL_CLUSTER_SCORE_THRESHOLD` từ `48.0` lên `52.0` để lọc sạch các vật thể có hình dáng không giống người.

---

## 3. Các File Thực Hiện Thay Đổi

Chúng tôi cam kết **KHÔNG xóa bất kỳ file nào** trong thư mục dự án theo đúng yêu cầu của bạn. Chúng tôi chỉ chỉnh sửa giá trị tham số trong 2 file hiện có:

### [MODIFY] [3d_people_tracking.cfg](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/example_configs/3d_people_tracking.cfg)

```diff
-dynamicRACfarCfg -1 3 4 2 2 8 12 4 8 4.80 7.50 0.38 1 1
+dynamicRACfarCfg -1 3 4 2 2 8 12 4 8 6.00 8.50 0.38 1 1

-staticRACfarCfg -1 5 2 2 2 8 8 6 4 7.20 12.50 0.30 0 0
+staticRACfarCfg -1 5 2 2 2 8 8 6 4 8.50 14.00 0.30 0 0
```

### [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)

```diff
-PC_ROI_Z = (0.05, 2.50)
+PC_ROI_Z = (0.20, 2.50)

-MIN_POINT_SNR = 0.5
+MIN_POINT_SNR = 1.5

-CLUSTER_EPS = 0.65
-CLUSTER_MIN_SAMPLES = 2
-CLUSTER_MIN_POINTS = 2
+CLUSTER_EPS = 0.50
+CLUSTER_MIN_SAMPLES = 3
+CLUSTER_MIN_POINTS = 3

-POINTCLOUD_STABILIZER_MIN_VOXEL_HITS = 1
+POINTCLOUD_STABILIZER_MIN_VOXEL_HITS = 2

-TARGET_CONFIRM_FRAMES = 1
+TARGET_CONFIRM_FRAMES = 2

-GHOST_MIN_SUPPORT_POINTS = 1
+GHOST_MIN_SUPPORT_POINTS = 3

-GHOST_DROP_UNSUPPORTED_IMMEDIATELY = False
+GHOST_DROP_UNSUPPORTED_IMMEDIATELY = True

-HUMAN_SCORE_THRESHOLD = 48.0
-VIRTUAL_CLUSTER_SCORE_THRESHOLD = 48.0
+HUMAN_SCORE_THRESHOLD = 52.0
+VIRTUAL_CLUSTER_SCORE_THRESHOLD = 52.0
```
