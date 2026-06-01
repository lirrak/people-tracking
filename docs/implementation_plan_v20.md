# KẾ HOẠCH TRIỂN KHAI v20.0 - KHÔI PHỤC LOG GỘP, TINH GỌN GIAO DIỆN VÀ SỬA TRIỆT ĐỂ LỖI MẤT DẤU NGƯỜI ĐỨNG YÊN

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 20.0** kết hợp ba nhóm nhiệm vụ cốt lõi, bổ sung các sửa lỗi triệt để cho hiện tượng người đứng yên bị mất dấu trên Radar:
1. **Khôi phục bộ ghi Log CSV**: Quay lại cấu trúc bộ ghi log thống kê gộp cấp độ frame (Frame-level aggregate metrics) gốc, ghi chép 1 dòng duy nhất cho mỗi frame với đầy đủ các thuộc tính đếm số lượng điểm, khoảng Min/Max/Mean SNR và tọa độ.
2. **Lược bỏ hiển thị tư thế (Posture Labels)**: Loại bỏ hoàn toàn các văn bản nhãn hiển thị tư thế (`[STANDING]`, `[SITTING]`, `[LYING/FALLEN]`) và màu sắc cảnh báo đỏ khỏi cửa sổ đồ thị 3D Matplotlib để giữ giao diện tối giản.
3. **Giải quyết triệt để lỗi mất dấu người đứng yên (Hai tầng bảo vệ)**:
   * **Tầng 1: Point-level Clutter Filter**: Sửa lỗi triệt tiêu thô bạo mây điểm tĩnh vật có Doppler $< 0.05\text{ m/s}$. Bằng cách đưa ra cấu hình `STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD = 0.015`, ta giữ lại toàn bộ các điểm vi động hô hấp ($0.02 - 0.08\text{ m/s}$) của người đứng yên, trong khi vẫn lọc sạch nhiễu tường/bàn ghế thực sự (Doppler chính xác $0.0$).
   * **Tầng 2: Track-level Static Clutter Filter**: Sửa lỗi nghiêm trọng từ v16.0 khi người đứng im quá 15 frames ($0.75$ giây) có vị trí ổn định ($\sigma_{xy} \le 0.05\text{ m}$) bị bộ lọc đánh dấu `is_static = True` và ẩn mất tiêu. Chúng tôi bổ sung cơ chế kiểm tra vi động nhịp thở (`0.015 <= doppler_std <= 0.10`) hoặc hình dáng người tự tin (`humanScore > 40` hoặc `supportPointCount > 6`) để **bỏ qua bộ lọc tĩnh vật** cho con người thật!

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ PHƯƠNG ÁN NÂNG CẤP

### 1. Khôi phục tệp Log CSV về dạng thống kê gộp frame (`pointcloud_logger.py`)
* **Headers khôi phục**:
  `frame_number,timestamp,raw_points_count,stable_points_count,display_points_count,raw_min_snr,raw_max_snr,raw_mean_snr,display_min_x,display_max_x,display_mean_x,display_min_y,display_max_y,display_mean_y,display_min_z,display_max_z,display_mean_z,display_min_doppler,display_max_doppler,display_mean_doppler,target_count,active_target_ids,presence`
* **Hàm ghi `log_frame`**: Tính toán các giá trị Min/Max/Mean của SNR, tọa độ hình học hiển thị (X, Y, Z) và Doppler thích nghi trên mây điểm hiển thị rồi xuất 1 dòng duy nhất xuống file CSV.

### 2. Loại bỏ nhãn thông báo và màu cảnh báo tư thế dọc trục Z (`visualization.py`)
* **Giải pháp**:
  * Trả lại định dạng nhãn vẽ hộp `box_label` về mặc định: `ID x` (ví dụ `ID 1000`) mà không kèm theo trạng thái tư thế.
  * Loại bỏ màu vẽ hộp `color="red"` khi người nằm sàn (truyền `color=None`).
  * Loại bỏ dòng chữ hiển thị tư thế (`posture`) ngay dưới tâm target và nhãn text.

### 3. Khắc phục lỗi mất dấu người đứng yên (`pointcloud_processing.py`, `filters.py`, `settings.py`)

#### A. Sửa lỗi tầng điểm thô (Point-level Static Clutter Filter)
* **Vấn đề**: Bộ lọc điểm tĩnh cũ lọc sạch tất cả điểm có Doppler $< 0.05\text{ m/s}$. Người đứng im thở có Doppler dao động $0.02 - 0.08\text{ m/s}$ nên bị lọc hết sạch (mây điểm bị Fading về 0 điểm hiển thị), khiến DBSCAN không thể gom cụm và xác nhận track.
* **Giải pháp**: 
  * Cấu hình trong `settings.py`:
    `STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD = 0.015`
    `STATIC_CLUTTER_POINT_PROTECTION_RADIUS = 1.2`
  * Trong `pointcloud_processing.py` hàm `build_human_point_mask`: Thay thế ngưỡng cứng `0.05` bằng tham số động `STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD`. Điều này giúp giữ lại các điểm mây thở của người đứng yên.

#### B. Sửa lỗi tầng vết bám (Track-level Static Clutter Filter)
* **Vấn đề**: Hàm `update` trong `GhostTargetFilter` (`filters.py`) tính toán độ lệch vị trí trong 15 frames. Nếu người đứng im, sai lệch $\sigma_{xy} \le 0.05\text{ m}$, hệ thống coi họ là đồ vật tĩnh (như cái ghế) và đặt `is_static = True`, ẩn luôn human box của họ trên màn hình.
* **Giải pháp**:
  * Trích xuất `doppler_std` của cluster cho cả target phần cứng trong `pointcloud_processing.py` bằng hàm `calculate_cluster_doppler_std()`.
  * Trong `filters.py` hàm `GhostTargetFilter.update()`: Khi kiểm tra điều kiện tĩnh `std_xy <= max_std`, bổ sung các điều kiện bảo vệ người thật:
    ```python
    is_breathing = (0.015 <= dop_std <= 0.10)
    is_confident_human = (target.get("humanScore", 0.0) > 40.0) or (target.get("supportPointCount", 0) > 6)
    if not (is_breathing or is_confident_human):
        is_static = True
    ```
  * Điều này đảm bảo chỉ có bàn ghế thực sự mới bị coi là tĩnh vật, còn người đứng im thở hoặc có hình dáng người rõ ràng vẫn được giữ vết 100%.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Định nghĩa thêm các cấu hình cho bộ lọc tĩnh vật cấp độ điểm: `ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER`, `STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD` và `STATIC_CLUTTER_POINT_PROTECTION_RADIUS`.

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* **build_human_point_mask**: Thay đổi ngưỡng cứng Doppler từ `0.05` sang động `STATIC_CLUTTER_POINT_DOPPLER_THRESHOLD` và mở rộng bán kính bảo vệ lên `1.2` mét.
* **VirtualTargetTracker.track_and_build**: Tính toán `doppler_std` cho cả target phần cứng để đồng bộ bảo vệ vết bám.

### 📄 [MODIFY] [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)
* **GhostTargetFilter.update**: Bổ sung bộ lọc thông minh kiểm tra nhịp thở (`doppler_std`) và độ tự tin người dùng (`humanScore`, `supportPointCount`) để bỏ qua việc đánh dấu static cho người đang đứng yên.

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Xác minh định dạng Log CSV
* Chạy chương trình radar, kiểm tra cột `display_points_count` khi người đứng yên.
* **Tiêu chuẩn vượt qua**:
  * `display_points_count` duy trì ở mức cao ($> 15$ điểm) ngay cả khi người đứng im hoàn toàn (không bị sụt về 0 như trước).

### 2. Xác minh ổn định bám vết người đứng yên
* Người đứng yên hoàn toàn ở trước mặt radar trong 60 giây.
* **Tiêu chuẩn vượt qua**:
  * Hộp bám vết 3D Matplotlib và ID mục tiêu được duy trì liên tục 100% thời gian, tuyệt đối không bị biến mất hay ẩn đi sau 15 frames như phiên bản cũ!
