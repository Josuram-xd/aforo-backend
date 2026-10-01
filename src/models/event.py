"""Shared aforo event contract (see ARCHITECTURE.md section 4).

Any change here must also be applied in aforo-vision (producer) and aforo-frontend (consumer).
"""

from enum import StrEnum


class Direction(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class EventMethod(StrEnum):
    FACE = "FACE"
    BODY_ONLY = "BODY_ONLY"


class CameraId(StrEnum):
    OUTSIDE = "camera-outside"
    INSIDE = "camera-inside"
