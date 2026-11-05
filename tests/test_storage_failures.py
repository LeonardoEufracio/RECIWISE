import inspect
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app import storage


@pytest.fixture
def transport(monkeypatch):
    config = SimpleNamespace(supabase_url="https://storage.invalid", supabase_service_role_key="sb_secret_fictitious",
                             storage_bucket="test-bucket")
    monkeypatch.setattr(storage, "get_settings", lambda: config)
    requests = []
    handler = {"response": lambda req: httpx.Response(200, json={"signedURL": "/signed/test"})}
    original = httpx.Client

    def receive(request):
        requests.append(request)
        return handler["response"](request)

    monkeypatch.setattr(storage.httpx, "Client", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(receive)))
    return config, requests, handler


@pytest.mark.parametrize("status,uncertain,collision", [(400, False, False), (403, False, False),
    (408, True, False), (409, False, True), (500, True, False), (503, True, False)])
def test_upload_classifies_storage_errors_without_exposing_response(transport, status, uncertain, collision):
    _, requests, handler = transport
    handler["response"] = lambda req: httpx.Response(status, json={"message": "fictitious private server response"})
    with pytest.raises(storage.StorageUploadError) as exc:
        storage.put_private_image("owned/photo.jpg", b"test", "image/jpeg")
    assert exc.value.status_code == 502
    assert exc.value.uncertain is uncertain and exc.value.collision is collision
    assert "private server response" not in exc.value.detail
    assert requests[0].headers["x-upsert"] == "false"


def test_supabase_duplicate_encoded_as_400_is_not_cleaned(transport):
    _, _, handler = transport
    handler["response"] = lambda req: httpx.Response(400, json={"error": "Duplicate", "statusCode": "409"})
    with pytest.raises(storage.StorageUploadError) as exc:
        storage.put_private_image("owned/photo.jpg", b"test", "image/jpeg")
    assert exc.value.collision is True


def test_upload_timeout_is_ambiguous(transport):
    _, _, handler = transport
    def timeout(request):
        raise httpx.ReadTimeout("fictitious timeout", request=request)
    handler["response"] = timeout
    with pytest.raises(storage.StorageUploadError) as exc:
        storage.put_private_image("owned/photo.jpg", b"test", "image/jpeg")
    assert exc.value.uncertain is True


def test_missing_storage_configuration_is_503_and_never_calls_network(transport):
    config, requests, _ = transport
    config.supabase_service_role_key = ""
    with pytest.raises(storage.StorageUploadError) as exc:
        storage.put_private_image("owned/photo.jpg", b"test", "image/jpeg")
    assert exc.value.status_code == 503 and exc.value.uncertain is False
    assert requests == []


@pytest.mark.parametrize("key", ["sb_secret_fictitious", "fictitious-legacy-service-key"])
def test_compensation_uses_one_exact_path_and_private_headers(transport, key):
    config, requests, handler = transport
    config.supabase_service_role_key = key
    handler["response"] = lambda req: httpx.Response(200, json=[])
    storage.remove_private_image("reports/test/test/owned.jpg")
    request = requests[0]
    assert request.method == "DELETE" and request.url.path == "/storage/v1/object/test-bucket"
    assert json.loads(request.content) == {"prefixes": ["reports/test/test/owned.jpg"]}
    assert request.headers["apikey"] == key
    assert ("authorization" in request.headers) is (not key.startswith("sb_secret_"))


@pytest.mark.parametrize("status", [403, 404, 500])
def test_failed_delete_is_not_treated_as_success(transport, status):
    _, _, handler = transport
    handler["response"] = lambda req: httpx.Response(status, json={})
    with pytest.raises(HTTPException) as exc:
        storage.remove_private_image("owned/photo.jpg")
    assert exc.value.status_code == 502


@pytest.mark.parametrize("body", [b'{"error":"failed"}', b'null', b'not-json'])
def test_invalid_delete_acknowledgement_is_not_success(transport, body):
    _, _, handler = transport
    handler["response"] = lambda req: httpx.Response(200, content=body)
    with pytest.raises(HTTPException) as exc:
        storage.remove_private_image("owned/photo.jpg")
    assert exc.value.status_code == 502


def test_signed_url_and_sync_worker_contract(transport):
    _, requests, _ = transport
    assert storage.signed_image_url("owned/photo.jpg") == "https://storage.invalid/storage/v1/signed/test"
    assert json.loads(requests[0].content) == {"expiresIn": 300}
    assert all(not inspect.iscoroutinefunction(fn) for fn in (
        storage.put_private_image, storage.remove_private_image, storage.signed_image_url))
