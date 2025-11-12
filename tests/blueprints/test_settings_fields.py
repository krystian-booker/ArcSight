import io
import json
from pathlib import Path

import pytest

from app import apriltag_fields
from app.extensions import db
from app.models import Setting


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
def apriltag_field_dirs(tmp_path, monkeypatch):
    default_dir = tmp_path / "defaults"
    user_base = tmp_path / "user_data"
    fields_dir = user_base / apriltag_fields._USER_FIELDS_SUBDIR
    default_dir.mkdir()
    fields_dir.mkdir(parents=True)

    monkeypatch.setattr(apriltag_fields, "_DEFAULT_FIELDS_DIR", default_dir)
    monkeypatch.setattr(
        apriltag_fields, "user_data_dir", lambda *args, **kwargs: str(user_base)
    )

    # Ensure blueprint uses refreshed directory data in template context
    return default_dir, fields_dir


def test_select_field_updates_setting(app, client, apriltag_field_dirs):
    default_dir, _ = apriltag_field_dirs
    _write_layout(default_dir / "2024-crescendo.json")

    response = client.post(
        "/settings/apriltag/select",
        json={"field_name": "2024-crescendo.json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected"] == "2024-crescendo.json"

    with app.app_context():
        setting = db.session.get(Setting, "apriltag_field")
        assert setting is not None
        assert setting.value == "2024-crescendo.json"


def test_select_field_rejects_unknown(client, apriltag_field_dirs):
    response = client.post(
        "/settings/apriltag/select",
        json={"field_name": "nonexistent.json"},
    )
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_upload_field_persists_file(client, apriltag_field_dirs):
    _, user_dir = apriltag_field_dirs
    payload = {
        "tags": [
            {
                "ID": 1,
                "pose": {
                    "translation": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {
                        "quaternion": {"W": 1.0, "X": 0.0, "Y": 0.0, "Z": 0.0}
                    },
                },
            }
        ]
    }
    data = {
        "field_layout": (
            io.BytesIO(json.dumps(payload).encode("utf-8")),
            "custom-field.json",
        )
    }

    response = client.post(
        "/settings/apriltag/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["ok"] is True
    saved = user_dir / "custom-field.json"
    assert saved.exists()


def test_delete_field_removes_user_layout(app, client, apriltag_field_dirs):
    _, user_dir = apriltag_field_dirs
    file_path = user_dir / "custom.json"
    _write_layout(file_path)

    with app.app_context():
        db.session.query(Setting).filter_by(key="apriltag_field").delete()
        db.session.add(Setting(key="apriltag_field", value="custom.json"))
        db.session.commit()

    response = client.post(
        "/settings/apriltag/delete",
        json={"field_name": "custom.json"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload.get("selected") is None
    assert not file_path.exists()

    with app.app_context():
        assert db.session.get(Setting, "apriltag_field") is None
