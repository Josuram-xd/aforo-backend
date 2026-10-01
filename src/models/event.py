"""Shared aforo event contract (see ARCHITECTURE.md section 4).

Any change here must also be applied in aforo-vision (producer) and aforo-frontend (consumer).
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Direction(StrEnum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


class EventMethod(StrEnum):
    FACE = "FACE"
    BODY_ONLY = "BODY_ONLY"


class CameraId(StrEnum):
    OUTSIDE = "camera-outside"
    INSIDE = "camera-inside"


class AforoEvent(BaseModel):
    """Resolved door-crossing event sent by aforo-vision to POST /events.

    JSON uses camelCase (eventId, personId, ...); Python attributes use snake_case.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
        frozen=True,
    )

    event_id: UUID
    person_id: UUID | None = None
    person_name: str | None = None
    direction: Direction
    camera_outside_id: Literal[CameraId.OUTSIDE]
    camera_inside_id: Literal[CameraId.INSIDE]
    confidence: float = Field(ge=0, le=1)
    method: EventMethod
    timestamp: AwareDatetime
