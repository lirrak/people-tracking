# KẾ HOẠCH TRIỂN KHAI v22.0 - ADAPTIVE SPATIAL PROTECTION GATE (CỔNG BẢO VỆ KHÔNG GIAN THÍCH NGHI VẬN TỐC)

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 22.0** nhằm giải quyết lỗi khóa cứng bóng ma phần cứng và bóng ma ảo bằng cách sử dụng cổng không gian thích nghi theo vận tốc, hoàn toàn **không phụ thuộc vào việc phát hiện vi động hô hấp (Breathing Doppler)**.

---

## 🔍 PHÂN TÍCH PHẢN HỒI VÀ THÁCH THỨC VẬT LÝ

Phản hồi của bạn cực kỳ chính xác: **Radar FMCW rất khó phát hiện vi động hơi thở của người sau khi họ vừa di chuyển rồi dừng lại**.
* Khi một người di chuyển, lồng ngực và quần áo dao động mạnh làm thay đổi biên độ Doppler liên tục. Khi dừng lại đột ngột, phải mất một thời gian tương đối dài (thường > 5-10 giây) để nhịp thở ổn định trở lại và tạo ra đỉnh Doppler tuần hoàn rõ nét.
* Do đó, nếu ta dùng điều kiện hơi thở `doppler_std >= 0.012` làm cổng cứng để quyết định bảo vệ điểm tĩnh khi đứng im, hệ thống sẽ **đóng cổng bảo vệ quá sớm**, dẫn đến lọc sạch mây điểm của người thật và gây ra hiện tượng **mất dấu người đứng yên**.

---

## ⚠️ VẤN ĐỀ CÒN TỒN ĐỌNG TỪ v21.0

Qua phân tích nhật ký chạy thực tế v21.0:
* Vết bám ảo (`virtual_target` ID 1000+) đã biến mất đúng chuẩn khi bạn rời đi ✅
* Tuy nhiên, hộp bám vết phần cứng **ID 1** (`source=firmware_target`) tại tọa độ `pos=(0.92, 0.98, 0.49) m` vẫn bị **khóa cứng vô hạn** với `support_points=30` và `score=85.0` ❌
* Nguyên nhân: Đoạn mã dưới đây tự động thêm **tất cả** vị trí phần cứng vào danh sách bảo vệ mà **không qua bất kỳ kiểm tra nào**:
  ```python
  for target in raw_targets:
      if "posX" in target and "posY" in target:
          confirmed_positions.append(np.array([target["posX"], target["posY"]], dtype=np.float32))
  ```

---

## 💡 GIẢI PHÁP ĐỀ XUẤT: ADAPTIVE SPATIAL PROTECTION GATE

Thay vì cố gắng phát hiện hơi thở Doppler cực nhỏ, chúng ta sẽ tận dụng **sự ổn định của bộ lọc IMM Stop Model** kết hợp với **thu hẹp bán kính không gian thông minh**:

```
Khi mục tiêu đứng yên (speed < 0.12 m/s):
  👉 Thu nhỏ bán kính bảo vệ điểm tĩnh xuống R_prot = 0.45 m (vừa khít cơ thể người).
  👉 Vì R_prot rất nhỏ, nó KHÔNG chạm tới tường hoặc bàn ghế kim loại bên cạnh (> 0.6 m).
  👉 Các điểm phản xạ tĩnh của tường/bàn ghế không được bảo vệ → Bị bộ lọc Doppler loại bỏ!
  👉 Chỉ có các điểm mây thuộc cơ thể người thật (nằm trong 0.45 m) được giữ lại → Bám vết ổn định.

Khi mục tiêu di chuyển (speed >= 0.12 m/s):
  👉 Mở rộng bán kính bảo vệ lên R_prot = 0.85 m.
  👉 Bán kính lớn bù đắp độ trễ Kalman và bao quát mây điểm di chuyển bị kéo dài.
```

### Tại sao giải pháp này triệt tiêu bóng ma tĩnh khi người rời đi?
1. Khi bạn bước đi ra ngoài phòng, tracker bám theo bạn ra ngoài.
2. Vị trí cũ tại P chỉ còn lại bàn ghế/tường. Hộp bám vết phần cứng (như ID 1) đứng im tại P có `speed = 0.0 < 0.12`.
3. Bán kính bảo vệ tại P lập tức thu nhỏ về **0.45 m**.
4. Ở khoảng cách cực hẹp này, các điểm phản xạ tĩnh từ tường/bàn ghế (thường cách tâm > 0.6 m) nằm ngoài vòng bảo vệ → bị bộ lọc tĩnh vật quét sạch.
5. Số điểm hỗ trợ tại P sụt về 0 → Target mất nguồn hỗ trợ → Biến mất chỉ sau 1.5 giây!

### Tại sao giải pháp này KHÔNG làm mất dấu người đứng yên?
* Khi bạn đứng im trước radar, **cơ thể bạn** là nguồn phản xạ chính ở khoảng cách **0 m** từ tâm bám vết.
* Bán kính 0.45 m vẫn thừa đủ để bao quát toàn bộ thân người (chiều rộng trung bình người trưởng thành ≈ 0.35-0.45 m).
* Chỉ có tường/bàn ghế bên cạnh (khoảng cách > 0.6 m) bị loại ra ngoài.

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [MODIFY] [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

#### 1. Chuẩn hóa đầu vào trong `build_human_point_mask`:
Tại đầu hàm, hỗ trợ cả danh sách tọa độ phẳng cũ và danh sách bộ đôi thích nghi `(tọa độ, bán_kính)` mới:
```python
    # Chuẩn hóa danh sách: chấp nhận cả [pos] và [(pos, radius)]
    normalized_tracks = []
    default_r = STATIC_CLUTTER_POINT_PROTECTION_RADIUS if 'STATIC_CLUTTER_POINT_PROTECTION_RADIUS' in globals() else 1.2
    for item in confirmed_track_positions:
        if isinstance(item, tuple) and len(item) == 2 and not isinstance(item[0], (int, float, np.floating)):
            normalized_tracks.append(item)
        else:
            normalized_tracks.append((item, default_r))
```

#### 2. Cập nhật vòng lặp bộ lọc tĩnh vật sử dụng `normalized_tracks`:
* Phần `ENABLE_MICRO_MOTION_ZONE`: dùng `track_pos` từ `normalized_tracks` (giữ nguyên bán kính micro_motion cũ).
* Phần `ENABLE_POINT_LEVEL_STATIC_CLUTTER_FILTER`: mỗi track dùng **bán kính riêng `custom_r`** thay vì bán kính cố định `1.2 m`.

#### 3. Cổng bảo vệ thích nghi trong `track_and_build`:
* Thay thế toàn bộ khối xử lý `confirmed_positions` cho cả mục tiêu ảo lẫn phần cứng:
  ```python
        # Version 22.0 - Adaptive Spatial Protection Gate
        confirmed_positions = []
        for tid, track_info in self.active_tracks.items():
            if track_info["state"] == "confirmed":
                k_state = track_info["kalman"].x
                speed = np.sqrt(k_state[3]**2 + k_state[4]**2 + k_state[5]**2)
                r_prot = 0.45 if speed < 0.12 else 0.85
                confirmed_positions.append((k_state[:2], r_prot))

        for target in raw_targets:
            if "posX" in target and "posY" in target:
                vx = target.get("velX", 0.0)
                vy = target.get("velY", 0.0)
                vz = target.get("velZ", 0.0)
                speed = np.sqrt(vx**2 + vy**2 + vz**2)
                r_prot = 0.45 if speed < 0.12 else 0.85
                pos = np.array([target["posX"], target["posY"]], dtype=np.float32)
                confirmed_positions.append((pos, r_prot))
  ```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Xác minh bám vết người đứng im
* Đứng im trước radar trong 60 giây (không cần cố gắng thở mạnh hay tạo vi động).
* **Tiêu chuẩn vượt qua**: Hộp bám vết ID duy trì ổn định 100% thời gian, không bị mất dấu hay nhấp nháy.

### 2. Xác minh xóa bóng ma khi rời phòng
* Sau khi được bám vết thành công lúc đứng im, bước nhanh ra khỏi tầm quét của radar.
* **Tiêu chuẩn vượt qua**: Hộp bám vết phần cứng và ảo tại vị trí cũ **phải biến mất hoàn toàn** chỉ sau khoảng 1.5 - 2 giây.
