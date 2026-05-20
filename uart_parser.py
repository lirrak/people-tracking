"""
Non-blocking UART packet parser for IWR6843AOP radar frames.
"""

import struct
import numpy as np

from constants import *
from settings import ENABLE_SIMPLE_POINTCLOUD_HUMAN_DETECT, HUMAN_ROI_X, HUMAN_ROI_Y, HUMAN_ROI_Z
from parsers import (
    extract_tlvs,
    parse_people_tracking_point_cloud,
    parse_target_list,
    parse_target_index,
    parse_target_height,
    parse_presence,
    parse_oob_detected_points,
    detect_human_from_pointcloud,
)


# ============================================================
# NON-BLOCKING AUTO UART PARSER
# ============================================================

class AutoRadarUARTParser:
    def __init__(self):
        self.buffer = bytearray()
        self.total_frames = 0
        self.bad_packets = 0
        self.last_tlv_types = []
        self.last_tlv_length_mode = "unknown"
        self.last_header_mode = "unknown"
        self.last_mode = "WAITING"
        self.total_bytes_received = 0
        self.first_bytes_hex = ""

    def append_data(self, data):
        if data:
            self.total_bytes_received += len(data)

            if not self.first_bytes_hex:
                self.first_bytes_hex = data[:64].hex(" ")

            self.buffer.extend(data)

        if len(self.buffer) > 2 * MAX_PACKET_LENGTH:
            magic_index = self.buffer.rfind(MAGIC_WORD)

            if magic_index >= 0:
                self.buffer = self.buffer[magic_index:]
            else:
                self.buffer.clear()

    def parse_available_frames(self):
        frames = []

        while True:
            frame = self._try_parse_one_frame()

            if frame is None:
                break

            frames.append(frame)

        return frames

    def _try_parse_one_frame(self):
        magic_index = self.buffer.find(MAGIC_WORD)

        if magic_index < 0:
            if len(self.buffer) > len(MAGIC_WORD):
                self.buffer = self.buffer[-len(MAGIC_WORD):]
            return None

        if magic_index > 0:
            del self.buffer[:magic_index]

        if len(self.buffer) < 40:
            return None

        candidates = []

        candidate_40 = self._try_candidate_header_40()
        if candidate_40 is not None:
            candidates.append(candidate_40)

        candidate_52 = self._try_candidate_header_52()
        if candidate_52 is not None:
            candidates.append(candidate_52)

        if not candidates:
            if self._looks_like_incomplete_packet():
                return None

            del self.buffer[0:1]
            self.bad_packets += 1
            return None

        candidates.sort(key=lambda c: c["score"], reverse=True)
        best = candidates[0]

        packet_length = best["packet_length"]
        del self.buffer[:packet_length]

        self.last_tlv_types = best["tlv_types"]
        self.last_tlv_length_mode = best["tlv_length_mode"]
        self.last_header_mode = best["header_mode"]
        self.last_mode = best["mode"]

        self.total_frames += 1

        return best["frame"]

    def _looks_like_incomplete_packet(self):
        if len(self.buffer) >= 40:
            try:
                values = struct.unpack("<8I", self.buffer[8:40])
                packet_len_40 = values[1]
                num_tlvs_40 = values[6]

                if 40 <= packet_len_40 <= MAX_PACKET_LENGTH and 0 < num_tlvs_40 <= 64:
                    if len(self.buffer) < packet_len_40:
                        return True
            except Exception:
                pass

        if len(self.buffer) >= 52:
            try:
                values = struct.unpack("<10I2H", self.buffer[8:52])
                packet_len_52 = values[3]
                num_tlvs_52 = values[10]

                if 52 <= packet_len_52 <= MAX_PACKET_LENGTH and 0 < num_tlvs_52 <= 64:
                    if len(self.buffer) < packet_len_52:
                        return True
            except Exception:
                pass

        return False

    def _try_candidate_header_40(self):
        if len(self.buffer) < 40:
            return None

        try:
            values = struct.unpack("<8I", self.buffer[8:40])
        except struct.error:
            return None

        header = {
            "version": values[0],
            "totalPacketLen": values[1],
            "platform": values[2],
            "frameNumber": values[3],
            "timeCpuCycles": values[4],
            "numDetectedObj": values[5],
            "numTLVs": values[6],
            "subFrameNumber": values[7],
            "headerSize": 40,
        }

        packet_length = header["totalPacketLen"]
        num_tlvs = header["numTLVs"]

        if packet_length < 40 or packet_length > MAX_PACKET_LENGTH:
            return None

        if num_tlvs <= 0 or num_tlvs > 64:
            return None

        if len(self.buffer) < packet_length:
            return None

        packet = bytes(self.buffer[:packet_length])
        packet_payload = packet[40:]

        tlvs, tlv_length_mode = extract_tlvs(packet_payload, num_tlvs)

        if not tlvs:
            return None

        tlv_types = [tlv["type"] for tlv in tlvs]

        people_count = sum(1 for t in tlv_types if t in KNOWN_PEOPLE_TLVS)
        oob_count = sum(1 for t in tlv_types if t in KNOWN_OOB_TLVS)

        if people_count == 0 and oob_count == 0:
            return None

        if people_count >= oob_count:
            frame = self._parse_people_tracking_tlvs(header, tlvs)
            frame["mode"] = "PEOPLE_TRACKING"
            header_mode = "SDK_40_WITH_PEOPLE_TLV"
            mode = "PEOPLE_TRACKING"
            score = people_count * 10000 + 400
        else:
            frame = self._parse_oob_tlvs(header, tlvs)
            frame["mode"] = "OUT_OF_BOX"
            header_mode = "SDK_40_OOB"
            mode = "OUT_OF_BOX"
            score = oob_count * 10000 + 100

        return {
            "frame": frame,
            "packet_length": packet_length,
            "tlv_types": tlv_types,
            "tlv_length_mode": tlv_length_mode,
            "header_mode": header_mode,
            "mode": mode,
            "score": score,
        }

    def _try_candidate_header_52(self):
        if len(self.buffer) < 52:
            return None

        try:
            values = struct.unpack("<10I2H", self.buffer[8:52])
        except struct.error:
            return None

        header = {
            "version": values[0],
            "platform": values[1],
            "timestamp": values[2],
            "packetLength": values[3],
            "frameNumber": values[4],
            "subframeNumber": values[5],
            "chirpMargin": values[6],
            "frameMargin": values[7],
            "uartSentTime": values[8],
            "trackProcessTime": values[9],
            "numTLVs": values[10],
            "checksum": values[11],
            "headerSize": 52,
        }

        packet_length = header["packetLength"]
        num_tlvs = header["numTLVs"]

        if packet_length < 52 or packet_length > MAX_PACKET_LENGTH:
            return None

        if num_tlvs <= 0 or num_tlvs > 64:
            return None

        if len(self.buffer) < packet_length:
            return None

        packet = bytes(self.buffer[:packet_length])
        packet_payload = packet[52:]

        tlvs, tlv_length_mode = extract_tlvs(packet_payload, num_tlvs)

        if not tlvs:
            return None

        tlv_types = [tlv["type"] for tlv in tlvs]
        people_count = sum(1 for t in tlv_types if t in KNOWN_PEOPLE_TLVS)

        if people_count == 0:
            return None

        frame = self._parse_people_tracking_tlvs(header, tlvs)
        frame["mode"] = "PEOPLE_TRACKING"

        return {
            "frame": frame,
            "packet_length": packet_length,
            "tlv_types": tlv_types,
            "tlv_length_mode": tlv_length_mode,
            "header_mode": "PEOPLE_52",
            "mode": "PEOPLE_TRACKING",
            "score": people_count * 10000 + 200,
        }

    def _parse_people_tracking_tlvs(self, header, tlvs):
        point_cloud = np.empty((0, 5), dtype=np.float32)
        targets = []
        target_index = np.empty((0,), dtype=np.uint8)
        target_heights = []
        presence = None
        unknown_tlvs = []

        for tlv in tlvs:
            tlv_type = tlv["type"]
            tlv_payload = tlv["payload"]

            if tlv_type in PEOPLE_TRACKING_POINT_CLOUD_TLVS:
                point_cloud = parse_people_tracking_point_cloud(tlv_payload, tlv_type)

            elif tlv_type in PEOPLE_TRACKING_TARGET_LIST_TLVS:
                targets = parse_target_list(tlv_payload)

            elif tlv_type in PEOPLE_TRACKING_TARGET_INDEX_TLVS:
                target_index = parse_target_index(tlv_payload)

            elif tlv_type in PEOPLE_TRACKING_TARGET_HEIGHT_TLVS:
                target_heights = parse_target_height(tlv_payload)

            elif tlv_type in PEOPLE_TRACKING_PRESENCE_TLVS:
                presence = parse_presence(tlv_payload)

            else:
                unknown_tlvs.append({
                    "type": int(tlv_type),
                    "length": int(tlv["length"]),
                    "payload_length": int(tlv["payload_length"]),
                })

        return {
            "header": header,
            "point_cloud": point_cloud,
            "targets": targets,
            "target_index": target_index,
            "target_heights": target_heights,
            "presence": presence,
            "unknown_tlvs": unknown_tlvs,
        }

    def _parse_oob_tlvs(self, header, tlvs):
        num_detected_obj = header.get("numDetectedObj", 0)

        point_cloud = np.empty((0, 5), dtype=np.float32)
        targets = []
        target_index = np.empty((0,), dtype=np.uint8)
        target_heights = []
        presence = None
        unknown_tlvs = []

        for tlv in tlvs:
            tlv_type = tlv["type"]
            tlv_payload = tlv["payload"]

            if tlv_type == OOB_TLV_DETECTED_POINTS:
                point_cloud = parse_oob_detected_points(tlv_payload, num_detected_obj)

            elif tlv_type in KNOWN_OOB_TLVS:
                pass

            else:
                unknown_tlvs.append({
                    "type": int(tlv_type),
                    "length": int(tlv["length"]),
                    "payload_length": int(tlv["payload_length"]),
                })

        if ENABLE_SIMPLE_POINTCLOUD_HUMAN_DETECT and len(point_cloud) > 0:
            human_detected, roi_count = detect_human_from_pointcloud(point_cloud)

            if human_detected:
                presence = 1

                roi_mask = (
                    (point_cloud[:, 0] >= HUMAN_ROI_X[0]) &
                    (point_cloud[:, 0] <= HUMAN_ROI_X[1]) &
                    (point_cloud[:, 1] >= HUMAN_ROI_Y[0]) &
                    (point_cloud[:, 1] <= HUMAN_ROI_Y[1]) &
                    (point_cloud[:, 2] >= HUMAN_ROI_Z[0]) &
                    (point_cloud[:, 2] <= HUMAN_ROI_Z[1])
                )

                roi_points = point_cloud[roi_mask]

                if len(roi_points) > 0:
                    center = np.mean(roi_points[:, 0:3], axis=0)

                    targets = [{
                        "tid": 1,
                        "posX": float(center[0]),
                        "posY": float(center[1]),
                        "posZ": float(center[2]),
                        "velX": 0.0,
                        "velY": 0.0,
                        "velZ": 0.0,
                        "accX": 0.0,
                        "accY": 0.0,
                        "accZ": 0.0,
                        "isVirtual": True,
                        "roiPointCount": roi_count,
                    }]
            else:
                presence = 0

        return {
            "header": {
                "frameNumber": header.get("frameNumber", 0),
                "numTLVs": header.get("numTLVs", 0),
                "numDetectedObj": header.get("numDetectedObj", 0),
                "headerSize": header.get("headerSize", 40),
            },
            "point_cloud": point_cloud,
            "targets": targets,
            "target_index": target_index,
            "target_heights": target_heights,
            "presence": presence,
            "unknown_tlvs": unknown_tlvs,
        }
