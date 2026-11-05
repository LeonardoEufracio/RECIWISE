from urllib.parse import quote
import httpx
from fastapi import HTTPException
from .config import get_settings



def storage_info() -> tuple[str, dict[str, str]]:
    s = get_settings()
    key = s.supabase_service_role_key.strip()

    if not key:
        raise HTTPException(
            status_code=503,
            detail="Almacenamiento de imágenes no configurado"
        )

    base = s.supabase_url.rstrip("/") + "/storage/v1/object"

    headers = {"apikey": key}

    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"

    return base, headers



class StorageUploadError(HTTPException):
    def __init__(self, status_code=502, *, uncertain=False, collision=False):
        super().__init__(status_code=status_code, detail=(
            "Almacenamiento de imágenes no configurado" if status_code == 503 else "No se pudo guardar la imagen"))
        self.uncertain = uncertain
        self.collision = collision


def put_private_image(path: str, contents: bytes, content_type: str) -> None:
    try:
        base, headers = storage_info()
    except HTTPException as exc:
        raise StorageUploadError(exc.status_code) from exc
    s = get_settings()
    uri = f"{base}/{quote(s.storage_bucket, safe='')}/{quote(path, safe='/')}"
    with httpx.Client(timeout=30) as client:
        try:
            result = client.post(uri, content=contents,
                                       headers={**headers, "Content-Type": content_type, "x-upsert": "false"})
            result.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # Supabase can encode a duplicate object as HTTP 400 or 409.
            try:
                error = exc.response.json()
            except ValueError:
                error = {}
            collision = status == 409 or (isinstance(error, dict) and (
                error.get("error") == "Duplicate" or error.get("code") in {"Duplicate", "KeyAlreadyExists"}
                or str(error.get("statusCode")) == "409"))
            raise StorageUploadError(uncertain=status == 408 or status >= 500, collision=collision) from exc
        except httpx.HTTPError as exc:
            # A timeout does not tell us whether Storage accepted the upload.
            raise StorageUploadError(uncertain=True) from exc


def remove_private_image(path: str) -> None:
    base, headers = storage_info()
    bucket = get_settings().storage_bucket
    with httpx.Client(timeout=30) as client:
        try:
            result = client.request("DELETE", f"{base}/{quote(bucket, safe='')}",
                                    json={"prefixes": [path]}, headers=headers)
            result.raise_for_status()
            # 200 + [] is an idempotent absence. Do not treat 403/404 as success.
            if result.status_code != 204 and not isinstance(result.json(), list):
                raise ValueError("Unexpected Storage delete acknowledgement")
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="No se pudo compensar la imagen") from exc


def signed_image_url(path: str) -> str:
    base, headers = storage_info()
    s = get_settings()
    uri = f"{base}/sign/{quote(s.storage_bucket, safe='')}/{quote(path, safe='/')}"
    with httpx.Client(timeout=15) as client:
        try:
            result = client.post(uri, json={"expiresIn": 300}, headers=headers)
            result.raise_for_status()
            data = result.json()
            signed = data["signedURL"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="No se pudo acceder a la imagen") from exc
    if signed.startswith("http"):
        return signed
    return s.supabase_url.rstrip("/") + "/storage/v1" + (signed if signed.startswith("/") else "/" + signed)
