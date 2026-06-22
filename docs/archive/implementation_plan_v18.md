# KẾ HOẠCH TRIỂN KHAI v18.0 - NÂNG CẤP BỘ LỌC IMM FILTER 3D VÀ THUẬT TOÁN HUNGARIAN DATA ASSOCIATION TOÀN CỤC

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 18.0** để tích hợp hai nâng cấp thuật toán lớn nhất nhằm đạt trạng thái tối ưu (State-of-the-art) cho bám vết người 3D bằng Radar:
1. **IMM Filter 3D (Interacting Multiple Model)**: Chạy song song mô hình Động (Constant Velocity - CV) và mô hình Tĩnh (Stop Model) để giải quyết triệt để lỗi mất dấu hoặc lệch state khi người dùng đứng im/ngồi xuống/đi chậm.
2. **Hungarian Data Association**: Thay thế thuật toán tham lam Nearest Neighbor (GNN) hiện tại bằng thuật toán Hungarian (Kuhn-Munkres) tối ưu toàn cục để chống chéo ID và nhầm lẫn ID khi có nhiều người di chuyển gần nhau, kèm theo cơ chế fallback pure-NumPy thông minh.

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ PHƯƠNG ÁN NÂNG CẤP

### 1. Tầng 5 - Nâng cấp từ Tuyến tính CV Kalman sang Bộ lọc IMM (Interacting Multiple Model) 3D
* **Vấn đề**: Người thực tế có hành vi động học cực kỳ đa dạng: đi thẳng nhanh (CV), đột ngột đứng yên thở/cử động nhẹ (Stop), rẽ hoặc cúi xuống. Bộ lọc 3D Constant Velocity (CV) hiện tại cố gắng khớp một vận tốc không đổi, dẫn đến ma trận hiệp phương sai sai số $P$ phình to khi đứng im, gây hiện tượng trôi hộp (drift) hoặc mất track sau vài giây.
* **Giải pháp**: Triển khai bộ lọc **IMM 3D** chạy song song hai mô hình chuyển động:
  * **Model 1: Constant Velocity (CV)**: Giống bộ lọc hiện tại, phù hợp khi người di chuyển chủ động. State vector $x = [p_x, p_y, p_z, v_x, v_y, v_z]^T$.
  * **Model 2: Zero-Velocity / Stationary (Stop)**: Thiết lập ma trận chuyển trạng thái $F$ triệt tiêu vận tốc và nhiễu hệ thống $Q$ cực nhỏ để khóa chặt vị trí khi đứng im.
  * **Cơ chế hoạt động của IMM**:
    1. **Mixing (Trộn trạng thái)**: Sử dụng ma trận chuyển đổi xác suất mô hình $p_{ij}$ (Transition Probability Matrix) để trộn trạng thái $x$ và hiệp phương sai $P$ của hai mô hình tại đầu mỗi frame.
    2. **Prediction (Dự báo song song)**: Từng mô hình tự dự báo trạng thái của mình.
    3. **Update (Cập nhật song song)**: Cập nhật độc lập dựa trên điểm centroid đo lường thực tế.
    4. **Probability Update (Cập nhật xác suất mô hình)**: Tính toán Likelihood (độ tương thích) của mỗi mô hình dựa trên vector cải tiến (innovation $\nu$) và ma trận hiệp phương sai cải tiến $S$ từ bộ lọc Kalman.
    5. **Combination (Kết hợp)**: Trọng số hóa trạng thái của 2 bộ lọc theo xác suất mô hình hiện tại ($p_{CV}$ và $p_{Stop}$) để cho ra vị trí, vận tốc tối ưu và gán lại cho bounding box hiển thị.

### 2. Tầng 4 - Nâng cấp bộ Data Association lên Hungarian Algorithm toàn cục
* **Vấn đề**: Thuật toán bám vết hiện tại sử dụng cơ chế Nearest Neighbor đơn giản, duyệt qua từng cluster và ghép với track gần nhất. Khi hai người đi giao nhau hoặc đứng rất gần, cơ chế tham lam này dễ gán nhầm ID, dẫn đến hiện tượng tráo ID (Identity Switch) hoặc một người hút cả 2 box.
* **Giải pháp**: Triển khai thuật toán **Hungarian** để tìm phương án ghép cặp giữa $M$ tracks và $N$ clusters sao cho **tổng chi phí là nhỏ nhất**.
  * **Chi phí ghép cặp (Cost Matrix)**: Sử dụng khoảng cách Mahalanobis kết hợp khoảng cách hình học 3D và độ lệch vận tốc:
    $$\text{Cost}_{i,j} = w_1 \cdot d_{\text{Euclidean3D}}^2 + w_2 \cdot d_{\text{Doppler}}^2 + w_3 \cdot d_{\text{Mahalanobis}}$$
  * **Cơ chế Fallback thông minh**: Để giữ vững tôn chỉ "chạy ngay lập tức không cần cài đặt thêm thư viện nặng", hệ thống sẽ cố gắng import `scipy.optimize.linear_sum_assignment`. Nếu môi trường chưa cài `scipy`, một bộ giải Hungarian tối ưu dạng **Greedy Recursive Munkres** viết hoàn toàn bằng `numpy` sẽ tự động kích hoạt làm fallback, đảm bảo tính bền vững 100%.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Bổ sung các cấu hình cho thuật toán IMM Filter:
  * `ENABLE_IMM_FILTER = True` (Bật/tắt IMM).
  * `IMM_TRANSITION_MATRIX` (Ma trận xác suất chuyển đổi giữa các mô hình chuyển động, mặc định $p_{11}=0.90, p_{12}=0.10, p_{21}=0.15, p_{22}=0.85$).
* Bổ sung các tham số trọng số chi phí cho ma trận Hungarian Cost:
  * `HUNGARIAN_DIST_WEIGHT = 0.70`
  * `HUNGARIAN_VEL_WEIGHT = 0.30`
  * `HUNGARIAN_MAHALANOBIS_WEIGHT = 0.10`

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* **Import** thư viện Hungarian: Cố gắng `from scipy.optimize import linear_sum_assignment`, nếu lỗi sẽ tự động fallback sang thuật toán giải ma trận chi phí tối ưu toàn cục pure-NumPy.
* Triển khai lớp **`IMMTracker3D`**:
  * Chứa hai thực thể `KalmanTracker3D` (một cấu hình với process noise chuyển động thông thường, một cấu hình cho stop model với vận tốc triệt tiêu).
  * Thực hiện toàn bộ chu trình IMM gồm 5 bước toán học: Mixing, Prediction, Update, Probability Update, Combination.
* Nâng cấp **`VirtualTargetTracker`**:
  * Thay thế vòng lặp so khớp NN cũ bằng ma trận chi phí Hungarian Cost Matrix.
  * Giải ma trận bằng bộ giải toàn cục để sinh ra tối ưu gán ID chính xác nhất.
  * Thay thế các đối tượng bám vết đơn tuyến tính `KalmanTracker3D` trong `self.active_tracks` bằng bộ lọc cao cấp `IMMTracker3D`.

### 📄 [MODIFY] [main.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/main.py)
* Tích hợp hiển thị debug xác suất mô hình IMM thực tế của từng Target đang bám vết lên terminal. Ví dụ: `ID 1000 | pos=(1.20, 2.50, 0.85) | vel=(0.02, -0.05, 0.00) | IMM Prob [CV: 12%, STOP: 88%]`.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử bám vết khi đứng im cực lâu (IMM Filter Verification)
* Chạy chương trình và người thử nghiệm đi vào vùng quét, sau đó đứng im hoàn toàn hoặc ngồi xuống ghế đọc sách trong 60 giây.
* **Tiêu chuẩn vượt qua**:
  * Hộp bounding box bám chặt quanh người, không bị nhảy rung lắc hoặc trôi dạt ra xa (drift) như CV cũ.
  * Xác suất mô hình IMM tự động chuyển dịch trọng số nghiêng về phía **STOP Model** ($>80\%$) chỉ sau 1-2 giây đứng im. Khi người dùng bắt đầu bước đi nhanh trở lại, hệ thống lập tức nhạy bén chuyển trọng số về **CV Model** ($>75\%$) trong vòng 0.2 giây.

### 2. Kiểm thử giao cắt đa mục tiêu (Hungarian Association Verification)
* Hai người đi ngược chiều nhau và giao nhau trực diện ở cự ly gần ($<0.5$ mét).
* **Tiêu chuẩn vượt qua**:
  * Sau khi giao nhau và tách ra, hai hộp bám vết vẫn giữ nguyên vẹn chính xác ID ban đầu, tuyệt đối không bị tráo ID (Identity Switch) or gộp chung thành một ID duy nhất rồi tự sinh ra ID mới khi tách ra.
  * Thuật toán Hungarian giải quyết thành công bài toán ghép cặp toàn cục tối ưu mà không gây trễ giật khung hình.

### 3. Kiểm thử tương thích không thư viện (No-Dependency Stability Check)
* Tạm thời đổi tên thư viện `scipy` trong môi trường ảo hoặc ép lỗi import để chạy chế độ Fallback Hungarian.
* **Tiêu chuẩn vượt qua**:
  * Chương trình vẫn khởi động bình thường, in log thông báo kích hoạt thành công chế độ `[WARNING] Scipy linear_sum_assignment not found. Fallback to pure-NumPy Munkres solver.`
  * Các tính năng bám vết đa mục tiêu hoạt động chính xác tương tự như khi có `scipy`.
