from datetime import datetime, timedelta, timezone
from io import BytesIO
from app.security import Actor


def payload():
    return {"description": "Hay residuos acumulados frente al parque",
            "latitude": -12.065, "longitude": -75.21,
            "observed_at": "2026-10-26T14:00:00-05:00", "waste_type": "mixto"}


def test_health_and_profile(test_env):
    client, state, _ = test_env
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/me").json()["role"] == "ciudadano"


def test_report_visibility_and_permissions(test_env):
    client, state, _ = test_env
    response = client.post("/reports", json=payload())
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["status"] == "recibido"
    assert len(client.get("/reports/mine").json()) == 1
    state["actor"] = Actor(state["second"], "ciudadano")
    assert client.get("/reports/mine").json() == []
    assert client.get(f"/reports/{report['id']}").status_code == 404
    assert client.get("/municipal/reports").status_code == 403
    state["actor"] = Actor(state["driver"], "chofer")
    assert client.post("/reports", json=payload()).status_code == 403
    assert client.get(f"/reports/{report['id']}").status_code == 404
    state["actor"] = Actor(state["manager"], "encargado_municipal")
    assert client.get(f"/reports/{report['id']}").status_code == 200
    assert len(client.get("/municipal/reports?status=recibido").json()) == 1
    assert client.get("/municipal/reports?north=2").status_code == 422
    assert client.get("/municipal/reports?north=-12&south=-13&west=-76&east=-75").json()[0]["id"] == report["id"]
    assert client.get("/municipal/reports?north=3&south=2&west=-76&east=-75").json() == []


def test_invalid_report_date_and_coordinates(test_env):
    client, _, _ = test_env
    example = payload()
    example["latitude"] = -99
    assert client.post("/reports", json=example).status_code == 422
    example = payload()
    example["observed_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    assert client.post("/reports", json=example).status_code == 422
    example["observed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/reports", json=example).status_code == 422


def test_vehicle_and_shifts(test_env):
    client, state, _ = test_env
    state["actor"] = Actor(state["manager"], "encargado_municipal")
    vehicle = client.post("/municipal/vehicles", json={"label": "Unidad de prueba",
                          "vehicle_type": "compactadora", "available": False})
    assert vehicle.status_code == 201, vehicle.text
    vehicle_id = vehicle.json()["id"]
    assert client.post("/municipal/vehicles", json={"label": "Unidad de prueba",
                         "vehicle_type": "compactadora"}).status_code == 409
    start = client.post("/municipal/sites", json={"name": "Inicio de prueba", "site_type": "salida",
                        "latitude": -12.01, "longitude": -75.02})
    dump = client.post("/municipal/sites", json={"name": "Descarga de prueba", "site_type": "descarga",
                        "latitude": -12.02, "longitude": -75.03})
    assert start.status_code == 201 and dump.status_code == 201
    shift = {"vehicle_id": vehicle_id, "driver_id": str(state["driver"]),
             "departure_site_id": start.json()["id"], "disposal_site_id": dump.json()["id"],
             "starts_at": "2026-11-02T08:00:00-05:00", "ends_at": "2026-11-02T12:00:00-05:00"}
    assert client.post("/municipal/shifts", json=shift).status_code == 422
    assert client.patch(f"/municipal/vehicles/{vehicle_id}/availability",
                        json={"available": True}).status_code == 200
    assert client.post("/municipal/shifts", json=shift).status_code == 201
    assert client.post("/municipal/shifts", json=shift).status_code == 409
    state["actor"] = Actor(state["citizen"], "ciudadano")
    assert client.get("/municipal/vehicles").status_code == 403


def test_photo_mime_validation_before_storage(test_env):
    client, _, _ = test_env
    report_id = client.post("/reports", json=payload()).json()["id"]
    file = {"file": ("not-an-image.txt", BytesIO(b"just words"), "text/plain")}
    result = client.post(f"/reports/{report_id}/photos", files=file)
    assert result.status_code == 415


def test_no_auth_without_token(test_env):
    from app.main import app
    from app.security import get_current_actor
    client, state, _ = test_env
    app.dependency_overrides.pop(get_current_actor)
    assert client.get("/me").status_code == 401
