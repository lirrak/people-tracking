# Bảng Theo Dõi Tiến Độ Thực Hiện Lọc Nhiễu Radar IWR6843AOP (Version 3)

## Phase 1: Noise Filtering & Visualizer Tuning
- `[x]` Tạo thư mục `docs/` lưu trữ tài liệu trong workspace và lưu bản sao của Implementation Plan.
- `[x]` Cấu hình phần cứng: Cập nhật ngưỡng lọc nhiễu CFAR trong `example_configs/3d_people_tracking.cfg`.
- `[x]` Cấu hình phần mềm: Cập nhật các bộ lọc nâng cao trong `settings.py` (ROI, SNR, DBSCAN, Temporal, Ghost).
- `[x]` Kiểm tra cú pháp và cấu trúc file trước khi vận hành.
- `[x]` Lập báo cáo lọc nhiễu chi tiết gửi người dùng.

## Phase 2: Double-box & Ghost-box Fixes
- `[x]` Cập nhật file cấu hình [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
- `[x]` Cập nhật logic lọc Target ROI trong [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
- `[x]` Cập nhật bộ lọc trùng thông minh trong [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)
- `[x]` Chạy kiểm tra cú pháp độc lập (Syntax & Import check)
- `[x]` Khởi chạy hệ thống và theo dõi nhật ký hoạt động (main.py)
- `[x]` Lập tài liệu báo cáo kết quả kiểm thử [walkthrough.md](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/docs/walkthrough.md)

## Phase 3: Erratic Detection & Multi-Target (3-People) Fixes
- `[x]` Cập nhật các cấu hình đa mục tiêu song song trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
- `[x]` Cấu trúc lại bộ lọc thời gian trong [filters.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/filters.py)
- `[x]` Chạy py_compile kiểm tra cú pháp.
- `[x]` Khởi chạy chạy thử nghiệm hệ thống thực tế (main.py).
- `[x]` Tạo báo cáo kết quả kiểm thử đa mục tiêu trong [walkthrough.md](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/docs/walkthrough.md).

## Phase 4: Stateful Tracking Association & Static Clutter Mitigation (Version 4)
- `[x]` Khai báo các cài đặt Static Clutter Filter trong [settings.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/settings.py)
- `[x]` Triển khai lớp stateful `VirtualTargetTracker` trong [pointcloud_processing.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/pointcloud_processing.py)
- `[x]` Cập nhật logic import và khởi tạo `VirtualTargetTracker` trong [main.py](file:///c:/Users/Lirrak/Documents/Born%20Again/Radar%20Project/IWR6843AOP/People%20Tracking/main.py)
- `[x]` Chạy kiểm tra cú pháp biên dịch `py_compile` đảm bảo không có lỗi cú pháp.
- `[x]` Gửi báo cáo hoàn tất thay đổi và báo user preview trước khi chạy kiểm thử thực tế.

