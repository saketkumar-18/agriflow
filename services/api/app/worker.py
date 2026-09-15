"""Background worker (spec 50): DB-backed job loop, no Redis required.

Jobs: weather_sync (pull daily forecast + store observations), recommendation
generation per active field, sensor_offline checks, expired cleanup, analytics
rollup placeholder. Run: python -m app.worker
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Farm, Field, Job, WeatherForecast, WeatherObservation
from app.services import check_sensor_offline, store_recommendation
from app.weather import lat_key, weather_provider

log = logging.getLogger("agriflow.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _enqueue_daily_jobs(db) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    farms = db.scalars(select(Farm).where(Farm.is_active, Farm.latitude.isnot(None))).all()
    for f in farms:
        k = f"weather:{f.id}:{today}"
        if not db.scalar(select(Job.id).where(Job.dedupe_key == k)):
            db.add(Job(kind="weather_sync", payload_json={"farm_id": f.id}, dedupe_key=k))
    # one recommendation sweep job per field per day:
    fields = db.scalars(select(Field).join(Farm).where(Field.is_active, Farm.is_active)).all()
    for fl in fields:
        k = f"reco:{fl.id}:{today}"
        if not db.scalar(select(Job.id).where(Job.dedupe_key == k)):
            db.add(Job(kind="recommendation", payload_json={"field_id": fl.id}, dedupe_key=k))
    if not db.scalar(select(Job.id).where(Job.dedupe_key == f"sensor:{today}")):
        db.add(Job(kind="sensor_check", payload_json={}, dedupe_key=f"sensor:{today}"))
    db.commit()


def _run_job(db, job: Job) -> None:
    if job.kind == "weather_sync":
        farm = db.get(Farm, job.payload_json["farm_id"])
        if farm and farm.latitude is not None:
            snap = weather_provider().get_weather(farm.latitude, farm.longitude, days=6)
            if snap.available:
                for fd in snap.forecast:
                    exists = db.scalar(select(WeatherForecast.id).where(
                        WeatherForecast.lat_key == lat_key(snap.lat, snap.lon),
                        WeatherForecast.day == fd.day,
                        WeatherForecast.generated_at >= datetime.now(timezone.utc) - timedelta(hours=24)))
                    if not exists:
                        db.add(WeatherForecast(lat_key=lat_key(snap.lat, snap.lon),
                                               generated_at=snap.fetched_at, day=fd.day,
                                               min_c=fd.min_c, max_c=fd.max_c,
                                               rain_prob_pct=fd.rain_prob_pct, rain_mm=fd.rain_mm,
                                               et0_mm=fd.et0_mm, condition_code=fd.condition_code,
                                               provider=snap.provider))
    elif job.kind == "recommendation":
        field = db.get(Field, job.payload_json["field_id"])
        if field and field.is_active:
            store_recommendation(db, field)
    elif job.kind == "sensor_check":
        check_sensor_offline(db)
    elif job.kind == "cleanup":
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        db.query(WeatherObservation).filter(WeatherObservation.observed_at < cutoff).delete()
        db.query(Job).filter(Job.status == "done", Job.finished_at <
                             datetime.now(timezone.utc) - timedelta(days=30)).delete()
    db.commit()


def run_once() -> int:
    db = SessionLocal()
    try:
        _enqueue_daily_jobs(db)
        jobs = db.scalars(select(Job).where(Job.status == "pending")
                          .order_by(Job.due_at).limit(10)).all()
        done = 0
        for job in jobs:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.attempts += 1
            db.commit()
            try:
                _run_job(db, job)
                job.status = "done"
                job.finished_at = datetime.now(timezone.utc)
            except Exception as exc:
                db.rollback()
                job.status = "failed" if job.attempts >= 3 else "pending"
                job.last_error = str(exc)[:480]
                log.exception("job %s failed", job.kind)
            db.commit()
            done += 1
        return done
    finally:
        db.close()


def main() -> None:
    log.info("AgriFlow worker started (DB-backed queue; poll every 60s)")
    while True:
        try:
            n = run_once()
            if n:
                log.info("processed %s jobs", n)
        except Exception:
            log.exception("worker loop error")
        time.sleep(60)


if __name__ == "__main__":
    main()
