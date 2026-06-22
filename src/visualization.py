"""
2D Circular Radar sweep HUD for mmWave People Tracking.
Fades point cloud and targets dynamically relative to a rotating sweep line.
"""

import time
import numpy as np
import matplotlib.pyplot as plt

from settings import *

# Maintain the exact signature for compatibility
def setup_3d_plot():
    """
    Sets up a 2D Cartesian plot designed to look like a circular radar HUD.
    """
    plt.ion()
    
    # 10x8 figure with pure black background
    fig = plt.figure(figsize=(10, 8), facecolor='#000000')
    ax = fig.add_subplot(111)
    
    # Set pure black background and equal aspect ratio
    ax.set_facecolor('#000000')
    ax.set_aspect('equal')
    
    # Range of display
    ax.set_xlim(-11, 11)
    ax.set_ylim(-11, 11)
    
    # Turn off native axes spines, ticks, and labels
    ax.axis('off')
    
    return fig, ax

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
    """
    Renders the 2D circular radar sweep HUD, fades items based on the sweep angle,
    and draws diagnostic telemetry panels in the corners.
    """
    ax.cla()
    
    # Lock limits and aspect
    ax.set_xlim(-11, 11)
    ax.set_ylim(-11, 11)
    ax.set_aspect('equal')
    ax.axis('off')
    
    # --------------------------------------------------------
    # 1. RENDER RETRO RADAR GRID
    # --------------------------------------------------------
    # Draw dark green square grid in background
    for grid_pos in range(-10, 11, 2):
        ax.plot([grid_pos, grid_pos], [-10, 10], color='#002200', linewidth=0.6, zorder=1)
        ax.plot([-10, 10], [grid_pos, grid_pos], color='#002200', linewidth=0.6, zorder=1)
        
    # Draw concentric range circles (2m, 4m, 6m, 8m, 10m)
    for r in [2, 4, 6, 8, 10]:
        circle = plt.Circle((0, 0), r, fill=False, edgecolor='#004d00', linewidth=1.0, zorder=2)
        ax.add_patch(circle)
        # Range text (placed along vertical/horizontal or offset)
        ax.text(0.15, r + 0.1, f"{r}m", color='#006600', fontsize=8, family='monospace', ha='left', va='bottom', zorder=2)
        
    # Draw crosshairs
    ax.plot([-10, 10], [0, 0], color='#004d00', linewidth=1.2, zorder=2)
    ax.plot([0, 0], [-10, 10], color='#004d00', linewidth=1.2, zorder=2)
    
    # Draw minor radial division lines
    for angle_deg in [30, 60, 120, 150, 210, 240, 300, 330]:
        rad = np.radians(angle_deg)
        ax.plot([-10 * np.sin(rad), 10 * np.sin(rad)], [-10 * np.cos(rad), 10 * np.cos(rad)],
                color='#003300', linewidth=0.8, linestyle=':', zorder=2)
                
    # Draw degree ticks and labels on the outer boundary (R=10)
    for deg in range(0, 360, 10):
        rad = np.radians(deg)
        x1 = 10.0 * np.sin(rad)
        y1 = 10.0 * np.cos(rad)
        x2 = 10.3 * np.sin(rad)
        y2 = 10.3 * np.cos(rad)
        ax.plot([x1, x2], [y1, y2], color='#006600', linewidth=1.0, zorder=2)
        
        if deg % 30 == 0:
            xl = 10.7 * np.sin(rad)
            yl = 10.7 * np.cos(rad)
            ax.text(xl, yl, f"{deg}", color='#00ff00', fontsize=8, family='monospace',
                    ha='center', va='center', zorder=2)

    # --------------------------------------------------------
    # 2. ROTATING SWEEP & PHOSPHOR GLOW
    # --------------------------------------------------------
    # Calculate sweep angle based on system time: 90 deg/sec (4 seconds per rotation)
    sweep_speed = 90.0
    sweep_angle = (time.time() * sweep_speed) % 360.0
    
    # Draw trailing fade wedge (15 thin slices with increasing alpha)
    num_slices = 15
    wedge_width_deg = 45.0
    for i in range(num_slices):
        alpha = (i / num_slices) ** 2 * 0.25  # Exponential alpha fade
        # Calculate bounding angles for slice
        a1 = np.radians(sweep_angle - wedge_width_deg * (num_slices - i) / num_slices)
        a2 = np.radians(sweep_angle - wedge_width_deg * (num_slices - (i + 1)) / num_slices)
        # Polygon vertices
        x_poly = [0, 10.0 * np.sin(a1), 10.0 * np.sin(a2)]
        y_poly = [0, 10.0 * np.cos(a1), 10.0 * np.cos(a2)]
        ax.fill(x_poly, y_poly, color='#00ff00', alpha=alpha, edgecolor='none', zorder=2)
        
    # Draw solid leading sweep line
    lead_rad = np.radians(sweep_angle)
    ax.plot([0, 10.0 * np.sin(lead_rad)], [0, 10.0 * np.cos(lead_rad)],
            color='#00ff00', alpha=0.9, linewidth=2.2, zorder=3)

    # --------------------------------------------------------
    # 3. DRAW POINT CLOUD WITH SWEEP FADE
    # --------------------------------------------------------
    if SHOW_POINT_CLOUD and point_cloud is not None and len(point_cloud) > 0:
        # Calculate angles relative to vertical y-axis
        pt_angles = np.degrees(np.arctan2(point_cloud[:, 0], point_cloud[:, 1])) % 360.0
        # Angular distance behind the sweep line
        pt_diffs = (sweep_angle - pt_angles) % 360.0
        
        # Calculate fade: maximum brightness when freshly swept, down to 0.05 when far/ahead
        pt_alphas = np.where(pt_diffs < 180.0, np.maximum(0.04, 1.0 - (pt_diffs / 180.0)), 0.04)
        
        # Build color array
        pc_colors = np.zeros((len(point_cloud), 4))
        pc_colors[:, 0] = 0.0  # R
        pc_colors[:, 1] = 0.8  # G (Medium bright green)
        pc_colors[:, 2] = 0.0  # B
        pc_colors[:, 3] = pt_alphas * 0.7  # Scale overall brightness
        
        ax.scatter(
            point_cloud[:, 0],
            point_cloud[:, 1],
            s=12,
            color=pc_colors,
            zorder=3
        )

    # --------------------------------------------------------
    # 4. DRAW TARGETS WITH SWEEP FADE
    # --------------------------------------------------------
    height_map = {}
    for height_item in target_heights:
        height_map[height_item["tid"]] = height_item

    if SHOW_TARGETS and targets:
        for target in targets:
            tid = target["tid"]
            x = target["posX"]
            y = target["posY"]
            vx = target["velX"]
            vy = target["velY"]
            is_virtual = target.get("isVirtual", False)
            
            # Calculate angle and sweep fade
            t_ang = np.degrees(np.arctan2(x, y)) % 360.0
            t_diff = (sweep_angle - t_ang) % 360.0
            t_alpha = float(np.where(t_diff < 180.0, np.maximum(0.08, 1.0 - (t_diff / 180.0)), 0.08))
            
            # Target center blip
            ax.scatter([x], [y], s=100, color='#00ff00', edgecolors='none', alpha=t_alpha, zorder=5)
            
            # Target outer glow ring
            glow = plt.Circle((x, y), 0.6, fill=True, color='#00ff00', alpha=t_alpha * 0.15, zorder=4)
            ax.add_patch(glow)
            
            # Text block labels: TID, height, confidence score, source
            h_val = 1.7
            if tid in height_map:
                h_val = height_map[tid]["maxZ"] - height_map[tid]["minZ"]
                if not np.isfinite(h_val) or h_val <= 0:
                    h_val = 1.7
                    
            score_val = target.get("humanScore", 0.0)
            
            lbl = f"TID {tid:02d}\nH:{h_val:.1f}m\nS:{score_val:.0f}"
            if is_virtual:
                lbl += "\n[VIR]"
            
            ax.text(x + 0.35, y, lbl, color='#00ff00', fontsize=8, alpha=t_alpha,
                    family='monospace', fontweight='bold', va='center', zorder=5)
            
            # Velocity vector
            if SHOW_TARGET_VELOCITY:
                ax.quiver(
                    x, y, vx, vy,
                    angles='xy', scale_units='xy', scale=2.5,
                    color='#00ff00', alpha=t_alpha, width=0.005, zorder=5
                )
                
            # Track history
            if SHOW_TRACK_HISTORY:
                history = track_history.get(tid)
                if len(history) >= 2:
                    hist_np = np.array(history)
                    ax.plot(
                        hist_np[:, 0],
                        hist_np[:, 1],
                        color='#008000',
                        linewidth=1.2,
                        linestyle=':',
                        alpha=t_alpha * 0.5,
                        zorder=4
                    )

    # --------------------------------------------------------
    # 5. DRAW SENSOR ICON (CENTER)
    # --------------------------------------------------------
    ax.scatter([0], [0], s=160, marker='^', facecolor='#00ff00', edgecolor='none', zorder=6)
    ax.text(0, -0.6, "SENSOR", color='#00ff00', fontsize=8, family='monospace', fontweight='bold', ha='center', va='top')

    # --------------------------------------------------------
    # 6. CORNER HUD WIDGETS
    # --------------------------------------------------------
    # Header Title
    ax.text(0.0, 10.4, f"IWR6843AOP RADAR RECEIVER v25.0 | MODE: {mode} | FRAME {frame_number}",
            color='#00ff00', fontsize=9, family='monospace', fontweight='bold', ha='center', va='center')
            
    # Top-Left Widget: SYS STATUS (Level Bars)
    ax.text(-9.5, 9.5, "SYS STATUS", color='#00ff00', fontsize=8, family='monospace', fontweight='bold')
    bar_y = [9.0, 8.7, 8.4, 8.1]
    bar_w = [1.8, 1.3, 1.6, 0.9]
    for y_pos, w in zip(bar_y, bar_w):
        rect = plt.Rectangle((-9.5, y_pos), w, 0.16, facecolor='#00ff00', edgecolor='none', alpha=0.8)
        ax.add_patch(rect)
        
    # Draw status info inside Top-Left quadrant
    clean_status = status_text.replace("Status: ", "")
    ax.text(-9.5, 7.5, clean_status, color='#00aa00', fontsize=7, family='monospace')
    ax.text(-9.5, 6.7, parser_status[:75], color='#008800', fontsize=7, family='monospace', wrap=True)

    # Top-Right Widget: SIGNAL WAVE (Fluctuating Waveform)
    rect_tr = plt.Rectangle((6.5, 7.5), 3.0, 2.0, fill=False, edgecolor='#004d00', linewidth=1.0)
    ax.add_patch(rect_tr)
    ax.text(6.6, 9.2, "SIGNAL WAVE", color='#00ff00', fontsize=7, family='monospace', fontweight='bold')
    
    wave_x = np.linspace(6.6, 9.4, 40)
    t_val = time.time()
    wave_y = 8.4 + 0.4 * np.sin(4 * wave_x + 8 * t_val) + 0.2 * np.sin(10 * wave_x - 5 * t_val) + np.random.normal(0, 0.04, 40)
    wave_y = np.clip(wave_y, 7.6, 9.4)
    ax.plot(wave_x, wave_y, color='#00ff00', linewidth=0.9, alpha=0.8)

    # Bottom-Left Widget: GEOMETRIC ANCHOR (Rotating 3D-like Sphere)
    globe_cx, globe_cy = -8.0, -8.0
    globe_r = 0.95
    # Outer circle
    globe_outer = plt.Circle((globe_cx, globe_cy), globe_r, fill=False, edgecolor='#00ff00', linewidth=0.9, alpha=0.6)
    ax.add_patch(globe_outer)
    # Latitude lines
    for h in [-0.6, -0.3, 0.0, 0.3, 0.6]:
        r_slice = np.sqrt(globe_r**2 - h**2)
        theta_vals = np.linspace(0, 2 * np.pi, 40)
        x_el = globe_cx + r_slice * np.cos(theta_vals)
        y_el = globe_cy + h + 0.15 * r_slice * np.sin(theta_vals)
        ax.plot(x_el, y_el, color='#004d00', linewidth=0.5, alpha=0.5)
    # Longitude lines
    for angle in [0, 45, 90, 135]:
        rad = np.radians(angle + t_val * 15.0)  # Spin globe slowly over time!
        theta_vals = np.linspace(-np.pi/2, np.pi/2, 40)
        x_m = globe_cx + globe_r * np.cos(rad) * np.sin(theta_vals)
        y_m = globe_cy + globe_r * np.sin(rad) * np.sin(theta_vals)
        ax.plot(x_m, y_m, color='#004d00', linewidth=0.5, alpha=0.5)
    ax.text(-9.5, -9.6, "GEOMETRIC ANCHOR", color='#00ff00', fontsize=7, family='monospace', fontweight='bold')

    # Bottom-Right Widget: SPECTRUM (Equalizer Bars)
    rect_br = plt.Rectangle((6.5, -9.5), 3.0, 2.0, fill=False, edgecolor='#004d00', linewidth=1.0)
    ax.add_patch(rect_br)
    ax.text(6.6, -7.8, "SPECTRUM", color='#00ff00', fontsize=7, family='monospace', fontweight='bold')
    
    num_bars = 8
    bar_width = 0.22
    bar_gap = 0.12
    start_bx = 6.7
    for bar_idx in range(num_bars):
        # Dynamic height based on index and time
        h_bar = 0.2 + 1.45 * abs(np.sin(bar_idx * 0.6 + t_val * 2.5)) + np.random.uniform(0, 0.08)
        bx = start_bx + bar_idx * (bar_width + bar_gap)
        by = -9.4
        rect_b = plt.Rectangle((bx, by), bar_width, h_bar, facecolor='#00ff00', edgecolor='none', alpha=0.85)
        ax.add_patch(rect_b)

    # Trigger canvas updates to draw and show frame
    fig.canvas.draw_idle()
    fig.canvas.flush_events()
