"""Farm + field management routers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Crop, Farm, Field, Role, Sensor, SoilType, User
from app.schemas import (
    FieldIn, FieldOut, FieldPatchIn, FarmIn, FarmOut,
)
from app.services import (
    audit, get_farm_403, get_field_403, http_err, visible_farms,
)

router = APIRouter()


def _farm_out(db: Session, farm: Farm) -> FarmOut:
    out = FarmOut.model_validate(farm)
    out.field_count = db.scalar(select(func.count(Field.id))
                                .where(Field.farm_id == farm.id, Field.is_active)) or 0
    return out


def _field_out(db: Session, field: Field) -> FieldOut:
    out = FieldOut.model_validate(field)
    out.sensor_present = bool(db.scalar(select(func.count(Sensor.id))
                                        .where(Sensor.field_id == field.id)))
    return out


@router.get("/farms", response_model=dict)
def list_farms(page: int = 1, page_size: int = 20,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farms = visible_farms(db, user)
    items = [_farm_out(db, f) for f in farms[(page - 1) * page_size:(page - 1) * page_size + page_size]]
    return {"items": items, "page": page, "page_size": page_size, "total": len(farms)}


@router.post("/farms", response_model=FarmOut, status_code=201)
def create_farm(body: FarmIn, request: Request,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role in (Role.agronomist,):
        raise http_err("farm.create_forbidden", "Only farmers can create farms", 403)
    farm = Farm(farmer_id=user.id, **body.model_dump())
    db.add(farm)
    db.flush()
    audit(db, request, user.id, "farm.create", "farm", str(farm.id), None,
          {"name": farm.name, "area": farm.total_area})
    db.commit()
    db.refresh(farm)
    return _farm_out(db, farm)


@router.get("/farms/{farm_id}", response_model=FarmOut)
def get_farm(farm_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _farm_out(db, get_farm_403(db, user, farm_id))


@router.patch("/farms/{farm_id}", response_model=FarmOut)
def update_farm(farm_id: int, body: FarmIn, request: Request,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm_403(db, user, farm_id)
    if user.role == Role.agronomist:
        raise http_err("farm.readonly_agronomist", "Agronomists cannot edit farms", 403)
    previous = {"name": farm.name, "location_text": farm.location_text}
    for k, v in body.model_dump().items():
        setattr(farm, k, v)
    audit(db, request, user.id, "farm.update", "farm", str(farm.id), previous,
          {"name": farm.name})
    db.commit()
    db.refresh(farm)
    return _farm_out(db, farm)


@router.delete("/farms/{farm_id}", status_code=204)
def delete_farm(farm_id: int, request: Request,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm_403(db, user, farm_id)
    if user.role == Role.agronomist:
        raise http_err("farm.readonly_agronomist", "Agronomists cannot delete farms", 403)
    farm.is_active = False  # soft delete; history preserved (spec 47)
    audit(db, request, user.id, "farm.delete", "farm", str(farm.id))
    db.commit()


@router.post("/farms/{farm_id}/fields", response_model=FieldOut, status_code=201)
def create_field(farm_id: int, body: FieldIn, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm_403(db, user, farm_id)
    if user.role == Role.agronomist:
        raise http_err("field.readonly_agronomist", "Agronomists cannot create fields", 403)
    if db.get(Crop, body.crop_id) is None:
        raise http_err("crop.not_found", "Unknown crop", 422)
    if db.get(SoilType, body.soil_type_id) is None:
        raise http_err("soil.not_found", "Unknown soil type", 422)
    field = Field(farm_id=farm.id, growth_stage=body.growth_stage_code,
                  **{k: v for k, v in body.model_dump().items()
                     if k not in ("growth_stage_code",)})
    db.add(field)
    db.flush()
    audit(db, request, user.id, "field.create", "field", str(field.id), None,
          {"name": field.name, "crop_id": field.crop_id})
    db.commit()
    db.refresh(field)
    return _field_out(db, field)


@router.get("/fields/{field_id}", response_model=FieldOut)
def get_field(field_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    return _field_out(db, field)


@router.patch("/fields/{field_id}", response_model=FieldOut)
def update_field(field_id: int, body: FieldPatchIn, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id, write=True)
    data = body.model_dump(exclude_none=True)
    previous = {k: (field.growth_stage.value if k == "growth_stage_code" else getattr(field, k))
                for k in data}
    if "growth_stage_code" in data:
        field.growth_stage = data.pop("growth_stage_code")
    for k, v in data.items():
        setattr(field, k, v)
    audit(db, request, user.id, "field.update", "field", str(field.id), previous, data)
    db.commit()
    db.refresh(field)
    return _field_out(db, field)


@router.delete("/fields/{field_id}", status_code=204)
def delete_field(field_id: int, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id, write=True)
    field.is_active = False
    audit(db, request, user.id, "field.delete", "field", str(field.id))
    db.commit()
