# IWR6843AOP Modular Radar Viewer - Point Cloud Human Processor

This version keeps the original UART parser/viewer structure and adds the advanced point-cloud pipeline:

1. ROI filter for human-height points
2. DBSCAN clustering
3. Human confidence score
4. `target_index` association when available
5. Firmware target + cluster fusion
6. Ghost target filter before drawing human boxes

## Run

```bash
cd iwr6843aop_modular_pointcloud_ai
python main.py
```

## Optional dependency

The code runs without scikit-learn using a built-in fallback DBSCAN. For better clustering speed/quality, install:

```bash
pip install scikit-learn
```

## Main tuning file

Edit `settings.py`. Useful values:

```python
CLUSTER_EPS = 0.50
CLUSTER_MIN_SAMPLES = 3
HUMAN_SCORE_THRESHOLD = 45.0
HUMAN_SCORE_TARGET_THRESHOLD = 35.0
CLUSTER_TO_TARGET_MIN_DISTANCE_XY = 0.75
GHOST_MAX_MISSING_FRAMES = 6
GHOST_DUPLICATE_DISTANCE_XY = 0.75
```

If one real person becomes two boxes, increase:

```python
CLUSTER_TO_TARGET_MIN_DISTANCE_XY = 0.90
GHOST_DUPLICATE_DISTANCE_XY = 0.90
```

If three nearby people are merged into two boxes, decrease:

```python
CLUSTER_EPS = 0.42
GHOST_DUPLICATE_DISTANCE_XY = 0.55
```

If ghost boxes remain after the person leaves, increase strictness:

```python
HUMAN_SCORE_TARGET_THRESHOLD = 45.0
GHOST_MAX_MISSING_FRAMES = 3
GHOST_DROP_UNSUPPORTED_IMMEDIATELY = True
```
