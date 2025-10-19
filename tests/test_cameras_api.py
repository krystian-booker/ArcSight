import json

from app.extensions import db
from app.models import Camera


def test_list_cameras_returns_serialized(client):
    """GET /api/cameras returns existing cameras as dictionaries."""
    db.session.query(Camera).delete()
    db.session.commit()

    cam1 = Camera(name="Front Door", identifier="cam_front", camera_type="USB")
    cam2 = Camera(name="Warehouse", identifier="cam_wh", camera_type="GenICam")
    db.session.add_all([cam1, cam2])
    db.session.commit()

    response = client.get("/api/cameras")
    assert response.status_code == 200

    payload = json.loads(response.data)
    assert isinstance(payload, list)
    assert [item["id"] for item in payload] == [cam1.id, cam2.id]
    assert payload[0]["name"] == cam1.name
    assert payload[1]["camera_type"] == cam2.camera_type


def test_list_cameras_empty_when_none_exist(client):
    """GET /api/cameras yields an empty list when no cameras are configured."""
    db.session.query(Camera).delete()
    db.session.commit()

    response = client.get("/api/cameras")
    assert response.status_code == 200
    assert json.loads(response.data) == []
