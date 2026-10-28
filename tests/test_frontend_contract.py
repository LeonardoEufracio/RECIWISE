"""Verifica la integración requerida por el frontend sin tocar Supabase real."""
from io import BytesIO
from datetime import datetime, timezone
from base64 import b64decode

from app import main
from app.security import Actor


def test_vite_cors_preflight_and_actual_response(test_env):
    client, _, _ = test_env
    origin = "http://localhost:5173"
    for method, path in [("GET", "/me"), ("POST", "/reports"),
                         ("POST", "/reports/00000000-0000-0000-0000-000000000000/photos")]:
        result = client.options(path, headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        })
        assert result.status_code == 200, result.text
        assert result.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in result.headers
    result = client.get("/me", headers={"Origin": origin})
    assert result.status_code == 200
    assert result.headers["access-control-allow-origin"] == origin
    denied = client.options("/reports", headers={
        "Origin": "https://untrusted.invalid",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_photo_upload_listing_limits_and_roles(test_env, monkeypatch):
    client, state, _ = test_env
    stored = []

    async def store(path, contents, content_type):
        stored.append((path, contents, content_type))

    async def sign(path):
        return f"https://storage.test/{path}?temporary=1"

    monkeypatch.setattr(main, "put_private_image", store)
    monkeypatch.setattr(main, "signed_image_url", sign)
    result = client.post("/reports", json={
        "description": "Reporte sintético para comprobar fotografías",
        "latitude": -12.05, "longitude": -75.2,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    })
    assert result.status_code == 201
    report = result.json()
    assert report["citizen_id"] == str(state["citizen"])
    assert report["waste_type"] is None
    path = f"/reports/{report['id']}/photos"
    png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")

    def image():
        return {"file": ("test.png", BytesIO(png), "image/png")}

    for _ in range(3):
        photo = client.post(path, files=image())
        assert photo.status_code == 201, photo.text
        assert photo.json()["signed_url"] is None
        assert photo.json()["content_type"] == "image/png"
    assert len(stored) == 3
    assert stored[0][1] == png
    assert client.post(path, files=image()).status_code == 409
    photos = client.get(path)
    assert photos.status_code == 200
    assert len(photos.json()) == 3
    assert all(photo["signed_url"].startswith("https://storage.test/") for photo in photos.json())
    state["actor"] = Actor(state["second"], "ciudadano")
    assert client.get(path).status_code == 404
    assert client.post(path, files=image()).status_code == 404
    state["actor"] = Actor(state["manager"], "encargado_municipal")
    assert client.get(path).status_code == 200
    assert client.post(path, files=image()).status_code == 403
