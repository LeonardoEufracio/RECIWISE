"""JWT y permisos reales con claves efímeras, JWKS local y SQLite.

No se sustituye get_current_actor ni jwt.decode. Solo se reemplazan la BD
externa, la configuración del emisor y el transporte HTTP del JWKS.
"""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import socket
from types import SimpleNamespace
import urllib.request
import uuid

from cryptography.hazmat.primitives.asymmetric import ec, rsa
import jwt
import pytest
from sqlalchemy.orm import Session

from app import security
from app.main import app
from app.models import Report, ServiceSite, Vehicle


PROJECT_URL = "https://reciwise-auth.test"
ISSUER = PROJECT_URL + "/auth/v1"
JWKS_URL = ISSUER + "/.well-known/jwks.json"
ALGORITHMS = ("ES256", "RS256")
HMAC_TEST_SECRET = b"reciwise-unit-tests-only-hmac-secret-32-bytes"

MUNICIPAL_OPERATIONS = [
    pytest.param("GET", "/municipal/reports", 200, id="reports_get"),
    pytest.param("GET", "/municipal/vehicles", 200, id="vehicles_get"),
    pytest.param("POST", "/municipal/vehicles", 201, id="vehicles_post"),
    pytest.param("PATCH", "/municipal/vehicles/{vehicle_id}/availability", 200, id="availability_patch"),
    pytest.param("GET", "/municipal/sites", 200, id="sites_get"),
    pytest.param("POST", "/municipal/sites", 201, id="sites_post"),
    pytest.param("GET", "/municipal/shifts", 200, id="shifts_get"),
    pytest.param("POST", "/municipal/shifts", 201, id="shifts_post"),
]


@pytest.fixture(scope="session")
def jwt_keys():
    """Material ficticio generado para esta ejecución; no se guarda en disco."""
    keys = {
        "ES256": ec.generate_private_key(ec.SECP256R1()),
        "RS256": rsa.generate_private_key(public_exponent=65537, key_size=2048),
    }
    wrong_keys = {
        "ES256": ec.generate_private_key(ec.SECP256R1()),
        "RS256": rsa.generate_private_key(public_exponent=65537, key_size=2048),
    }
    public_jwks = []
    for algorithm, converter in (("ES256", jwt.algorithms.ECAlgorithm),
                                 ("RS256", jwt.algorithms.RSAAlgorithm)):
        jwk = converter.to_jwk(keys[algorithm].public_key(), as_dict=True)
        jwk.update({"kid": "test-" + algorithm, "alg": algorithm, "use": "sig"})
        public_jwks.append(jwk)
    return keys, wrong_keys, {"keys": public_jwks}


@pytest.fixture
def jwt_env(test_env, jwt_keys, monkeypatch):
    client, state, engine = test_env
    keys, wrong_keys, jwks = jwt_keys
    # La fixture general sustituye el actor: retirarlo para probar la cadena
    # completa de Bearer -> JWKS -> firma/claims -> perfil/rol -> endpoint.
    app.dependency_overrides.pop(security.get_current_actor)
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(supabase_url=PROJECT_URL))
    security.jwks_client.cache_clear()
    fetched_urls = []

    def local_jwks(request, *args, **kwargs):
        url = request.full_url if isinstance(request, urllib.request.Request) else request
        assert url == JWKS_URL, "Las pruebas solo admiten el JWKS ficticio"
        fetched_urls.append(url)
        return BytesIO(json.dumps(jwks).encode("utf-8"))

    # PyJWT 2.9+ utiliza urlopen o un opener según la versión instalada.
    # Ambos transportes devuelven el mismo JSON local; el cliente JWKS real
    # sigue seleccionando kid, interpretando las claves y usando su caché.
    monkeypatch.setattr(urllib.request, "urlopen", local_jwks)
    monkeypatch.setattr(urllib.request, "build_opener",
                        lambda *args, **kwargs: SimpleNamespace(open=local_jwks))

    def forbid_network(*args, **kwargs):
        pytest.fail("Estas pruebas JWT no deben abrir conexiones de red")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)

    ids = {name: uuid.uuid4() for name in ("vehicle_id", "departure_id", "disposal_id", "report_id")}
    with Session(engine) as db:
        db.add(Vehicle(id=ids["vehicle_id"], label="Vehículo sintético de permisos",
                       vehicle_type="compactadora", available=True))
        db.add(ServiceSite(id=ids["departure_id"], name="Salida sintética",
                           site_type="salida", latitude=-12, longitude=-75, active=True))
        db.add(ServiceSite(id=ids["disposal_id"], name="Descarga sintética",
                           site_type="descarga", latitude=-12.01, longitude=-75.01, active=True))
        db.add(Report(id=ids["report_id"], citizen_id=state["citizen"],
                      description="Reporte sintético para verificar permisos",
                      latitude=-12, longitude=-75, observed_at=datetime.now(timezone.utc)))
        db.commit()

    def make_token(subject=None, algorithm="ES256", claims=None, omit=(), wrong_signature=False, kid=None):
        payload = {
            "sub": str(subject if subject is not None else state["citizen"]),
            "iss": ISSUER, "aud": "authenticated",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        payload.update(claims or {})
        for name in omit:
            payload.pop(name, None)
        if algorithm == "HS256":
            key = HMAC_TEST_SECRET
        else:
            key = (wrong_keys if wrong_signature else keys)[algorithm]
        # Un HS256 usa un kid publicado válido: no debe rechazarse solo
        # por falta de clave, sino por la lista de algoritmos admitidos.
        return jwt.encode(payload, key, algorithm=algorithm,
                          headers={"kid": kid if kid is not None else "test-" + ("ES256" if algorithm == "HS256" else algorithm)})

    def request(method, path, token):
        path = path.format(vehicle_id=ids["vehicle_id"])
        body = None
        if method == "POST" and path == "/municipal/vehicles":
            body = {"label": "Nueva unidad sintética", "vehicle_type": "otro", "available": False}
        elif method == "PATCH":
            body = {"available": False}
        elif method == "POST" and path == "/municipal/sites":
            body = {"name": "Sitio sintético nuevo", "site_type": "ambos", "latitude": -12, "longitude": -75}
        elif method == "POST" and path == "/municipal/shifts":
            body = {
                "vehicle_id": str(ids["vehicle_id"]), "driver_id": str(state["driver"]),
                "departure_site_id": str(ids["departure_id"]), "disposal_site_id": str(ids["disposal_id"]),
                "starts_at": "2026-11-02T08:00:00-05:00", "ends_at": "2026-11-02T12:00:00-05:00",
            }
        return client.request(method, path, json=body,
                              headers={"Authorization": "Bearer " + token})

    try:
        yield SimpleNamespace(client=client, state=state, ids=ids, token=make_token,
                              request=request, fetched_urls=fetched_urls)
    finally:
        security.jwks_client.cache_clear()


def assert_auth_error(response, status, message):
    assert response.status_code == status, response.text
    assert response.json() == {"detail": message}


def test_request_without_jwt_returns_401(jwt_env):
    response = jwt_env.client.get("/me")
    assert_auth_error(response, 401, "Se requiere un token de acceso")
    assert jwt_env.fetched_urls == []


@pytest.mark.parametrize("authorization", ["Basic prueba", "Bearer", "Bearer "])
def test_invalid_authorization_header_returns_401(jwt_env, authorization):
    response = jwt_env.client.get("/me", headers={"Authorization": authorization})
    assert_auth_error(response, 401, "Se requiere un token de acceso")
    assert jwt_env.fetched_urls == []


@pytest.mark.parametrize("token", ["no-es-un-jwt", "a.b.c", "eyJhbGciOiJFUzI1NiJ9.payload-invalido.firma"])
def test_malformed_jwt_returns_401(jwt_env, token):
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 401, "Token inválido o vencido")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("case", ["expired", "wrong_signature", "wrong_issuer", "wrong_audience"])
def test_invalid_signature_or_claims_returns_401(jwt_env, algorithm, case):
    claims = {}
    if case == "expired":
        claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    elif case == "wrong_issuer":
        claims["iss"] = "https://otro-emisor.test/auth/v1"
    elif case == "wrong_audience":
        claims["aud"] = "otra-audiencia"
    token = jwt_env.token(algorithm=algorithm, claims=claims, wrong_signature=case == "wrong_signature")
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 401, "Token inválido o vencido")
    assert jwt_env.fetched_urls == [JWKS_URL]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("claim", ["sub", "exp", "iss", "aud"])
def test_required_claim_missing_returns_401(jwt_env, algorithm, claim):
    token = jwt_env.token(algorithm=algorithm, omit=(claim,))
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 401, "Token inválido o vencido")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_subject_not_uuid_returns_401(jwt_env, algorithm):
    token = jwt_env.token(algorithm=algorithm, claims={"sub": "no-es-un-uuid"})
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 401, "Token inválido o vencido")


def test_hs256_returns_401_with_published_kid(jwt_env):
    token = jwt_env.token(algorithm="HS256")
    assert jwt.get_unverified_header(token) == {"alg": "HS256", "kid": "test-ES256", "typ": "JWT"}
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 401, "Token inválido o vencido")
    assert jwt_env.fetched_urls == [JWKS_URL]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_unknown_kid_returns_401(jwt_env, algorithm):
    token = jwt_env.token(algorithm=algorithm, kid="clave-no-publicada")
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 401, "Token inválido o vencido")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("role,expected", [("citizen", "ciudadano"), ("manager", "encargado_municipal"), ("driver", "chofer")])
def test_valid_asymmetric_jwt_reads_role_from_profile(jwt_env, algorithm, role, expected):
    token = jwt_env.token(subject=jwt_env.state[role], algorithm=algorithm)
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(jwt_env.state[role]), "role": expected}
    assert jwt_env.fetched_urls == [JWKS_URL]


@pytest.mark.parametrize("role", ["citizen", "driver"])
@pytest.mark.parametrize("method,path,success_status", MUNICIPAL_OPERATIONS)
def test_non_municipal_roles_are_forbidden(jwt_env, role, method, path, success_status):
    token = jwt_env.token(subject=jwt_env.state[role])
    response = jwt_env.request(method, path, token)
    assert_auth_error(response, 403, "No tienes permiso para esta operación")


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("method,path,success_status", MUNICIPAL_OPERATIONS)
def test_manager_can_access_all_municipal_operations(jwt_env, algorithm, method, path, success_status):
    token = jwt_env.token(subject=jwt_env.state["manager"], algorithm=algorithm)
    response = jwt_env.request(method, path, token)
    assert response.status_code == success_status, response.text
    if method == "GET":
        assert isinstance(response.json(), list)
        if path == "/municipal/reports":
            assert response.json()[0]["id"] == str(jwt_env.ids["report_id"])
    elif path == "/municipal/shifts":
        assert response.json()["created_by"] == str(jwt_env.state["manager"])
    else:
        assert "id" in response.json()


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_authenticated_user_without_profile_returns_403(jwt_env, algorithm):
    token = jwt_env.token(subject=uuid.uuid4(), algorithm=algorithm)
    response = jwt_env.client.get("/me", headers={"Authorization": "Bearer " + token})
    assert_auth_error(response, 403, "Usuario sin perfil habilitado")


def test_jwt_metadata_cannot_promote_citizen(jwt_env):
    token = jwt_env.token(claims={"role": "encargado_municipal",
                                 "user_metadata": {"role": "encargado_municipal"}})
    headers = {"Authorization": "Bearer " + token}
    profile = jwt_env.client.get("/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["role"] == "ciudadano"
    response = jwt_env.client.get("/municipal/reports", headers=headers)
    assert_auth_error(response, 403, "No tienes permiso para esta operación")
