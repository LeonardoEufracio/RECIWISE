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



async def put_private_image(path: str, contents: bytes, content_type: str) -> None:
    base, headers = storage_info()
    s = get_settings()
    uri = f"{base}/{quote(s.storage_bucket, safe='')}/{quote(path, safe='/')}"
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            result = await client.post(uri, content=contents,
                                       headers={**headers, "Content-Type": content_type, "x-upsert": "false"})
            result.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="No se pudo guardar la imagen") from exc


async def signed_image_url(path: str) -> str:
    base, headers = storage_info()
    s = get_settings()
    uri = f"{base}/sign/{quote(s.storage_bucket, safe='')}/{quote(path, safe='/')}"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            result = await client.post(uri, json={"expiresIn": 300}, headers=headers)
            result.raise_for_status()
            data = result.json()
            signed = data["signedURL"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="No se pudo acceder a la imagen") from exc
    if signed.startswith("http"):
        return signed
    return s.supabase_url.rstrip("/") + "/storage/v1" + (signed if signed.startswith("/") else "/" + signed)
