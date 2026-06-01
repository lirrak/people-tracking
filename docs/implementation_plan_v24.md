# KẾ HOẠCH TRIỂN KHAI v24.0 - DYNAMIC STATE LOCKING (KHÓA TRẠNG THÁI ĐỘNG HỌC & ĐIỂM HÌNH HỌC DÁNG NGƯỜI)

Tài liệu này trình bày kế hoạch nâng cấp hệ thống lên **Version 24.0** nhằm giải quyết triệt để lỗi khóa cứng hộp bóng ma tĩnh khi người rời khỏi phòng (đặc biệt tại bàn ghế, tường), trong khi vẫn duy trì độ ổn định hiển thị hộp 100% khi người thật đứng yên trong vùng hoạt động của radar. 

**Phương án này hoàn toàn KHÔNG phụ thuộc vào bộ lọc vi động hô hấp (Doppler Breathing), vốn có độ nhạy kém và chập chờn vật lý khi đứng yên.** Thay vào đó, chúng ta áp dụng cơ chế **Dynamic State Locking (Khóa trạng thái người thật dựa trên lịch sử vận tốc và điểm hình học)** - một phương án đã được chứng minh hiệu quả trong các phiên bản trước.

---

## 🔍 PHÂN TÍCH NHẬT KÝ CHẠY GẦN NHẤT & CƠ CHẾ LỖI KHÓA CỨNG (FEEDBACK LOOP)

Qua phân tích nhật ký `radar_run_output.log` gần nhất, hệ thống gặp hiện tượng khóa cứng các hộp ảo (ví dụ ID `1000`, `1001`, `1002`...) ở trạng thái vận tốc bằng 0 (`vel=(0.00, 0.00, 0.00) m/s`) và số điểm hỗ trợ lớn (`support_points >= 8`):
1. **Lớp bảo vệ tĩnh vật vô điều kiện**: Khi tracker hoặc radar nhận dạng một mục tiêu tĩnh (như chiếc ghế), hệ thống tự động mở một cổng bảo vệ không gian `r_prot = 0.45m` xung quanh tọa độ đó.
2. **Kích hoạt điểm tĩnh**: Cổng bảo vệ này giữ lại toàn bộ các điểm phản xạ tĩnh của chiếc ghế (Doppler $\approx 0$), bỏ qua bộ lọc tĩnh vật cấp độ điểm.
3. **Gom cụm và gán nhãn**: Các điểm tĩnh này được gom cụm lại bởi DBSCAN, tạo ra một cụm lớn có `supportPointCount > 6`.
4. **Vòng lặp phản hồi ngược (Feedback Loop)**: Trong `GhostTargetFilter.update`, điều kiện để bỏ qua bộ lọc tĩnh vật toàn diện là:
   `is_confident_human = (target.get("humanScore", 0.0) > 40.0) or (target.get("supportPointCount", 0) > 6)`
   Do `supportPointCount` luôn lớn hơn 6 (nhờ các điểm tĩnh được bảo vệ), `is_confident_human` luôn bằng `True`, dẫn đến việc hệ thống coi chiếc ghế là người thật đứng im và hiển thị hộp vĩnh viễn!

---

## 💡 GIẢI PHÁP ĐỀ XUẤT TRONG VERSION 24.0: DYNAMIC STATE LOCKING (KHÓA TRẠNG THÁI NGƯỜI THẬT)

Để đáp ứng hoàn hảo hai yêu cầu cốt lõi của bạn mà không phụ thuộc vào vi động hô hấp chập chờn:
1. **Khi trong tầm radar và đứng yên**: Hộp vẫn hiển thị ổn định, không bị nhấp nháy hay mất dấu.
2. **Khi rời khỏi tầm radar**: Hộp biến mất hoàn toàn và không khóa cứng vào bàn ghế.

Chúng tôi áp dụng cơ chế **Dynamic State Locking (Khóa trạng thái người thật dựa trên lịch sử vận tốc và điểm hình học)** kết hợp **Adaptive Spatial Protection Gate**:

### 1. Cơ chế khóa trạng thái di chuyển (Stateful Motion History)
Mỗi Track ID (cả phần cứng và phần mềm) sẽ duy trì một trạng thái bộ nhớ `has_moved` lưu trong tracker:
* **Khi khởi tạo Track mới**: Mặc định `has_moved = False`.
* **Kích hoạt khóa người thật**: Nếu mục tiêu di chuyển với vận tốc $\ge 0.15\text{ m/s}$, hệ thống lập tức khóa trạng thái: `has_moved = True`. Trạng thái này sẽ được **duy trì vĩnh viễn** suốt vòng đời của Track ID đó.
* **Tại sao phương án này phân biệt được người và bàn ghế?**
  * **Con người thật**: Phải di chuyển đi vào phòng trước khi đứng im $\rightarrow$ `has_moved` chắc chắn sẽ được khóa bằng `True`.
  * **Đồ vật tĩnh (chiếc ghế, bức tường)**: Đã nằm im ở đó từ trước, vận tốc từ lúc khởi tạo luôn bằng 0 $\rightarrow$ `has_moved` luôn bằng `False`.

### 2. Cổng bảo vệ thích nghi theo trạng thái động học
Bán kính bảo vệ điểm tĩnh `r_prot` tại vị trí mục tiêu được quyết định chặt chẽ:
* Nếu mục tiêu di chuyển (`speed >= 0.15 m/s`): Mở rộng cổng bảo vệ `r_prot = 0.85m` để bao quát mây điểm di chuyển bị kéo dài.
* Nếu mục tiêu đứng im (`speed < 0.15 m/s`):
  * **Nếu là người thật** (`has_moved = True` và hình dáng hình học hợp lệ `humanScore > 40.0`): Thu hẹp cổng bảo vệ xuống `r_prot = 0.45m` để vừa khít cơ thể người, giữ lại điểm mây người đứng im.
  * **Nếu là vật thể tĩnh** (`has_moved = False` hoặc hình dáng không hợp lệ `humanScore <= 40.0`): **Đóng hoàn toàn cổng bảo vệ** `r_prot = 0.0`.

### 3. Phá vỡ hoàn toàn vòng lặp Feedback khi rời đi
* **Khi bạn rời đi**:
  * Khi bạn di chuyển ra ngoài phòng, tracker bám theo bạn ra ngoài và ID bám vết của bạn sẽ tự động bị xóa (deletion) khi mất dấu ngoài biên.
  * Nếu một mục tiêu mới (bóng ma phần cứng/phần mềm) cố gắng sinh ra tại chiếc ghế cũ:
    * Do chiếc ghế chưa từng di chuyển, mục tiêu mới sinh ra sẽ có `has_moved = False`.
    * Đồng thời, điểm số hình học dáng người của chiếc ghế kim loại hoặc bức tường rất thấp (`humanScore < 20.0` do sai kích thước, chiều cao thấp).
    * Hệ thống lập tức đóng cổng bảo vệ `r_prot = 0.0`.
    * Toàn bộ điểm tĩnh của chiếc ghế bị bộ lọc điểm tĩnh quét sạch $\rightarrow$ `supportPointCount` sụt về 0 $\rightarrow$ Mục tiêu ma biến mất hoàn toàn chỉ sau dưới 1.5 giây!

---

## 📝 DANH SÁCH FILE THAY ĐỔI CHI TIẾT (PROPOSED CHANGES)

### 📄 [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)

#### 1. Cấu trúc lại `VirtualTargetTracker` để theo dõi lịch sử vận tốc và khóa trạng thái `has_moved`
* Bổ sung `self.track_motion_history = {}` trong hàm `__init__` để lưu trạng thái `has_moved` của từng ID (cả Virtual và Hardware).
* Trong `track_and_build()`, cập nhật trạng thái `has_moved` và cổng bảo vệ thích nghi động học:
```python
        # Quyết định cổng bảo vệ thích nghi dựa trên Dynamic State Locking (v24.0)
        confirmed_positions = []
        
        # A. Xử lý Virtual Tracks
        for tid, track_info in self.active_tracks.items():
            if track_info["state"] == "confirmed":
                k_state = track_info["kalman"].x
                pos = k_state[:2]
                speed = np.sqrt(k_state[3]**2 + k_state[4]**2 + k_state[5]**2)
                score = track_info.get("score", 0.0)
                
                # Cập nhật và lưu giữ trạng thái đã từng di chuyển
                if speed >= 0.15:
                    self.track_motion_history[tid] = True
                
                has_moved = self.track_motion_history.get(tid, False)
                is_confident_human = has_moved and (score > 40.0)
                
                # Quyết định bán kính bảo vệ điểm tĩnh
                if speed >= 0.15:
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
                score = target.get("humanScore", 0.0)
                pos = np.array([target["posX"], target["posY"]], dtype=np.float32)
                
                if speed >= 0.15:
                    self.track_motion_history[tid] = True
                    
                has_moved = self.track_motion_history.get(tid, False)
                is_confident_human = has_moved and (score > 40.0)
                
                if speed >= 0.15:
                    r_prot = 0.85
                    confirmed_positions.append((pos, r_prot))
                elif is_confident_human:
                    r_prot = 0.45
                    confirmed_positions.append((pos, r_prot))
```
* Bổ sung cơ chế dọn dẹp bộ nhớ đệm `self.track_motion_history` khi target bị xóa khỏi hệ thống để tránh phình bộ nhớ.

---

### 📄 [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)

#### 1. Đồng bộ và sửa lỗi `is_confident_human` trong `GhostTargetFilter`
* Loại bỏ điều kiện lỗi thời `supportPointCount > 6` gây khóa cứng bàn ghế.
* Sử dụng kết hợp **Recent Motion History** và điểm số hình học để quyết định bỏ qua bộ lọc tĩnh vật toàn diện:
```python
                    # Loại bỏ điều kiện lỗi thời supportPointCount > 6 gây khóa cứng
                    # Nhận dạng người đứng im dựa trên lịch sử di chuyển tích lũy và dáng người (Version 24.0)
                    current_speed = self.target_speed(target)
                    if current_speed >= 0.15:
                        self.max_speed_history[tid] = max(self.max_speed_history.get(tid, 0.0), current_speed)
                    
                    has_moved = self.max_speed_history.get(tid, 0.0) >= 0.15
                    is_confident_score = (target.get("humanScore", 0.0) > 40.0)
                    
                    is_human_presence = has_moved and is_confident_score
                    
                    if not is_human_presence:
                        is_static = True
```

---

## 🔬 KẾ HOẠCH XÁC MINH (VERIFICATION PLAN)

### 1. Xác minh triệt tiêu hộp ma bàn ghế khi người rời phòng
* **Cách thực hiện**: Chạy hệ thống lúc không có người, hoặc sau khi người đã đứng yên tại vị trí đó rồi đi ra khỏi phòng.
* **Tiêu chuẩn vượt qua**: Các hộp tĩnh tại bàn ghế, tường không bao giờ xuất hiện. Nếu xuất hiện nhất thời khi người vừa đi qua, hộp phải tự động biến mất hoàn toàn trong vòng dưới 1.5 giây do không thỏa mãn điều kiện `has_moved` của mục tiêu mới.

### 2. Xác minh duy trì hộp người đứng im
* **Cách thực hiện**: Một người bước vào vùng quét, đứng im hoàn toàn trước radar trong vòng 60 giây.
* **Tiêu chuẩn vượt qua**: Hộp bám vết duy trì hiển thị liên tục 100% thời gian, không nhấp nháy, không bị ẩn đột ngột nhờ cơ chế giữ cổng thích nghi bằng trạng thái đã được khóa `has_moved = True`.
