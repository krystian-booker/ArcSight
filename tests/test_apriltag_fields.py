import json
from pathlib import Path

import pytest

from app import apriltag_fields


def _write_layout(path: Path, tag_id: int = 1) -> None:
    payload = {
        "tags": [
            {
                "ID": tag_id,
                "pose": {
                    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {
                        "quaternion": {"W": 1.0, "X": 0.0, "Y": 0.0, "Z": 0.0}
                    },
                },
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def patched_field_dirs(tmp_path, monkeypatch):
    default_dir = tmp_path / "defaults"
    user_base = tmp_path / "user_data"
    user_fields_dir = user_base / apriltag_fields._USER_FIELDS_SUBDIR
    default_dir.mkdir()
    user_fields_dir.mkdir(parents=True)

    monkeypatch.setattr(apriltag_fields, "_DEFAULT_FIELDS_DIR", default_dir)
    monkeypatch.setattr(
        apriltag_fields, "user_data_dir", lambda *args, **kwargs: str(user_base)
    )

    return default_dir, user_fields_dir


def test_list_all_fields_merges_sources(patched_field_dirs):
    default_dir, user_dir = patched_field_dirs
    _write_layout(default_dir / "2024-crescendo.json")
    _write_layout(default_dir / "2025-reefscape.json")
    _write_layout(user_dir / "2025-reefscape.json", tag_id=2)
    _write_layout(user_dir / "2023-custom.json", tag_id=3)

    fields = apriltag_fields.list_all_fields()
    names = [info.name for info in fields]

    assert names == [
        "2025-reefscape.json",
        "2024-crescendo.json",
        "2023-custom.json",
    ]
    assert fields[0].source == "user"
    assert any(info.source == "default" for info in fields)


def test_load_field_layout_by_name_validates(patched_field_dirs):
    default_dir, user_dir = patched_field_dirs
    _write_layout(default_dir / "2024-crescendo.json")
    broken = {
        "tags": [
            {
                "ID": 9,
                "pose": {
                    "translation": {"x": 0.0, "y": 0.0},
                    "rotation": {},
                },
            }
        ]
    }
    (user_dir / "bad.json").write_text(json.dumps(broken), encoding="utf-8")

    good = apriltag_fields.load_field_layout_by_name("2024-crescendo.json")
    assert good is not None
    assert good["tags"][0]["ID"] == 1

    assert apriltag_fields.load_field_layout_by_name("bad.json") is None


def test_validate_layout_structure_missing_keys():
    layout = {
        "tags": [
            {
                "ID": 1,
                "pose": {
                    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"quaternion": {"W": 1.0, "X": 0.0, "Y": 0.0}},
                },
            }
        ]
    }
    is_valid, error = apriltag_fields.validate_layout_structure(layout)
    assert not is_valid
    assert "quaternion" in (error or "")
