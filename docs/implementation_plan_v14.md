# KẾ HOẠCH TRIỂN KHAI v14.0 - ĐỒNG BỘ GÓC NHÌN WEBCAM VÀ BẢO VỆ MỤC TIÊU ĐỨNG IM CỐT LÕI

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 14.0** nhằm giải quyết hai vấn đề lớn nhất được phát hiện trong phiên record v13.0: sự sai khác về góc nhìn sensor mô phỏng vs thực tế và hiện tượng xóa nhầm điểm tĩnh làm mất dấu người đứng im.

---

## 🔍 PHÂN TÍCH VẤN ĐỀ VÀ GIẢI PHÁP ĐỘT PHÁ

### 1. Đồng bộ góc nhìn mô phỏng (3D Plot Viewport) và Camera thực tế
* **Vấn đề**: Vị trí và góc nghiêng của Sensor mô phỏng trên đồ thị không khớp với camera Logitech thực tế (vốn được đặt ngay trên đỉnh radar). Góc nhìn 3D mặc định lệch hướng, gây mất cảm giác trực quan.
* **Giải pháp**:
  * Tịnh tiến Sensor Box 3D lên độ cao lắp đặt thực tế: $Z_{sensor} = \text{RADAR\_MOUNT\_HEIGHT\_M} = 1.15\text{ m}$.
  * Xoay các đỉnh của Sensor Box quanh trục X một góc bằng `RADAR_TILT_ANGLE_DEG = 30.0` để nghiêng hộp xuống đúng góc nghiêng vật lý của radar.
  * Khóa góc nhìn Matplotlib 3D bằng:
    `ax.view_init(elev=RADAR_TILT_ANGLE_DEG, azim=-90)`
    để đồ họa hiển thị dưới chính xác góc nhìn từ mắt của camera/radar đặt trên cao nhìn xuống, tạo sự đồng bộ hoàn hảo 100% khi ghi video side-by-side.

### 2. Sửa lỗi triệt tiêu điểm tĩnh của mục tiêu phần cứng (Firmware Target Blanking)
* **Vấn đề**: Bộ lọc điểm tĩnh `ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER` chỉ bảo vệ mây điểm trong bán kính $1.0\text{ m}$ quanh các `confirmed_positions` thuộc `VirtualTargetTracker` (thuật toán phần mềm). Nó bỏ sót các mục tiêu bám bởi phần cứng (`raw_targets`), dẫn đến việc toàn bộ mây điểm của người dùng bị xóa sạch khi họ đứng im, làm target phần cứng bị coi là ghost và biến mất sau 5 frame.
* **Giải pháp**:
  * Cập nhật logic trong `track_and_build` của `pointcloud_processing.py` để tự động đưa toàn bộ tọa độ `(posX, posY)` của các `raw_targets` đang hoạt động ổn định vào danh sách bảo vệ `confirmed_positions`.
  * *Kết quả*: Mây điểm của người đứng im sẽ được bảo vệ tuyệt đối và ổn định, triệt tiêu hoàn toàn lỗi nhấp nháy mất hộp khi đứng im.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
* Cấu hình tham số khóa góc nhìn camera:
```python
# ============================================================
# CAMERA & VIEWPORT LOCK (Version 14.0)
# ============================================================
ENABLE_CAMERA_VIEW_LOCK = True         # Khóa góc nhìn Matplotlib 3D đồng bộ với Webcam thực tế
```

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
* Cập nhật hàm `VirtualTargetTracker.track_and_build` để bảo vệ điểm tĩnh của target phần cứng:
```python
        # Lấy danh sách vị trí confirmed tracks để bảo vệ điểm tĩnh
        confirmed_positions = [
            track_info["kalman"].x[:2] 
            for track_info in self.active_tracks.values() 
            if track_info["state"] == "confirmed"
        ]
        
        # Thêm các target phần cứng vào danh sách vị trí đã xác nhận để bảo vệ điểm tĩnh (Version 14.0)
        for target in raw_targets:
            if "posX" in target and "posY" in target:
                confirmed_positions.append(np.array([target["posX"], target["posY"]], dtype=np.float32))
```

### 📄 [MODIFY] [visualization.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/visualization.py)
* Cập nhật `draw_sensor_box_3d` xoay nghiêng và tịnh tiến lên cao độ $1.15\text{ m}$:
```python
def draw_sensor_box_3d(ax):
    if not SHOW_SENSOR_BOX:
        return

    sx = SENSOR_BOX_SIZE_X / 2.0
    sy = SENSOR_BOX_SIZE_Y / 2.0
    sz = SENSOR_BOX_SIZE_Z / 2.0

    # Tính toán các đỉnh sau khi quay 30 độ và tịnh tiến lên độ cao lắp đặt thực tế (Version 14.0)
    theta = np.radians(RADAR_TILT_ANGLE_DEG if 'RADAR_TILT_ANGLE_DEG' in globals() else 30.0)
    h = RADAR_MOUNT_HEIGHT_M if 'RADAR_MOUNT_HEIGHT_M' in globals() else 1.15

    local_vertices = np.array([
        [-sx, -sy, -sz],
        [ sx, -sy, -sz],
        [ sx,  sy, -sz],
        [-sx,  sy, -sz],
        [-sx, -sy,  sz],
        [ sx, -sy,  sz],
        [ sx,  sy,  sz],
        [-sx,  sy,  sz],
    ])

    vertices = np.zeros_like(local_vertices)
    vertices[:, 0] = local_vertices[:, 0]
    vertices[:, 1] = local_vertices[:, 1] * np.cos(theta) - local_vertices[:, 2] * np.sin(theta)
    vertices[:, 2] = local_vertices[:, 1] * np.sin(theta) + local_vertices[:, 2] * np.cos(theta) + h

    faces = [
        [vertices[0], vertices[1], vertices[2], vertices[3]],
        [vertices[4], vertices[5], vertices[6], vertices[7]],
        [vertices[0], vertices[1], vertices[5], vertices[4]],
        [vertices[2], vertices[3], vertices[7], vertices[6]],
        [vertices[1], vertices[2], vertices[6], vertices[5]],
        [vertices[0], vertices[3], vertices[7], vertices[4]],
    ]

    sensor_box = Poly3DCollection(
        faces,
        alpha=0.90,
        edgecolor="black",
        linewidths=0.8
    )

    sensor_box.set_facecolor("steelblue")
    sensor_box.set_label("Sensor")

    ax.add_collection3d(sensor_box)

    if SHOW_SENSOR_LABEL:
        ax.text(
            0.0,
            0.0,
            h + sz + 0.08,
            "Sensor",
            ha="center"
        )
```

* Khóa góc nhìn trong `update_3d_plot`:
```python
    ax.cla()

    # Đặt góc nhìn Camera khớp hoàn toàn với vị trí và độ nghiêng vật lý của Radar/Webcam (Version 14.0)
    if ENABLE_CAMERA_VIEW_LOCK if 'ENABLE_CAMERA_VIEW_LOCK' in globals() else True:
        ax.view_init(elev=RADAR_TILT_ANGLE_DEG if 'RADAR_TILT_ANGLE_DEG' in globals() else 30.0, azim=-90)
```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Kiểm thử góc nhìn Camera đồng bộ
* Khởi chạy `python main.py` và kiểm tra xem góc nhìn 3D mô phỏng của Matplotlib có khớp hoàn toàn với hướng chụp của Webcam Logitech hay không.
* Xác nhận Sensor Box nằm lơ lửng ở cao độ $1.15\text{ m}$ và chúc đầu nghiêng xuống $30^\circ$.

### 2. Kiểm thử triệt tiêu lỗi mất dấu khi đứng im
* Đứng yên hoàn toàn trước radar trong hơn 30 giây.
* **Tiêu chuẩn đạt**: Hộp bám đuổi của target phần cứng duy trì ổn định không nhấp nháy hay biến mất; mây điểm thô hiển thị đầy đủ và không bị bộ lọc tĩnh xóa nhầm.
