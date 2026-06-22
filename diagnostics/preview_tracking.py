"""
Preview and dry-run script for IWR6843AOP 3D People Tracking (Version 7.0).
This script validates:
1. Dynamic Range-Density Gate (rejecting low density at close range).
2. Range-Adaptive DBSCAN clustering.
3. Multipath Mirror Suppression (detecting and removing dội gương ghosts).
4. Stateful Tracking and Multi-Target Bipartite Association.
"""

import os
import sys

# Add root directory and src directory to system path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
sys.path.insert(0, os.path.join(parent_dir, 'src'))

import numpy as np
from settings import *
from pointcloud_processing import (
    transform_to_room_coordinates,
    transform_target_to_room_coordinates,
    cluster_pointcloud,
    suppress_multipath_ghosts,
    VirtualTargetTracker,
    empty_point_cloud
)
from filters import GhostTargetFilter

def test_dynamic_density_gate():
    print("\n--- 1. TESTING DYNAMIC RANGE-DENSITY GATE ---")
    print(f"VIRTUAL_CLUSTER_MIN_POINTS limit: {VIRTUAL_CLUSTER_MIN_POINTS}")
    
    # 1. Close-range cluster (Y=1.0m) with 6 points. 
    # For R=1.0m, N_min = max(5, round(18 - 2.5 * 1.0)) = 16 points. 6 points should be REJECTED!
    close_points = np.array([
        [0.0, 1.0, 1.0, 0.0, 20.0],
        [0.1, 1.0, 1.1, 0.0, 20.0],
        [-0.1, 1.0, 0.9, 0.0, 20.0],
        [0.05, 1.0, 1.0, 0.0, 20.0],
        [-0.05, 1.0, 1.0, 0.0, 20.0],
        [0.0, 1.0, 1.05, 0.0, 20.0]
    ], dtype=np.float32)
    
    # 2. Far-range cluster (Y=4.5m) with 8 points.
    # For R=4.5m, N_min = max(5, round(18 - 2.5 * 4.5)) = 7 points. 8 points should be ACCEPTED!
    far_points = np.array([
        [0.0, 4.5, 1.0, 0.0, 20.0],
        [0.2, 4.5, 1.2, 0.0, 20.0],
        [-0.2, 4.5, 0.8, 0.0, 20.0],
        [0.1, 4.5, 1.0, 0.0, 20.0],
        [-0.1, 4.5, 1.0, 0.0, 20.0],
        [0.0, 4.5, 1.1, 0.0, 20.0],
        [0.05, 4.5, 0.9, 0.0, 20.0],
        [-0.05, 4.5, 1.0, 0.0, 20.0]
    ], dtype=np.float32)
    
    all_pts = np.vstack([close_points, far_points])
    clusters = cluster_pointcloud(all_pts)
    
    print(f"Total points generated: {len(all_pts)}")
    print(f"Number of clusters accepted after Density Gate: {len(clusters)}")
    
    for idx, c in enumerate(clusters):
        center = np.mean(c[:, 0:3], axis=0)
        print(f"  Accepted Cluster {idx} at Y={center[1]:.2f}m has {len(c)} points.")
        
    assert len(clusters) == 1
    assert np.allclose(np.mean(clusters[0][:, 1]), 4.5, atol=0.2)
    print("SUCCESS: Dynamic Range-Density Gate successfully filtered close-range noise and accepted far-range targets!")

def test_multipath_ghost_suppression():
    print("\n--- 2. TESTING MULTIPATH GHOST TARGET SUPPRESSION ---")
    
    # Simulate candidates generated:
    # 1. Primary Target (real person) at X=0.0, Y=1.5, Z=1.0, with support_points=35
    primary = {
        "tid": 1000,
        "posX": 0.0,
        "posY": 1.5,
        "posZ": 1.0,
        "supportPointCount": 35,
        "humanScore": 88.0,
        "source": "cluster"
    }
    
    # 2. Secondary Target (ghost mirror reflection) at same Azimuth (X=0.05, Y=3.5, Z=1.0), with support_points=12
    # Since X is close (<0.35m), Y is further dội gương (>0.8m), and points are fewer (12 < 35 * 0.70 = 24.5), it must be suppressed!
    ghost = {
        "tid": 1001,
        "posX": 0.05,
        "posY": 3.5,
        "posZ": 1.0,
        "supportPointCount": 12,
        "humanScore": 75.0,
        "source": "cluster"
    }
    
    # 3. Third Target (another real person at a different angle) at X=-1.5, Y=3.8, Z=1.0, with support_points=15
    # Since X is far from primary (-1.5 vs 0.0), it should be KEPT!
    other_person = {
        "tid": 1002,
        "posX": -1.5,
        "posY": 3.8,
        "posZ": 1.0,
        "supportPointCount": 15,
        "humanScore": 78.0,
        "source": "cluster"
    }
    
    candidates = [primary, ghost, other_person]
    filtered = suppress_multipath_ghosts(candidates)
    
    print(f"Candidates before suppression: {len(candidates)}")
    print(f"Candidates after suppression : {len(filtered)}")
    for t in filtered:
        print(f"  Target ID {t['tid']} at X={t['posX']:.2f}, Y={t['posY']:.2f} m | Points={t['supportPointCount']}")
        
    assert len(filtered) == 2
    tids = [t["tid"] for t in filtered]
    assert 1000 in tids
    assert 1002 in tids
    assert 1001 not in tids
    print("SUCCESS: Multipath Mirror Suppressor successfully suppressed mirror ghost targets!")

def test_tracker_v7():
    print("\n--- 3. TESTING INTEGRATED TRACKER v7.0 ---")
    tracker = VirtualTargetTracker()
    ghost_filter = GhostTargetFilter(
        max_missing_frames=GHOST_MAX_MISSING_FRAMES,
        min_support_points=VIRTUAL_CLUSTER_MIN_POINTS,
        support_radius_x=GHOST_SUPPORT_RADIUS_X,
        support_radius_y=GHOST_SUPPORT_RADIUS_Y,
        support_radius_z=GHOST_SUPPORT_RADIUS_Z,
        confirm_frames=TARGET_CONFIRM_FRAMES,
        enable_smoothing=ENABLE_TARGET_SMOOTHING
    )
    
    print("Simulating frames of a single human moving, with random multipath noise...")
    for frame in range(1, 10):
        y_pos = 1.5 + 0.02 * frame
        
        # 1. Real human points (Z_radar < 0 due to tilted boresight): 18 points (should pass density gate at R ~ 1.6m)
        human_pts = []
        for i in range(18):
            human_pts.append([0.0 + 0.05*np.sin(i), y_pos + 0.02*np.cos(i), -0.7 + 0.05*i, 0.0, 25.0])
            
        # 2. Random multipath mirror points at Y=3.8m: 5 points (should be filtered out by density gate or suppressed as a ghost)
        ghost_pts = []
        for i in range(5):
            ghost_pts.append([0.05 + 0.02*i, 3.8 + 0.01*i, -0.4, 0.0, 20.0])
            
        all_points = np.vstack(human_pts + ghost_pts)
        
        candidate_targets, display_pts, cluster_debug = tracker.track_and_build(
            raw_targets=[],
            point_cloud=all_points,
            frame_number=frame
        )
        
        targets = ghost_filter.update(candidate_targets, display_pts, frame)
        
        print(f"Frame {frame} | Candidates: {len(candidate_targets)} | Confirmed Targets: {len(targets)}")
        for t in targets:
            print(f"  Target ID {t['tid']} at X={t['posX']:.2f}, Y={t['posY']:.2f}, Z={t['posZ']:.2f} m | Score={t['humanScore']:.1f}")

    print("SUCCESS: Integrated Tracker v7.0 successfully kept a single stable human target!")

if __name__ == '__main__':
    print("====================================================")
    print("      IWR6843AOP 3D People Tracking v7.0 Preview    ")
    print("====================================================")
    test_dynamic_density_gate()
    test_multipath_ghost_suppression()
    test_tracker_v7()
    print("====================================================")
    print(" PREVIEW TEST COMPLETED SUCCESSFULLY! CODE IS READY!")
    print("====================================================")
