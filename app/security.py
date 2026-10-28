import uuid
from dataclasses import dataclass
from functools import lru_cache
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import Profile

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID
    role: str


@lru_cache
def jwks_client() -> PyJWKClient:
    url = get_settings().supabase_url.rstrip("/")
    return PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_jwk_set=True, lifespan=300)


def get_current_actor(
    token: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Actor:
    if token is None or token.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Se requiere un token de acceso")
    issuer = get_settings().supabase_url.rstrip("/") + "/auth/v1"
    try:
        key = jwks_client().get_signing_key_from_jwt(token.credentials).key
        claims = jwt.decode(
            token.credentials,
            key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["sub", "exp", "iss", "aud"]},
        )
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, OSError):
        raise HTTPException(status_code=401, detail="Token inválido o vencido")
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(status_code=403, detail="Usuario sin perfil habilitado")
    return Actor(id=user_id, role=profile.role)


def require_roles(*accepted: str):
    def inner(actor: Actor = Depends(get_current_actor)) -> Actor:
        if actor.role not in accepted:
            raise HTTPException(status_code=403, detail="No tienes permiso para esta operación")
        return actor
    return inner
