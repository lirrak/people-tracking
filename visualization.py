"""
3D visualization helpers for point cloud, targets, sensor box, and human box.
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from settings import *


# ============================================================
# VISUALIZATION HELPERS
# ============================================================

def setup_3d_plot():
    plt.ion()

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    return fig, ax


def draw_wireframe_box_3d(
    ax,
    center,
    size,
    label=None,
    linewidth=1.8,
    alpha=1.0
):
    """
    Vẽ hộp wireframe 3D.

    center = (cx, cy, cz)
    size   = (width_x, depth_y, height_z)
    """

    cx, cy, cz = center
    width_x, depth_y, height_z = size

    sx = width_x / 2.0
    sy = depth_y / 2.0
    sz = height_z / 2.0

    vertices = np.array([
        [cx - sx, cy - sy, cz - sz],
        [cx + sx, cy - sy, cz - sz],
        [cx + sx, cy + sy, cz - sz],
        [cx - sx, cy + sy, cz - sz],
        [cx - sx, cy - sy, cz + sz],
        [cx + sx, cy - sy, cz + sz],
        [cx + sx, cy + sy, cz + sz],
        [cx - sx, cy + sy, cz + sz],
    ])

    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]

    first_edge = True

    for edge_start, edge_end in edges:
        ax.plot(
            [vertices[edge_start, 0], vertices[edge_end, 0]],
            [vertices[edge_start, 1], vertices[edge_end, 1]],
            [vertices[edge_start, 2], vertices[edge_end, 2]],
            linewidth=linewidth,
            alpha=alpha,
            label=label if first_edge and label else None
        )
        first_edge = False


def get_human_box_from_target(target, height_map):
    """
    Tạo hộp bao quanh người từ target.

    Ưu tiên:
    1. Nếu ENABLE_GEOMETRIC_ANCHOR_LOCK -> Khóa cứng kích thước hộp hình dạng người mặc định
    2. Nếu không có -> dùng chiều cao từ TLV hoặc hộp mặc định co giãn
    """

    tid = target["tid"]

    x = target["posX"]
    y = target["posY"]
    z = target["posZ"]

    # Áp dụng Neo giữ hình học (Version 13.0)
    if ENABLE_GEOMETRIC_ANCHOR_LOCK if 'ENABLE_GEOMETRIC_ANCHOR_LOCK' in globals() else True:
        width_x = HUMAN_BOX_DEFAULT_WIDTH_X
        depth_y = HUMAN_BOX_DEFAULT_DEPTH_Y
        height_z = HUMAN_BOX_DEFAULT_HEIGHT_Z
        center_z = z
        if not np.isfinite(center_z):
            center_z = height_z / 2.0
    else:
        width_x = HUMAN_BOX_DEFAULT_WIDTH_X
        depth_y = HUMAN_BOX_DEFAULT_DEPTH_Y

        if USE_TARGET_HEIGHT_FOR_HUMAN_BOX and tid in height_map:
            min_z = height_map[tid]["minZ"]
            max_z = height_map[tid]["maxZ"]

            height_z = max_z - min_z

            if not np.isfinite(height_z) or height_z <= 0:
                height_z = HUMAN_BOX_DEFAULT_HEIGHT_Z
                center_z = z
            else:
                height_z = max(
                    HUMAN_BOX_MIN_HEIGHT_Z,
                    min(HUMAN_BOX_MAX_HEIGHT_Z, height_z)
                )
                center_z = (min_z + max_z) / 2.0

        else:
            height_z = HUMAN_BOX_DEFAULT_HEIGHT_Z
            center_z = z
            if not np.isfinite(center_z):
                center_z = height_z / 2.0

    center = (x, y, center_z)
    size = (width_x, depth_y, height_z)

    return center, size


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



def draw_floor_box(ax):
    x_min, x_max = X_LIMIT
    y_min, y_max = Y_LIMIT
    z_floor = 0.0

    floor_x = [x_min, x_max, x_max, x_min, x_min]
    floor_y = [y_min, y_min, y_max, y_max, y_min]
    floor_z = [z_floor, z_floor, z_floor, z_floor, z_floor]

    ax.plot(floor_x, floor_y, floor_z, linewidth=1.0)


def update_3d_plot(
    fig,
    ax,
    point_cloud,
    targets,
    target_heights,
    track_history,
    frame_number,
    presence,
    mode,
    status_text,
    parser_status
):
    ax.cla()

    # Đặt góc nhìn Camera khớp hoàn toàn với vị trí và độ nghiêng vật lý của Radar/Webcam (Version 14.0)
    if ENABLE_CAMERA_VIEW_LOCK if 'ENABLE_CAMERA_VIEW_LOCK' in globals() else True:
        ax.view_init(elev=RADAR_TILT_ANGLE_DEG if 'RADAR_TILT_ANGLE_DEG' in globals() else 30.0, azim=-90)

    ax.set_title(
        f"IWR6843AOP Viewer | Mode: {mode} | Frame {frame_number} | "
        f"Targets: {len(targets)} | Presence: {presence}"
    )

    ax.set_xlabel("X left/right [m]")
    ax.set_ylabel("Y forward [m]")
    ax.set_zlabel("Z height [m]")

    ax.set_xlim(X_LIMIT)
    ax.set_ylim(Y_LIMIT)
    ax.set_zlim(Z_LIMIT)

    draw_floor_box(ax)
    draw_sensor_box_3d(ax)

    if SHOW_POINT_CLOUD and point_cloud is not None and len(point_cloud) > 0:
        ax.scatter(
            point_cloud[:, 0],
            point_cloud[:, 1],
            point_cloud[:, 2],
            s=10,
            alpha=0.45,
            label="Point Cloud"
        )

    height_map = {}

    for height_item in target_heights:
        height_map[height_item["tid"]] = height_item

    if SHOW_TARGETS and targets:
        for target in targets:
            tid = target["tid"]

            x = target["posX"]
            y = target["posY"]
            z = target["posZ"]

            vx = target["velX"]
            vy = target["velY"]
            vz = target["velZ"]

            is_virtual = target.get("isVirtual", False)

            # -----------------------------
            # Human box
            # -----------------------------
            if SHOW_HUMAN_BOX:
                human_box_center, human_box_size = get_human_box_from_target(
                    target,
                    height_map
                )

                box_label = None

                if SHOW_HUMAN_BOX_LABEL:
                    if is_virtual:
                        box_label = f"Human box ID {tid} PC"
                    else:
                        box_label = f"Human box ID {tid}"

                draw_wireframe_box_3d(
                    ax=ax,
                    center=human_box_center,
                    size=human_box_size,
                    label=box_label,
                    linewidth=1.8,
                    alpha=0.95
                )

            # -----------------------------
            # Target center
            # -----------------------------
            target_label = f"Target {tid}"
            if is_virtual:
                target_label += " (PointCloud)"

            ax.scatter(
                [x],
                [y],
                [z],
                s=100,
                marker="o",
                label=target_label
            )

            label_text = f"ID {tid}"
            if is_virtual:
                label_text += "\nPC detect"
            if "supportPointCount" in target:
                label_text += f"\npts {target['supportPointCount']}"
            if "humanScore" in target:
                label_text += f"\nscore {target['humanScore']:.0f}"
            if target.get("source") == "cluster":
                label_text += "\ncluster"

            ax.text(
                x,
                y,
                z + 0.15,
                label_text,
                ha="center"
            )

            # -----------------------------
            # Velocity vector
            # -----------------------------
            if SHOW_TARGET_VELOCITY:
                ax.quiver(
                    x,
                    y,
                    z,
                    vx,
                    vy,
                    vz,
                    length=0.5,
                    normalize=False,
                    arrow_length_ratio=0.25
                )

            # -----------------------------
            # Track history
            # -----------------------------
            if SHOW_TRACK_HISTORY:
                history = track_history.get(tid)

                if len(history) >= 2:
                    history_np = np.array(history)

                    ax.plot(
                        history_np[:, 0],
                        history_np[:, 1],
                        history_np[:, 2],
                        linewidth=1.5
                    )

            # -----------------------------
            # Target height line, if available
            # -----------------------------
            if tid in height_map:
                min_z = height_map[tid]["minZ"]
                max_z = height_map[tid]["maxZ"]

                ax.plot(
                    [x, x],
                    [y, y],
                    [min_z, max_z],
                    linewidth=2.0
                )

    ax.text2D(
        0.02,
        0.96,
        status_text,
        transform=ax.transAxes
    )

    ax.text2D(
        0.02,
        0.91,
        parser_status,
        transform=ax.transAxes
    )

    ax.legend(loc="upper right")

    fig.canvas.draw_idle()
    fig.canvas.flush_events()
