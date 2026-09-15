"""Irrigation events, feedback, notifications, analytics, dashboard summary, sync,
advisories, admin."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Advisory, AuditLog, Farm, FarmerFeedback, Field, IrrigationEvent,
    IrrigationRecommendation, Notification, Role, Sensor, SoilMoistureReading, User, WeatherObservation,
)
from app.schemas import (
    AdvisoryIn, AdvisoryOut, AssignAgronomistIn, FeedbackIn, IrrigationEventIn,
    IrrigationEventOut, NotificationOut, SyncBatchIn, UserPatchIn,
)
from app.services import (
    audit, field_area_ha, get_farm_403, get_field_403, http_err, latest_moisture,
    recommendation_to_dict, store_recommendation, visible_farms,
)
from app.weather import lat_key, weather_provider

router = APIRouter()


# ------------------------------------------------------------- irrigation events

@router.post("/irrigation-events", response_model=IrrigationEventOut, status_code=201)
def create_irrigation_event(body: IrrigationEventIn, request: Request,
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, body.field_id, write=True)
    if body.idempotency_key:
        dup = db.scalar(select(IrrigationEvent).where(
            IrrigationEvent.idempotency_key == body.idempotency_key))
        if dup:  # offline replay: return existing, never double-record
            return IrrigationEventOut.model_validate(dup)
    mm = body.amount_mm
    liters = body.liters
    area_ha = field_area_ha(field)
    if mm is None and liters is not None:
        mm = round(liters / (area_ha * 10000.0), 2)   # 1 mm over 1 ha = 10,000 L
    if liters is None and mm is not None:
        liters = round(mm * area_ha * 10000.0)
    row = IrrigationEvent(field_id=field.id, farmer_id=user.id,
                          recommendation_id=body.recommendation_id,
                          irrigated_at=body.irrigated_at, duration_minutes=body.duration_minutes,
                          amount_mm=mm, liters=liters, note=body.note,
                          idempotency_key=body.idempotency_key)
    db.add(row)
    db.flush()
    audit(db, request, user.id, "irrigation_event.create", "irrigation_event", str(row.id),
          None, {"field_id": field.id, "mm": mm, "liters": liters})
    db.commit()
    db.refresh(row)
    return IrrigationEventOut.model_validate(row)


@router.get("/irrigation-events", response_model=dict)
def list_irrigation_events(field_id: int | None = None, farm_id: int | None = None,
                           page: int = 1, page_size: int = 20,
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(IrrigationEvent).join(Field, IrrigationEvent.field_id == Field.id).join(
        Farm, Field.farm_id == Farm.id)
    allowed = {f.id for f in visible_farms(db, user)}
    q = q.where(Farm.id.in_(allowed or {-1}))
    if field_id:
        q = q.where(IrrigationEvent.field_id == field_id)
    if farm_id:
        get_farm_403(db, user, farm_id)
        q = q.where(Field.farm_id == farm_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(IrrigationEvent.irrigated_at.desc())
                      .offset((page - 1) * page_size).limit(min(page_size, 100))).all()
    return {"items": [IrrigationEventOut.model_validate(r) for r in rows],
            "page": page, "page_size": page_size, "total": total}


# ------------------------------------------------------------- feedback

@router.post("/feedback", status_code=201)
def create_feedback(body: FeedbackIn, request: Request,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rec = db.get(IrrigationRecommendation, body.recommendation_id)
    if rec is None:
        raise http_err("rec.not_found", "Recommendation not found", 404)
    get_field_403(db, user, rec.field_id, write=True)
    fb = FarmerFeedback(recommendation_id=rec.id, farmer_id=user.id,
                        useful=body.useful, did_irrigate=body.did_irrigate,
                        comment=body.comment)
    db.add(fb)
    audit(db, request, user.id, "feedback.create", "recommendation", str(rec.id))
    db.commit()
    return {"id": fb.id}


# ------------------------------------------------------------- notifications

@router.get("/notifications")
def list_notifications(unread: bool = False, page: int = 1, page_size: int = 20,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Notification.created_at.desc())
                      .offset((page - 1) * page_size).limit(min(page_size, 100))).all()
    return {"items": [NotificationOut.model_validate(
        {"id": n.id, "type": n.type, "severity": n.severity, "title_key": n.title_key,
         "params_json": n.params_json, "created_at": n.created_at, "read_at": n.read_at})
        for n in rows],
        "page": page, "page_size": page_size, "total": total}


@router.post("/notifications/{nid}/read", status_code=204)
def mark_read(nid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, nid)
    if n is None or n.user_id != user.id:
        raise http_err("notification.not_found", "Notification not found", 404)
    n.read_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == user.id,
                                  Notification.read_at.is_(None)) \
        .update({"read_at": datetime.now(timezone.utc)})
    db.commit()


# ------------------------------------------------------------- dashboard summary

@router.get("/farms/{farm_id}/summary")
def farm_summary(farm_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    farm = get_farm_403(db, user, farm_id)
    fields = db.scalars(select(Field).where(Field.farm_id == farm.id, Field.is_active)).all()
    out_fields = []
    weather = None
    for f in fields:
        m = latest_moisture(db, f.id)
        age_h = None
        if m:
            age_h = round((datetime.now(timezone.utc) - m.taken_at).total_seconds() / 3600.0, 1)
        rec_row = db.scalars(select(IrrigationRecommendation)
                             .where(IrrigationRecommendation.field_id == f.id)
                             .order_by(IrrigationRecommendation.computed_at.desc()).limit(1)).first()
        if rec_row is None or rec_row.expires_at < datetime.now(timezone.utc):
            rec_row = store_recommendation(db, f)
        rec = recommendation_to_dict(rec_row)
        if rec["override"] and rec["override"]["action"] == "cancel":
            status = "ok"
        elif not rec["irrigation_needed"]:
            status = "ok"
        elif rec["urgency"] in ("HIGH", "CRITICAL"):
            status = "needs_irrigation"
        else:
            status = "review"
        out_fields.append({
            "id": f.id, "name": f.name, "crop_name": f.crop.name if f.crop else None,
            "growth_stage": f.growth_stage.value,
            "soil_moisture": ({"value": m.value_pct, "source": m.source.value,
                               "measured_at": m.taken_at.isoformat(), "age_hours": age_h}
                              if m else None),
            "recommendation": rec, "status": status,
        })
    if farm.latitude is not None and farm.longitude is not None and weather is None and fields:
        from app.routers.data import _weather_payload
        weather = _weather_payload(fields[0]).model_dump()
    return {"farm": {"id": farm.id, "name": farm.name, "demo": farm.demo},
            "fields": out_fields, "weather_snapshot": weather,
            "generated_at": datetime.now(timezone.utc).isoformat()}


# ------------------------------------------------------------- field detail + history

@router.get("/fields/{field_id}/detail")
def field_detail(field_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    from app.routers.data import _weather_payload
    from app.routers.farms import _field_out
    field, _ = get_field_403(db, user, field_id)
    m = latest_moisture(db, field.id)
    rec_row = db.scalars(select(IrrigationRecommendation)
                         .where(IrrigationRecommendation.field_id == field.id)
                         .order_by(IrrigationRecommendation.computed_at.desc()).limit(1)).first()
    if rec_row is None:
        rec_row = store_recommendation(db, field)
    return {"field": _field_out(db, field).model_dump(),
            "latest_reading": ({"value_pct": m.value_pct, "source": m.source.value,
                                "taken_at": m.taken_at.isoformat()} if m else None),
            "recommendation": recommendation_to_dict(rec_row),
            "weather": _weather_payload(field).model_dump()}


@router.get("/fields/{field_id}/history")
def field_history(field_id: int, days: int = 30, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    field, farm = get_field_403(db, user, field_id)
    days = min(days, 120)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    readings = db.scalars(select(SoilMoistureReading)
                          .where(SoilMoistureReading.field_id == field.id,
                                 SoilMoistureReading.taken_at >= since)
                          .order_by(SoilMoistureReading.taken_at)).all()
    events = db.scalars(select(IrrigationEvent)
                        .where(IrrigationEvent.field_id == field.id,
                               IrrigationEvent.irrigated_at >= since)).all()
    per_day_mm: dict[str, float] = {}
    for e in events:
        k = e.irrigated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        per_day_mm[k] = per_day_mm.get(k, 0.0) + (e.amount_mm or 0.0)

    rain: list[dict] = []
    temps: list[dict] = []
    et0: list[dict] = []
    etc: list[dict] = []
    if farm.latitude is not None:
        obs = db.scalars(select(WeatherObservation)
                         .where(WeatherObservation.lat_key == lat_key(farm.latitude, farm.longitude),
                                WeatherObservation.observed_at >= since)
                         .order_by(WeatherObservation.observed_at)).all()
        by_day: dict[str, dict] = {}
        for o in obs:
            k = o.observed_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
            d = by_day.setdefault(k, {"rain": 0.0, "tmax": None, "tmin": None, "et0": None})
            d["rain"] += o.rain_mm or 0.0
            if o.tmax_c is not None:
                d["tmax"] = max(d["tmax"] or o.tmax_c, o.tmax_c)
            if o.tmin_c is not None:
                d["tmin"] = min(d["tmin"] or o.tmin_c, o.tmin_c)
            d["et0"] = d["et0"] or o.et0_mm
        kc = (field.crop.stage_params or {}).get(field.growth_stage.value, {}).get("kc", 1.0)
        for k in sorted(by_day):
            d = by_day[k]
            rain.append({"day": k, "value": round(d["rain"], 1),
                         "kind": "demo_observed" if field.demo else "observed"})
            if d["tmax"] is not None and d["tmin"] is not None:
                temps.append({"day": k, "min": round(d["tmin"], 1), "max": round(d["tmax"], 1)})
            if d["et0"] is not None:
                et0.append({"day": k, "value": round(d["et0"], 2), "kind": "estimated"})
                etc.append({"day": k, "value": round(d["et0"] * float(kc), 2), "kind": "estimated"})
    return {"field_id": field.id, "from": since.isoformat(),
            "to": datetime.now(timezone.utc).isoformat(),
            "soil_moisture": [{"t": r.taken_at.isoformat(), "value": r.value_pct,
                               "source": r.source.value} for r in readings],
            "rainfall_mm": rain, "temperature_c": temps,
            "irrigation_mm": [{"day": k, "value": round(v, 1)} for k, v in sorted(per_day_mm.items())],
            "et0_mm": et0, "etc_mm": etc}


# ------------------------------------------------------------- analytics

@router.get("/analytics/farm/{farm_id}")
def farm_analytics(farm_id: int, month: str | None = None,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm_403(db, user, farm_id)
    y, mo = (int(month[:4]), int(month[5:7])) if month and "-" in month else \
        (datetime.now(timezone.utc).year, datetime.now(timezone.utc).month)
    start = datetime(y, mo, 1, tzinfo=timezone.utc)
    end = datetime(y, mo, calendar.monthrange(y, mo)[1], 23, 59, 59, tzinfo=timezone.utc)
    fields = db.scalars(select(Field).where(Field.farm_id == farm.id)).all()
    fids = [f.id for f in fields] or [-1]
    used = db.scalar(select(func.coalesce(func.sum(IrrigationEvent.liters), 0.0))
                     .where(IrrigationEvent.field_id.in_(fids),
                            IrrigationEvent.irrigated_at >= start,
                            IrrigationEvent.irrigated_at <= end)) or 0.0
    rec_used = db.scalar(select(func.coalesce(func.sum(IrrigationEvent.liters), 0.0))
                         .where(IrrigationEvent.field_id.in_(fids),
                                IrrigationEvent.recommendation_id.isnot(None),
                                IrrigationEvent.irrigated_at >= start,
                                IrrigationEvent.irrigated_at <= end)) or 0.0
    # modelled baseline: scheduled-irrigation emulation over recommendation-issued days
    weekly: list[dict] = []
    cursor = start
    while cursor <= end:
        w_end = min(cursor + timedelta(days=7), end)
        wl = db.scalar(select(func.coalesce(func.sum(IrrigationEvent.liters), 0.0))
                       .where(IrrigationEvent.field_id.in_(fids),
                              IrrigationEvent.irrigated_at >= cursor,
                              IrrigationEvent.irrigated_at <= w_end)) or 0.0
        weekly.append({"week": cursor.strftime("%Y-%m-%d"), "irrigated_liters": round(wl)})
        cursor = w_end + timedelta(days=1)
    return {"month": f"{y}-{mo:02d}",
            "total_irrigation_liters": round(used),
            "recommended_liters": round(rec_used),
            "potential_difference_liters": round(max(0.0, used - rec_used)),
            "wording_key": "analytics.potential_reduction_note",
            "events_count": db.scalar(select(func.count(IrrigationEvent.id))
                                      .where(IrrigationEvent.field_id.in_(fids),
                                             IrrigationEvent.irrigated_at >= start,
                                             IrrigationEvent.irrigated_at <= end)) or 0,
            "fields": [{"id": f.id, "name": f.name} for f in fields],
            "weekly": weekly}


@router.get("/analytics/farm/{farm_id}/water-over-time")
def water_over_time(farm_id: int, days: int = 90, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    farm = get_farm_403(db, user, farm_id)
    days = min(days, 365)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fields = db.scalars(select(Field).where(Field.farm_id == farm.id)).all()
    fids = [f.id for f in fields] or [-1]
    rows = db.scalars(select(IrrigationEvent)
                      .where(IrrigationEvent.field_id.in_(fids),
                             IrrigationEvent.irrigated_at >= since)).all()
    agg: dict[str, dict] = {}
    for e in rows:
        k = e.irrigated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        a = agg.setdefault(k, {"liters": 0.0, "mm": 0.0, "n": 0})
        a["liters"] += e.liters or 0.0
        a["mm"] += e.amount_mm or 0.0
        a["n"] += 1
    return [{"day": k, "liters": round(v["liters"]), "mm": round(v["mm"] / v["n"], 1)}
            for k, v in sorted(agg.items())]


# ------------------------------------------------------------- advisories

@router.get("/fields/{field_id}/advisories", response_model=list[AdvisoryOut])
def list_advisories(field_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    get_field_403(db, user, field_id)
    return db.scalars(select(Advisory).where(Advisory.field_id == field_id)
                      .order_by(Advisory.created_at.desc()).limit(50)).all()


@router.post("/advisories", response_model=AdvisoryOut, status_code=201)
def add_advisory(body: AdvisoryIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    if user.role not in (Role.agronomist, Role.admin):
        raise http_err("advisory.forbidden", "Only agronomists can add advisories", 403)
    get_field_403(db, user, body.field_id)
    a = Advisory(field_id=body.field_id, author_id=user.id, note=body.note)
    db.add(a)
    db.flush()
    audit(db, request, user.id, "advisory.create", "advisory", str(a.id),
          None, {"field_id": body.field_id})
    db.commit()
    return a


@router.get("/agronomist/farms")
def agronomist_farms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in (Role.agronomist, Role.admin):
        raise http_err("agronomist.only", "Agronomist or admin role required", 403)
    out = []
    for farm in visible_farms(db, user):
        fields = db.scalars(select(Field).where(Field.farm_id == farm.id, Field.is_active)).all()
        needs = 0
        for f in fields:
            rec = db.scalars(select(IrrigationRecommendation)
                             .where(IrrigationRecommendation.field_id == f.id)
                             .order_by(IrrigationRecommendation.computed_at.desc()).limit(1)).first()
            if rec and rec.irrigation_needed and rec.urgency.value in ("HIGH", "CRITICAL"):
                needs += 1
        out.append({"id": farm.id, "name": farm.name, "field_count": len(fields),
                    "needs_review_count": needs, "demo": farm.demo})
    return out


# ------------------------------------------------------------- sync (offline queue)

@router.post("/sync/batch")
def sync_batch(body: SyncBatchIn, request: Request,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    results = []
    for action in body.actions:
        try:
            if action.type == "irrigation_event":
                payload = {**action.payload}
                payload.pop("local_id", None)
                payload.setdefault("idempotency_key", action.local_id)
                evt = create_irrigation_event(IrrigationEventIn.model_validate(payload),
                                              request, db, user)
                results.append({"local_id": action.local_id, "status": "created" if evt.id else "duplicate"})
            elif action.type == "reading":
                from app.routers.data import add_reading
                from app.schemas import ReadingIn
                payload = {**action.payload}
                fid = payload.pop("field_id")
                r = add_reading(fid, ReadingIn.model_validate(payload), request, db, user)
                results.append({"local_id": action.local_id, "status": "created", "id": r.id})
            elif action.type == "feedback":
                fb = create_feedback(FeedbackIn.model_validate(action.payload), request, db, user)
                results.append({"local_id": action.local_id, "status": "created", "id": fb["id"]})
            else:
                results.append({"local_id": action.local_id, "status": "error",
                                "error": "sync.unknown_type"})
        except Exception as exc:
            detail = getattr(exc, "detail", None)
            code = detail["error"]["code"] if isinstance(detail, dict) else "sync.failed"
            results.append({"local_id": action.local_id, "status": "error", "error": code})
    return {"results": results}


# ------------------------------------------------------------- admin

@router.get("/admin/stats")
def admin_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise http_err("admin.only", "Admin role required", 403)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sensors = db.scalars(select(Sensor)).all()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    online = sum(1 for s in sensors if s.last_seen_at and s.last_seen_at >= cutoff)
    snap = None
    weather_health = "not_configured"
    from app.config import get_settings
    if get_settings().weather_provider.lower().startswith("open"):
        snap = weather_provider().get_weather(26.14, 91.72, days=1)
        weather_health = "ok" if snap.available else "error"
    return {
        "total_users": db.scalar(select(func.count(User.id))) or 0,
        "total_farms": db.scalar(select(func.count(Farm.id)).where(Farm.is_active)) or 0,
        "active_farms": db.scalar(select(func.count(Farm.id)).where(Farm.is_active)) or 0,
        "total_fields": db.scalar(select(func.count(Field.id)).where(Field.is_active)) or 0,
        "recommendations_today": db.scalar(select(func.count(IrrigationRecommendation.id))
                                           .where(IrrigationRecommendation.computed_at >= today_start)) or 0,
        "irrigation_events_30d": db.scalar(select(func.count(IrrigationEvent.id))
                                           .where(IrrigationEvent.irrigated_at >=
                                                  datetime.now(timezone.utc) - timedelta(days=30))) or 0,
        "sensor_uptime_pct": round(100.0 * online / len(sensors), 1) if sensors else None,
        "weather_provider_health": weather_health,
    }


@router.get("/admin/users")
def admin_users(role: str | None = None, page: int = 1, page_size: int = 20,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise http_err("admin.only", "Admin role required", 403)
    q = select(User)
    if role:
        q = q.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(User.id).offset((page - 1) * page_size)
                      .limit(min(page_size, 100))).all()
    from app.schemas import UserOut
    return {"items": [UserOut.model_validate(u) for u in rows],
            "page": page, "page_size": page_size, "total": total}


@router.patch("/admin/users/{target_id}")
def admin_patch_user(target_id: int, body: UserPatchIn, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise http_err("admin.only", "Admin role required", 403)
    target = db.get(User, target_id)
    if target is None:
        raise http_err("user.not_found", "User not found", 404)
    previous = {"role": target.role.value, "is_active": target.is_active}
    if body.role is not None:
        target.role = body.role
    if body.is_active is not None:
        target.is_active = body.is_active
    audit(db, request, user.id, "admin.user_update", "user", str(target.id),
          previous, {"role": target.role.value, "is_active": target.is_active})
    db.commit()
    from app.schemas import UserOut
    return UserOut.model_validate(target)


@router.post("/admin/farms/{farm_id}/assign-agronomist")
def assign_agronomist(farm_id: int, body: AssignAgronomistIn, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise http_err("admin.only", "Admin role required", 403)
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise http_err("farm.not_found", "Farm not found", 404)
    agr = db.get(User, body.user_id)
    if agr is None or agr.role not in (Role.agronomist,):
        raise http_err("user.not_agronomist", "Target user is not an agronomist", 422)
    farm.assigned_agronomist_id = agr.id
    audit(db, request, user.id, "admin.assign_agronomist", "farm", str(farm.id),
          None, {"agronomist_id": agr.id})
    db.commit()
    return {"ok": True}


@router.get("/admin/audit")
def admin_audit(page: int = 1, page_size: int = 25, user_id: int | None = None,
                action: str | None = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != Role.admin:
        raise http_err("admin.only", "Admin role required", 403)
    q = select(AuditLog)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(AuditLog.created_at.desc())
                      .offset((page - 1) * page_size).limit(min(page_size, 100))).all()
    return {"items": [{"id": a.id, "user_id": a.user_id, "action": a.action,
                       "resource_type": a.resource_type, "resource_id": a.resource_id,
                       "previous": a.previous_json, "new": a.new_json,
                       "ip": a.ip, "created_at": a.created_at.isoformat()} for a in rows],
            "page": page, "page_size": page_size, "total": total}
