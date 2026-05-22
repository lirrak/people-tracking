"""
User-editable settings for IWR6843AOP radar viewer.

This version focuses on improving human detection stability:
- tighter point-cloud ROI
- point quality filtering
- stronger human-shape scoring
- multi-frame confirmation
- target smoothing
"""

import os

# ============================================================
# USER SETTINGS
# ============================================================

CFG_PORT = "COM13"
DATA_PORT = "COM14"

CFG_BAUDRATE = 115200
DATA_BAUDRATE = 921600

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE_PATH = os.path.join(
    BASE_DIR,
    "example_configs",
    "3d_people_tracking.cfg"
)

# Nếu True: không gửi config, chỉ đọc DATA UART
SKIP_CONFIG = False

# Vẽ mỗi N frame radar
PLOT_EVERY_N_FRAMES = 1

# Refresh GUI để không bị Not Responding
GUI_REFRESH_INTERVAL_SEC = 0.05

# Nếu không có data trong khoảng này thì báo rõ
NO_DATA_WARNING_SEC = 3.0

# Debug
PRINT_UART_DEBUG = True
PRINT_FRAME_DEBUG = True
PRINT_FRAME_DEBUG_EVERY_N_FRAMES = 10

# Giới hạn vùng hiển thị
X_LIMIT = (-5, 5)
Y_LIMIT = (0, 10)
Z_LIMIT = (-2, 3)

SHOW_POINT_CLOUD = True
SHOW_TARGETS = True
SHOW_TRACK_HISTORY = True
SHOW_TARGET_VELOCITY = True

# Nếu chưa có target list, thử detect người đơn giản từ point cloud
ENABLE_SIMPLE_POINTCLOUD_HUMAN_DETECT = True

HUMAN_ROI_X = (-3.0, 3.0)
HUMAN_ROI_Y = (0.30, 6.5)
HUMAN_ROI_Z = (0.05, 2.50)
HUMAN_MIN_POINTS = 2

# ============================================================
# POINT CLOUD HUMAN DETECTION SETTINGS
# ============================================================

# Bật bộ xử lý point cloud nâng cao:
# ROI filter -> quality filter -> clustering -> human confidence score -> target fusion.
ENABLE_POINTCLOUD_HUMAN_PROCESSOR = True

# Nếu True: viewer chỉ vẽ point cloud đã lọc trong vùng người.
# Nếu False: vẫn vẽ toàn bộ point cloud gốc.
SHOW_FILTERED_POINT_CLOUD_ONLY = True

# ROI lọc điểm có khả năng thuộc người.
# Với radar đặt cao khoảng 60 cm và chĩa xuống, nên tránh vùng sát sàn.
# Nếu người thật bị mất chân/body thấp, giảm PC_ROI_Z[0] xuống 0.15 hoặc 0.10.
# Nếu nhiễu sàn nhiều, tăng PC_ROI_Z[0] lên 0.35 hoặc 0.45.
PC_ROI_X = (-3.0, 3.0)
PC_ROI_Y = (0.30, 6.5)
PC_ROI_Z = (0.20, 2.50)

# ROI lọc tâm target phần cứng/phần mềm để tránh phản xạ sàn dưới âm (Double Box)
TARGET_ROI_Z = (-0.15, 2.20)

# Lọc chất lượng point cloud.
# Cột thứ 5 trong point cloud của TI thường là SNR/intensity.
# Nếu parser trả SNR = 0 cho toàn bộ point cloud, bộ lọc SNR sẽ tự bỏ qua.
ENABLE_POINT_QUALITY_FILTER = True
MIN_POINT_SNR = 1.5
MAX_POINT_SNR = 300.0

# Lọc Doppler rất lớn bất thường. Người thường không tạo vận tốc quá cao trong indoor test.
ENABLE_DOPPLER_OUTLIER_FILTER = True
MAX_ABS_DOPPLER = 4.0

# DBSCAN clustering.
# eps nhỏ hơn giúp tách người gần nhau tốt hơn nhưng có thể làm cụm bị vỡ.
# eps lớn hơn giúp gom point cloud thưa nhưng dễ gộp 2 người thành 1.
CLUSTER_EPS = 0.50
CLUSTER_MIN_SAMPLES = 3
CLUSTER_MIN_POINTS = 3

# Điều kiện hình học cơ bản của một cụm giống người.
# Các giá trị này giúp loại bỏ nhiễu sàn / cạnh bàn / mảng tường.
HUMAN_CLUSTER_MIN_HEIGHT_Z = 0.08
HUMAN_CLUSTER_MAX_HEIGHT_Z = 2.20
HUMAN_CLUSTER_MIN_WIDTH_X = 0.05
HUMAN_CLUSTER_MAX_WIDTH_X = 1.50
HUMAN_CLUSTER_MAX_DEPTH_Y = 1.60
HUMAN_CLUSTER_MIN_CENTER_Z = 0.08
HUMAN_CLUSTER_MAX_CENTER_Z = 1.80

# Ngưỡng human score.
# Tăng nếu bị false detect / ghost.
# Giảm nếu người thật bị mất box.
HUMAN_SCORE_THRESHOLD = 52.0
HUMAN_SCORE_TARGET_THRESHOLD = 28.0

# Khi tạo virtual target từ cluster, nếu cluster quá gần target firmware
# thì không tạo thêm box để tránh 1 người có 2 box.
CLUSTER_TO_TARGET_MIN_DISTANCE_XY = 0.85

# ============================================================
# VIRTUAL CLUSTER TARGET CONTROL
# ============================================================

# Nếu True, cho phép tạo human box từ point cloud cluster khi firmware chưa có target.
ENABLE_VIRTUAL_CLUSTER_TARGETS = True

# Chỉ tạo box ảo từ point cloud khi firmware không trả target thật.
# Đây là chế độ ổn định nhất để tránh duplicate box.
VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS = False

# Gộp nhiều cluster nhỏ trên cùng một cơ thể thành 1 người.
# Tăng lên 1.20 nếu 1 người vẫn bị tách nhiều box.
# Giảm xuống 0.70 nếu nhiều người đứng gần nhau bị gộp.
VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 0.85

# Sau khi gộp cluster, cụm phải đủ điểm và đủ score mới tạo box ảo.
VIRTUAL_CLUSTER_MIN_POINTS = 2
VIRTUAL_CLUSTER_SCORE_THRESHOLD = 52.0

# Giới hạn số virtual target tối đa để tránh loạn khi point cloud nhiễu.
VIRTUAL_CLUSTER_MAX_TARGETS = 3

# Bán kính lấy point cloud quanh target firmware khi target_index không dùng được.
TARGET_SUPPORT_RADIUS_X = 0.85
TARGET_SUPPORT_RADIUS_Y = 0.85
TARGET_SUPPORT_RADIUS_Z = 1.20

# Sử dụng target_index TLV nếu firmware trả về.
# target_index giúp biết point nào thuộc target ID nào.
USE_TARGET_INDEX_ASSOCIATION = True

# ID bắt đầu cho các target ảo sinh ra từ point cloud cluster.
VIRTUAL_TARGET_ID_BASE = 1000

# Khoảng cách tối đa giữa các frame để so khớp kế thừa ID ảo (mét).
# Cho phép cụm mây điểm di chuyển linh hoạt vẫn giữ được đúng mã định danh cũ.
VIRTUAL_TRACKER_ASSOCIATION_RADIUS = 1.30


# ============================================================
# STATIC CLUTTER FILTER SETTINGS (Version 4)
# ============================================================
ENABLE_STATIC_CLUTTER_FILTER = True
STATIC_CLUTTER_MIN_FRAMES = 15       # Số frame để bắt đầu lọc vật thể tĩnh
STATIC_CLUTTER_MAX_STD = 0.05       # Độ lệch chuẩn XY tối đa để coi là đứng im hoàn toàn (đồ vật)
STATIC_CLUTTER_MAX_DOPPLER = 0.04   # Vận tốc Doppler trung bình tối đa của vật thể tĩnh (m/s)


# ============================================================
# TEMPORAL POINT CLOUD STABILIZER
# ============================================================

# Gom point cloud trong vài frame gần nhất để giảm chập chờn.
# Nên bật khi point cloud từ người bị thưa / nhấp nháy.
ENABLE_POINTCLOUD_TEMPORAL_STABILIZER = True

# Số frame giữ lại. 2-3 là an toàn. Cao quá sẽ tạo ghost point.
POINTCLOUD_STABILIZER_MAX_AGE_FRAMES = 5

# Kích thước voxel để kiểm tra điểm có xuất hiện ổn định gần cùng vị trí không.
# Nhỏ hơn: lọc nhiễu mạnh hơn nhưng dễ mất người.
# Lớn hơn: giữ người tốt hơn nhưng có thể giữ nhiễu.
POINTCLOUD_STABILIZER_VOXEL_SIZE_X = 0.38
POINTCLOUD_STABILIZER_VOXEL_SIZE_Y = 0.38
POINTCLOUD_STABILIZER_VOXEL_SIZE_Z = 0.45

# Một voxel phải xuất hiện trong ít nhất N frame mới được xem là ổn định.
# 2 là cân bằng tốt giữa ổn định và không mất người.
POINTCLOUD_STABILIZER_MIN_VOXEL_HITS = 2

# Giữ lại điểm của frame hiện tại để người mới xuất hiện không bị trễ quá lâu.
POINTCLOUD_STABILIZER_KEEP_CURRENT_FRAME = False

# Giới hạn số point sau khi cộng dồn để tránh GUI chậm.
POINTCLOUD_STABILIZER_MAX_POINTS = 400

# ============================================================
# GHOST TARGET FILTER + TEMPORAL STABILITY
# ============================================================

# Bật bộ lọc box ảo / target cũ
ENABLE_GHOST_TARGET_FILTER = True

# Cần bao nhiêu frame liên tiếp trước khi xác nhận target mới.
# Tăng lên 3 nếu detect loạn. Giảm xuống 1 nếu người thật bị chậm hiện box.
TARGET_CONFIRM_FRAMES = 4

# Có áp dụng confirm frame cho firmware target không?
# False: firmware target hiện nhanh hơn.
# True: ổn định hơn nhưng box hiện chậm hơn.
APPLY_CONFIRMATION_TO_FIRMWARE_TARGETS = True

# Số frame giữ lại target khi không còn point cloud hỗ trợ.
# Giảm xuống 2 hoặc 3 nếu box vẫn tồn tại quá lâu sau khi người rời đi.
GHOST_MAX_MISSING_FRAMES = 5

# Số point tối thiểu gần target để coi target còn thật.
GHOST_MIN_SUPPORT_POINTS = 3

# Bán kính tìm point cloud xung quanh target.
GHOST_SUPPORT_RADIUS_X = 0.85
GHOST_SUPPORT_RADIUS_Y = 0.85
GHOST_SUPPORT_RADIUS_Z = 1.20

# Nếu 2 target quá gần nhau, giữ target có nhiều support points hơn.
# Tăng lên 1.15 để gộp trùng tốt hơn (chống Double Box).
GHOST_DUPLICATE_DISTANCE_XY = 1.15

# Nếu True: không vẽ target không có point cloud hỗ trợ ngay lập tức.
# Nếu False: vẫn giữ trong GHOST_MAX_MISSING_FRAMES frame.
GHOST_DROP_UNSUPPORTED_IMMEDIATELY = False

# Target smoothing giúp box không bị giật.
# alpha cao: bám nhanh nhưng rung hơn. alpha thấp: mượt hơn nhưng trễ hơn.
ENABLE_TARGET_SMOOTHING = True
TARGET_SMOOTHING_ALPHA = 0.28

# Nếu target nhảy quá xa giữa 2 frame, không smoothing theo target cũ nữa.
TARGET_SMOOTHING_RESET_DISTANCE = 1.60

# ============================================================
# SENSOR BOX DISPLAY
# ============================================================

SHOW_SENSOR_BOX = True

SENSOR_X = 0.0
SENSOR_Y = 0.0
SENSOR_Z = 0.0

SENSOR_BOX_SIZE_X = 0.30
SENSOR_BOX_SIZE_Y = 0.18
SENSOR_BOX_SIZE_Z = 0.10

SHOW_SENSOR_LABEL = True

# ============================================================
# HUMAN BOX DISPLAY
# ============================================================

SHOW_HUMAN_BOX = True

# Nếu firmware có target height TLV, dùng minZ/maxZ thật
USE_TARGET_HEIGHT_FOR_HUMAN_BOX = True

# Kích thước hộp mặc định nếu không có target height TLV
HUMAN_BOX_DEFAULT_WIDTH_X = 0.85
HUMAN_BOX_DEFAULT_DEPTH_Y = 0.85
HUMAN_BOX_DEFAULT_HEIGHT_Z = 1.70

# Độ cao tối thiểu/tối đa để tránh hộp quá dị
HUMAN_BOX_MIN_HEIGHT_Z = 0.5
HUMAN_BOX_MAX_HEIGHT_Z = 2.3

# Có hiển thị chữ trên hộp người không
SHOW_HUMAN_BOX_LABEL = True
