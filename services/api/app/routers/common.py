"""Auth + preferences + reference data routers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import Crop, SoilType, User
from app.schemas import (
    CropOut, LoginIn, PreferencesIn, RegisterIn, SoilTypeOut, TokenOut, UserOut,
)
from app.services import audit, http_err

router = APIRouter()
settings = get_settings()


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.email == body.email.lower()))
    if exists:
        raise http_err("auth.email_taken", "An account with this email already exists", 409)
    user = User(email=body.email.lower(), password_hash=hash_password(body.password),
                full_name=body.full_name.strip(), phone=body.phone, language=body.language)
    # public registration is farmer-only (RBAC): admin/agronomist created via admin API
    db.add(user)
    db.flush()
    audit(db, request, user.id, "user.register", "user", str(user.id))
    db.commit()
    return TokenOut(access_token=create_access_token(user),
                    expires_in=settings.access_token_expire_minutes * 60,
                    user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise http_err("auth.invalid", "Incorrect email or password", 401)
    return TokenOut(access_token=create_access_token(user),
                    expires_in=settings.access_token_expire_minutes * 60,
                    user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.put("/auth/me/preferences")
def save_preferences(body: PreferencesIn, request: Request,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    previous = {"alert_level": user.alert_level, "language": user.language}
    user.alert_level = body.alert_level
    if body.language:
        user.language = body.language
    if body.channels:
        user.channel_push = body.channels.get("push", user.channel_push)
        user.channel_email = body.channels.get("email", user.channel_email)
    audit(db, request, user.id, "user.preferences", "user", str(user.id),
          previous, {"alert_level": user.alert_level, "language": user.language,
                     "channels": {"push": user.channel_push, "email": user.channel_email}})
    db.commit()
    return {"alert_level": user.alert_level,
            "channels": {"push": user.channel_push, "email": user.channel_email},
            "language": user.language,
            "email_available": bool(settings.smtp_host)}


# ---------------- reference data (read-only; configurable in DB, spec 7/9)

@router.get("/crops", response_model=list[CropOut])
def list_crops(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Crop).order_by(Crop.name)).all()


@router.get("/crops/{crop_id}", response_model=CropOut)
def get_crop(crop_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    crop = db.get(Crop, crop_id)
    if crop is None:
        raise http_err("crop.not_found", "Crop not found", 404)
    return crop


@router.get("/soil-types", response_model=list[SoilTypeOut])
def list_soil_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(SoilType).order_by(SoilType.name)).all()
