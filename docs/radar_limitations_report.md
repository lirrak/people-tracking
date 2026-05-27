# BÁO CÁO PHÂN TÍCH CHUYÊN SÂU & VƯỢT KHUÔN KHỔ VỀ CÁC HẠN CHẾ CỦA HỆ THỐNG RADAR PEOPLE TRACKING (IWR6843AOP)

Báo cáo này được thực hiện dựa trên việc phân tích chi tiết, từng khung hình (Frame-by-Frame) giữa hình ảnh thực tế từ Webcam và Mô phỏng 3D Radar ở cả hai phiên chạy **Version 11.0** và **Version 12.0**. Thay vì chỉ nhìn nhận dưới góc độ lỗi lập trình, báo cáo này sẽ đi sâu vào bản chất vật lý sóng điện từ, cấu trúc anten và giới hạn phần cứng của chip radar IWR6843AOP kết hợp với kiến trúc xử lý phần mềm hiện tại.

---

## 🔍 PHẦN I: PHÂN TÍCH SỰ KIỆN RECORD THỰC TẾ (SO SÁNH 1:1)

Qua quan sát các tệp record đồng bộ (Reality vs Radar), ta thấy rõ các hành vi tương quan sau:

| Khung hình (Frame) | Hành động thực tế (Webcam) | Phản hồi của Radar (3D Plot) | Trạng thái kỹ thuật & Phát hiện |
| :--- | :--- | :--- | :--- |
| **Frame 700 - 705** | Người dùng di chuyển nhanh từ trái sang phải. | Hộp bám đuổi di chuyển đồng hành rất mượt, bám sát. | **V12.0 Đạt yêu cầu**: Tốc độ di chuyển lớn làm tăng hệ số $\alpha \rightarrow 0.82$, triệt tiêu hoàn toàn độ trễ bám đuổi. |
| **Frame 706 - 710** | Người dùng dừng lại, đứng im hoàn toàn trước bàn làm việc. | Số lượng point cloud giảm nhanh từ 80 $\rightarrow$ 34 $\rightarrow$ 16 điểm. | **Hiệu ứng Self-Blanking**: Doppler tiệm cận về 0, mây điểm thưa dần do bộ lọc triệt tiêu tĩnh vật hoạt động. |
| **Frame 711 - 715** | Người đứng im hoàn toàn, thở nhẹ. | Mây điểm Display = 0. Hộp bám đuổi được giữ nguyên nhờ bộ đếm `missing_frames` tích lũy từ 1 đến 5. | **V12.0 Đạt yêu cầu**: Vùng bảo vệ vi mô nhặt lại được phản xạ thở nhẹ (Doppler cực thấp, SNR ~1.2) giữ vết bám không bị đứt đột ngột. |
| **Frame 716 - 718** | Người đứng im lâu hơn (>1.75s). | Hộp bám đuổi biến mất hoàn toàn. Webcam hiển thị người vẫn đứng nguyên. | **Hạn chế vật lý tĩnh**: Cảm biến bị mù hoàn toàn do cơ thể không có dịch chuyển vĩ mô, bộ đếm thích nghi chạm ngưỡng xóa vết. |

---

## ⚠️ PHẦN II: BÁO CÁO CÁC HẠN CHẾ CỐT LÕI (OUT-OF-THE-BOX DIAGNOSTICS)

Dưới đây là **5 hạn chế mang tính hệ thống và vật lý** được bóc tách một cách sáng tạo và vượt khuôn khổ:

### 1. Hiện tượng "Tự che khuất cơ thể" (Body-Shadowing Self-Occlusion)
* **Phân tích phi khuôn khổ**: Cơ thể người không phải là một điểm chất điểm lý thuyết mà là một cấu trúc 3D phức tạp chứa nước (hấp thụ mạnh sóng mmWave). 
* **Hạn chế xảy ra**: Khi người dùng đứng nghiêng mình hoặc giơ tay trước ngực:
  * Phần cơ thể phía trước sẽ **che khuất (shadow)** toàn bộ phần lưng và các chi phía sau đối với hướng nhìn của radar.
  * *Hậu quả*: Mây điểm thô đột ngột bị "bóp dẹp" thành một dải mỏng hoặc bị chia làm 2 cụm độc lập (ví dụ cụm đầu và cụm chân bị đứt đoạn ở giữa). DBSCAN bị đánh lừa và phân tách thành 2 hộp Bounding Box ảo đè lên nhau, hoặc hộp bị co rúm kích thước dị thường so với hình thể thực tế trên webcam.

```
       Radar Sóng
         |||||
         vvvvv
      [Ngực Người]  <-- Phản xạ mạnh (Có điểm)
      [   Bụng   ]
     /   Occluded \ <-- Vùng bị che bóng (Mù điểm hoàn toàn)
    [    Lưng    ] 
```

### 2. Hiện tượng "Hòa ảnh Vật thể tĩnh" (Respiratory Doppler Bleed & Furniture Fusion)
* **Phân tích phi khuôn khổ**: Trong v12.0, ta hạ thấp ngưỡng `MICRO_MOTION_MIN_SNR = 1.0` tại vùng bảo vệ Confirmed Target để bắt phản xạ hơi thở. Tuy nhiên, điều này tạo ra một tác dụng phụ vật lý cực kỳ thú vị:
* **Hạn chế xảy ra**: Khi người đứng im ngay sát một vật thể tĩnh có khả năng phản xạ mạnh (như ghế văn phòng tựa lưng kim loại, case máy tính, hoặc quạt gió đang quay nhẹ):
  * Sóng phản xạ vi mô từ hơi thở của người dùng sẽ bị "nhập nhầm" hoặc dội ngược qua bề mặt kim loại của chiếc ghế.
  * *Hậu quả*: Radar nhận diện chiếc ghế cũng có "Doppler vi mô" và gộp toàn bộ điểm của chiếc ghế vào cụm cơ thể người. Trên mô phỏng 3D, chiếc hộp Bounding Box đột ngột phình to gấp đôi, nuốt trọn cả chiếc ghế kim loại bên cạnh, tạo ra hiện tượng **"Hòa ảnh người và nội thất" (Furniture Fusion)**.

### 3. Sự suy hao mây điểm ở rìa trường quét (Peripheral Cloud Decay)
* **Phân tích phi khuôn khổ**: Mặt anten của IWR6843AOP là anten phân tán phẳng (Patch Antennas) có giản đồ hướng quét giới hạn ($\pm 60^\circ$ Azimuth).
* **Hạn chế xảy ra**: Khi người dùng bước sang hai mép rìa của góc camera (khoảng $\pm 50^\circ$ đến $\pm 60^\circ$ so với pháp tuyến radar):
  * Độ lợi anten (Antenna Gain) bị suy hao cực mạnh theo hàm Cosine góc quét (sụt giảm từ 3dB đến 6dB).
  * *Hậu quả*: Dù người dùng vẫn hiển thị sáng rõ trên Webcam, mây điểm radar phía góc quét biên lập tức bị thưa thớt nghiêm trọng (chỉ còn 2-3 điểm SNR rất yếu). Hộp bám đuổi bắt đầu rung giật dữ dội, nhảy ID liên tục và biến mất đột ngột mặc dù người dùng chưa hề bước ra khỏi phòng.

```
                  Radar Cảm Biến
                     /   |   \
                    /    |    \
   Cực rìa (-60°)  /     |     \  Cực rìa (+60°)
  [Gain sụt -6dB] /      |      \ [Gain sụt -6dB]
  Mây điểm thưa    /       |       \ Mây điểm thưa
  Hộp rung giật   /        |        \ Hộp rung giật
                 /  Vùng giữa (0°)   \
                [Độ lợi cực đại 0dB]
```

### 4. Hiện tượng "Dội gương đa hướng phi Radial" (Non-Radial Wall Multipath Echoes)
* **Phân tích phi khuôn khổ**: Bộ lọc Ghost Target hiện tại của chúng ta (`suppress_multipath_ghosts`) chỉ lọc được dội gương dạng **Radial** (tức là ghost nằm trên cùng một đường thẳng chĩa từ radar đi qua target chính).
* **Hạn chế xảy ra**: Trong phòng làm việc thực tế có rất nhiều góc tường vuông góc hoặc kính cửa sổ:
  * Sóng radar chéo góc đập vào người dùng $\rightarrow$ nảy vào tường phẳng $\rightarrow$ quay lại radar.
  * *Hậu quả*: Radar tính toán khoảng thời gian bay (ToF) và góc nhận thấy có một mục tiêu ảo nằm góc chéo **bên ngoài bức tường** (nơi không hề có đường thẳng trực tiếp nào nối tới người dùng). Webcam hiển thị một góc phòng trống không, nhưng radar lại vẽ một Bounding Box đứng im nhảy nhót sau bức tường làm nhiễu loạn bộ đếm số người trong phòng.

### 5. Nghẽn cổ chai luồng vẽ đồ họa và trễ gói Serial (Matplotlib GIL & Serialization Choke)
* **Phân tích phi khuôn khổ**: Đây là hạn chế nghiêm trọng về mặt kiến trúc phần mềm Python. Do cơ chế khóa toàn cục GIL (Global Interpreter Lock), toàn bộ việc đọc UART, chạy thuật toán lọc 3D Kalman và vẽ Matplotlib đều chia sẻ chung một tài nguyên CPU.
* **Hạn chế xảy ra**: Khi ta bật tính năng ghi hình đồng bộ v11.0/v12.0:
  * Việc Matplotlib kết xuất canvas đồ họa và OpenCV ghi video chiếm dụng tài nguyên tính toán rất lớn. Canvas Grab mất từ **30ms đến 50ms** mỗi frame.
  * *Hậu quả*: Luồng chính bị tạm dừng (choke) trong vài chục mili-giây. Serial Buffer của hệ điều hành Windows tích lũy dồn ứ dữ liệu UART từ radar. Khi luồng chính được giải phóng, nó phải đọc và parse liên tục 3-4 radar frame cùng lúc để bắt kịp. Trên màn hình, người dùng sẽ thấy hộp Bounding Box di chuyển kiểu giật cục, nhảy cóc (Micro-Stuttering) mặc dù tần số quét vật lý của radar vẫn là 20Hz rất đều đặn.

---

## 🛠️ PHẦN III: HƯỚNG ĐI SÁNG TẠO CHO VERSION TIẾP THEO (V13.0)

Để khắc phục các giới hạn vật lý và đồ họa sâu sắc trên, chúng tôi đề xuất các giải pháp mang tính cách mạng cho **Version 13.0**:

1. **Thuật toán "Neo giữ hình học" (Geometric Anchor Lock)**:
   * Chống hiện tượng Che khuất (Occlusion) và Hòa ảnh nội thất. Khi target đã confirmed đứng im sát ghế, ta khóa chặt thể tích hộp Bounding Box dựa trên lịch sử hình dáng khi người dùng di chuyển trước đó (lưu trữ hình học 3D động), không cho phép hộp phình to hay co rúm theo mây điểm thưa thời gian thực.
2. **Nội suy anten thích nghi biên (Antenna Edge Gain Compensation)**:
   * Tự động nhân hệ số bù SNR dựa trên góc quét Azimuth $\theta$. Điểm ở rìa biên ($|\theta| > 45^\circ$) sẽ được nhân bù độ nhạy để chống lại sự suy hao tự nhiên của cấu trúc anten patch, giữ hộp ổn định ở biên.
3. **Kiến trúc xử lý đa tiến trình song song (Multiprocessing & Asynchronous Render)**:
   * Tách luồng UART Reader, luồng chạy Kalman/DBSCAN và luồng Vẽ đồ họa/Ghi hình Webcam thành 3 Tiến trình (Process) độc lập chia sẻ bộ nhớ chung (Shared Memory). GIL sẽ được giải phóng hoàn chỉnh, triệt tiêu 100% hiện tượng giật cục đồ họa do Serial backlog.
