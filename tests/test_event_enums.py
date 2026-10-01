from models.event import CameraId, Direction, EventMethod


def test_enum_values_match_shared_contract():
    assert {d.value for d in Direction} == {"ENTRY", "EXIT"}
    assert {m.value for m in EventMethod} == {"FACE", "BODY_ONLY"}
    assert {c.value for c in CameraId} == {"camera-outside", "camera-inside"}
