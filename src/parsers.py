"""
TLV, point cloud, target, and presence parsers.
"""

import struct
import numpy as np

from constants import *
from settings import (
    HUMAN_ROI_X,
    HUMAN_ROI_Y,
    HUMAN_ROI_Z,
    HUMAN_MIN_POINTS,
)


# ============================================================
# POINT CLOUD / TARGET PARSERS
# ============================================================

def parse_oob_detected_points(payload, num_points):
    points = []

    point_size = 16
    max_points = len(payload) // point_size
    n = min(num_points, max_points)

    for i in range(n):
        offset = i * point_size

        try:
            x, y, z, doppler = struct.unpack_from("<ffff", payload, offset)
        except struct.error:
            break

        if np.isfinite([x, y, z, doppler]).all():
            points.append([x, y, z, doppler, 0.0])

    return np.array(points, dtype=np.float32)


def parse_compressed_point_cloud(payload):
    """
    People Tracking compressed point cloud.

    Header:
    float elevationUnit
    float azimuthUnit
    float dopplerUnit
    float rangeUnit
    float snrUnit

    Each point:
    int8 elevation
    int8 azimuth
    int16 doppler
    uint16 range
    uint16 snr
    """

    if len(payload) < 20:
        return np.empty((0, 5), dtype=np.float32)

    try:
        elevation_unit, azimuth_unit, doppler_unit, range_unit, snr_unit = struct.unpack_from(
            "<fffff",
            payload,
            0
        )
    except struct.error:
        return np.empty((0, 5), dtype=np.float32)

    units = np.array(
        [
            elevation_unit,
            azimuth_unit,
            doppler_unit,
            range_unit,
            snr_unit
        ],
        dtype=np.float32
    )

    if not np.isfinite(units).all():
        return np.empty((0, 5), dtype=np.float32)

    if abs(elevation_unit) > 1.0:
        return np.empty((0, 5), dtype=np.float32)

    if abs(azimuth_unit) > 1.0:
        return np.empty((0, 5), dtype=np.float32)

    if abs(range_unit) <= 0 or abs(range_unit) > 10:
        return np.empty((0, 5), dtype=np.float32)

    points = []
    point_size = 8
    offset = 20

    while offset + point_size <= len(payload):
        try:
            elev_i, azim_i, doppler_i, range_i, snr_i = struct.unpack_from(
                "<bbhHH",
                payload,
                offset
            )
        except struct.error:
            break

        elev = elev_i * elevation_unit
        azim = azim_i * azimuth_unit
        doppler = doppler_i * doppler_unit
        r = range_i * range_unit
        snr = snr_i * snr_unit

        x = r * np.cos(elev) * np.sin(azim)
        y = r * np.cos(elev) * np.cos(azim)
        z = r * np.sin(elev)

        if np.isfinite([x, y, z, doppler, snr]).all():
            points.append([x, y, z, doppler, snr])

        offset += point_size

    return np.array(points, dtype=np.float32)


def parse_float_point_cloud(payload):
    points = []

    # 20 bytes/point: range, azimuth, elevation, doppler, snr
    if len(payload) >= 20 and len(payload) % 20 == 0:
        point_size = 20
        num_points = len(payload) // point_size

        for i in range(num_points):
            offset = i * point_size

            try:
                r, azim, elev, doppler, snr = struct.unpack_from(
                    "<fffff",
                    payload,
                    offset
                )
            except struct.error:
                break

            x = r * np.cos(elev) * np.sin(azim)
            y = r * np.cos(elev) * np.cos(azim)
            z = r * np.sin(elev)

            if np.isfinite([x, y, z, doppler, snr]).all():
                points.append([x, y, z, doppler, snr])

        return np.array(points, dtype=np.float32)

    # 16 bytes/point: x, y, z, doppler
    if len(payload) >= 16 and len(payload) % 16 == 0:
        point_size = 16
        num_points = len(payload) // point_size

        for i in range(num_points):
            offset = i * point_size

            try:
                x, y, z, doppler = struct.unpack_from(
                    "<ffff",
                    payload,
                    offset
                )
            except struct.error:
                break

            if np.isfinite([x, y, z, doppler]).all():
                points.append([x, y, z, doppler, 0.0])

        return np.array(points, dtype=np.float32)

    return np.empty((0, 5), dtype=np.float32)


def parse_people_tracking_point_cloud(payload, tlv_type):
    if tlv_type == PT_TLV_COMPRESSED_POINT_CLOUD_EXT:
        return parse_compressed_point_cloud(payload)

    if len(payload) >= 28 and (len(payload) - 20) % 8 == 0:
        compressed_points = parse_compressed_point_cloud(payload)

        if len(compressed_points) > 0:
            return compressed_points

    return parse_float_point_cloud(payload)


def parse_target_list(payload):
    """
    Target list.

    Supported:
    - 40 bytes/target: tid + pos/vel/acc
    - 112 bytes/target: tid + pos/vel/acc + covariance/gain/confidence
    """

    targets = []

    if len(payload) < 40:
        return targets

    if len(payload) % 112 == 0:
        target_size = 112
    elif len(payload) % 40 == 0:
        target_size = 40
    else:
        target_size = 112 if len(payload) >= 112 else 40

    num_targets = len(payload) // target_size

    for i in range(num_targets):
        offset = i * target_size

        if offset + 40 > len(payload):
            break

        try:
            values = struct.unpack_from("<I9f", payload, offset)
        except struct.error:
            break

        target = {
            "tid": int(values[0]),
            "posX": float(values[1]),
            "posY": float(values[2]),
            "posZ": float(values[3]),
            "velX": float(values[4]),
            "velY": float(values[5]),
            "velZ": float(values[6]),
            "accX": float(values[7]),
            "accY": float(values[8]),
            "accZ": float(values[9]),
        }

        if np.isfinite([
            target["posX"],
            target["posY"],
            target["posZ"],
            target["velX"],
            target["velY"],
            target["velZ"]
        ]).all():
            targets.append(target)

    return targets


def parse_target_index(payload):
    if len(payload) == 0:
        return np.empty((0,), dtype=np.uint8)

    return np.frombuffer(payload, dtype=np.uint8).copy()


def parse_target_height(payload):
    heights = []
    item_size = 12

    if len(payload) < item_size:
        return heights

    num_items = len(payload) // item_size

    for i in range(num_items):
        offset = i * item_size

        try:
            tid, max_z, min_z = struct.unpack_from("<Iff", payload, offset)
        except struct.error:
            break

        if np.isfinite([max_z, min_z]).all():
            heights.append({
                "tid": int(tid),
                "maxZ": float(max_z),
                "minZ": float(min_z),
            })

    return heights


def parse_presence(payload):
    if len(payload) >= 4:
        try:
            return struct.unpack_from("<I", payload, 0)[0]
        except struct.error:
            return None

    if len(payload) >= 1:
        return int(payload[0])

    return None

# ============================================================
# SIMPLE POINT CLOUD HUMAN DETECTION
# ============================================================

def detect_human_from_pointcloud(points):
    if points is None or len(points) == 0:
        return False, 0

    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]

    mask = (
        (x >= HUMAN_ROI_X[0]) & (x <= HUMAN_ROI_X[1]) &
        (y >= HUMAN_ROI_Y[0]) & (y <= HUMAN_ROI_Y[1]) &
        (z >= HUMAN_ROI_Z[0]) & (z <= HUMAN_ROI_Z[1])
    )

    roi_points = points[mask]
    count = len(roi_points)

    return count >= HUMAN_MIN_POINTS, count

# ============================================================
# TLV EXTRACTION
# ============================================================

def extract_tlvs(packet_payload, num_tlvs):
    """
    Try both:
    - TLV length = payload length
    - TLV length = total length including 8-byte TLV header
    """

    candidates = []

    for length_mode in ["payload_length", "total_length"]:
        offset = 0
        tlvs = []
        valid = True
        known_count = 0

        for _ in range(num_tlvs):
            if offset + 8 > len(packet_payload):
                valid = False
                break

            try:
                tlv_type, tlv_length = struct.unpack_from("<II", packet_payload, offset)
            except struct.error:
                valid = False
                break

            if tlv_length <= 0:
                valid = False
                break

            if length_mode == "payload_length":
                payload_length = tlv_length
                next_offset = offset + 8 + payload_length
            else:
                if tlv_length < 8:
                    valid = False
                    break

                payload_length = tlv_length - 8
                next_offset = offset + tlv_length

            if payload_length < 0:
                valid = False
                break

            if next_offset > len(packet_payload):
                valid = False
                break

            payload_start = offset + 8
            payload_end = payload_start + payload_length
            tlv_payload = packet_payload[payload_start:payload_end]

            tlv_type_int = int(tlv_type)

            tlvs.append({
                "type": tlv_type_int,
                "length": int(tlv_length),
                "payload_length": int(payload_length),
                "payload": tlv_payload,
                "length_mode": length_mode,
            })

            if tlv_type_int in KNOWN_PEOPLE_TLVS or tlv_type_int in KNOWN_OOB_TLVS:
                known_count += 1

            offset = next_offset

        if valid and tlvs:
            leftover = len(packet_payload) - offset

            candidates.append({
                "mode": length_mode,
                "tlvs": tlvs,
                "known_count": known_count,
                "leftover": abs(leftover),
                "score": known_count * 10000 - abs(leftover),
            })

    if not candidates:
        return [], "invalid"

    candidates.sort(key=lambda c: c["score"], reverse=True)

    return candidates[0]["tlvs"], candidates[0]["mode"]
