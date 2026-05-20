"""
User-editable settings for IWR6843AOP radar viewer.
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
PLOT_EVERY_N_FRAMES = 2

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

HUMAN_ROI_X = (-2.5, 2.5)
HUMAN_ROI_Y = (0.3, 6.0)
HUMAN_ROI_Z = (-0.5, 2.5)
HUMAN_MIN_POINTS = 5

# ============================================================
# GHOST TARGET FILTER SETTINGS
# ============================================================

# Bật bộ lọc box ảo / target cũ
ENABLE_GHOST_TARGET_FILTER = True

# Số frame giữ lại target khi không còn point cloud hỗ trợ.
# Giảm xuống 3 nếu box vẫn tồn tại quá lâu sau khi người rời đi.
GHOST_MAX_MISSING_FRAMES = 6

# Số point tối thiểu gần target để coi target còn thật.
GHOST_MIN_SUPPORT_POINTS = 2

# Bán kính tìm point cloud xung quanh target.
GHOST_SUPPORT_RADIUS_X = 0.75
GHOST_SUPPORT_RADIUS_Y = 0.75
GHOST_SUPPORT_RADIUS_Z = 1.30

# Nếu 2 target quá gần nhau, giữ target có nhiều support points hơn.
# Giảm xuống 0.55 nếu muốn tách người đứng gần nhau mạnh hơn.
# Tăng lên 0.90 nếu vẫn bị 1 người hiện 2 box.
GHOST_DUPLICATE_DISTANCE_XY = 0.75

# Nếu True: không vẽ target không có point cloud hỗ trợ ngay lập tức.
# Nếu False: vẫn giữ trong GHOST_MAX_MISSING_FRAMES frame.
GHOST_DROP_UNSUPPORTED_IMMEDIATELY = False


# ============================================================
# POINT CLOUD HUMAN DETECTION SETTINGS
# ============================================================

# Bật bộ xử lý point cloud nâng cao:
# ROI filter -> clustering -> human confidence score -> target fusion.
ENABLE_POINTCLOUD_HUMAN_PROCESSOR = True

# Nếu True: viewer chỉ vẽ point cloud đã lọc trong vùng người.
# Nếu False: vẫn vẽ toàn bộ point cloud gốc.
SHOW_FILTERED_POINT_CLOUD_ONLY = True

# ROI lọc điểm có khả năng thuộc người.
# Chỉnh theo vùng test thực tế của bạn.
PC_ROI_X = (-3.5, 3.5)
PC_ROI_Y = (0.4, 7.0)
PC_ROI_Z = (0.2, 2.6)

# DBSCAN clustering.
# eps nhỏ hơn giúp tách người gần nhau tốt hơn nhưng có thể làm cụm bị vỡ.
# eps lớn hơn giúp gom point cloud thưa nhưng dễ gộp 2 người thành 1.
CLUSTER_EPS = 0.50
CLUSTER_MIN_SAMPLES = 3
CLUSTER_MIN_POINTS = 3

# Ngưỡng human score.
# Tăng nếu bị false detect / ghost.
# Giảm nếu người thật bị mất box.
HUMAN_SCORE_THRESHOLD = 65.0
HUMAN_SCORE_TARGET_THRESHOLD = 40.0

# Khi tạo virtual target từ cluster, nếu cluster quá gần target firmware
# thì không tạo thêm box để tránh 1 người có 2 box.
CLUSTER_TO_TARGET_MIN_DISTANCE_XY = 0.75


# ============================================================
# VIRTUAL CLUSTER TARGET CONTROL
# ============================================================

# Nếu True, cho phép tạo human box từ point cloud cluster khi firmware chưa có target.
# Nếu trước radar chỉ có 1 người nhưng bị hiện nhiều box ID 1000, 1001,...
# thì nguyên nhân thường nằm ở virtual cluster targets này.
ENABLE_VIRTUAL_CLUSTER_TARGETS = True

# Chỉ tạo box ảo từ point cloud khi firmware không trả target thật.
# Đây là chế độ ổn định nhất để tránh duplicate box.
VIRTUAL_CLUSTER_ONLY_WHEN_NO_FIRMWARE_TARGETS = True

# Gộp nhiều cluster nhỏ trên cùng một cơ thể thành 1 người.
# Tăng lên 1.20 nếu 1 người vẫn bị tách nhiều box.
# Giảm xuống 0.70 nếu nhiều người đứng gần nhau bị gộp.
VIRTUAL_CLUSTER_MERGE_DISTANCE_XY = 1.00

# Sau khi gộp cluster, cụm phải đủ điểm và đủ score mới tạo box ảo.
VIRTUAL_CLUSTER_MIN_POINTS = 6
VIRTUAL_CLUSTER_SCORE_THRESHOLD = 65.0

# Giới hạn số virtual target tối đa để tránh loạn khi point cloud nhiễu.
VIRTUAL_CLUSTER_MAX_TARGETS = 3

# Bán kính lấy point cloud quanh target firmware khi target_index không dùng được.
TARGET_SUPPORT_RADIUS_X = 0.75
TARGET_SUPPORT_RADIUS_Y = 0.75
TARGET_SUPPORT_RADIUS_Z = 1.30

# Sử dụng target_index TLV nếu firmware trả về.
# target_index giúp biết point nào thuộc target ID nào.
USE_TARGET_INDEX_ASSOCIATION = True

# ID bắt đầu cho các target ảo sinh ra từ point cloud cluster.
VIRTUAL_TARGET_ID_BASE = 1000

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
HUMAN_BOX_DEFAULT_WIDTH_X = 1.0
HUMAN_BOX_DEFAULT_DEPTH_Y = 1.0
HUMAN_BOX_DEFAULT_HEIGHT_Z = 1.8

# Độ cao tối thiểu/tối đa để tránh hộp quá dị
HUMAN_BOX_MIN_HEIGHT_Z = 0.5
HUMAN_BOX_MAX_HEIGHT_Z = 2.5

# Có hiển thị chữ trên hộp người không
SHOW_HUMAN_BOX_LABEL = True
