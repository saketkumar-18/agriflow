"""Authentication: password hashing (hashlib.scrypt, stdlib) + JWT (PyJWT) + RBAC deps."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Role, User

settings = get_settings()
_scrypt = hashlib.scrypt
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = _scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, dk_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = _scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                     n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(dk_hex)))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id), "role": user.role.value,
        "iat": now, "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": "agriflow",
    }
    return jwt.encode(payload, settings.auth_secret, algorithm=settings.jwt_algorithm)


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "auth.missing_token", "message": "Not authenticated", "details": None}})
    try:
        payload = jwt.decode(creds.credentials, settings.auth_secret,
                             algorithms=[settings.jwt_algorithm], issuer="agriflow")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "auth.expired", "message": "Session expired, please log in again", "details": None}})
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "auth.invalid", "message": "Invalid credentials", "details": None}})
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": {"code": "auth.invalid", "message": "Invalid credentials", "details": None}})
    request.state.user_id = user.id
    return user


def require_roles(*roles: Role):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"error": {"code": "auth.forbidden", "message": "You do not have permission for this action", "details": None}})
        return user
    return dep
