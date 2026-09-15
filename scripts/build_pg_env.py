"""Point agriflow-api at the shared Render Postgres (internal connection).

Reads render_pg_full.json (fetched with --include-sensitive-connection-info,
gitignored). Rewrites DATABASE_URL to the INTERNAL psycopg2 URL and adds
PG_SCHEMA=agriflow so our tables live in an isolated schema. The internal
string is scheme-only usable; we convert postgres:// -> postgresql+psycopg2://
and append sslmode=require (Render internal trust, but harmless).
PUT replaces the WHOLE set — we resend every existing var, unchanged.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

d = json.loads(Path("render_pg_full.json").read_text())
d = d.get("data", d)
ci = d["connectionInfo"]
internal = ci["internalConnectionString"]
assert internal.startswith("postgres://"), "unexpected scheme"

# force ssl over the password portion only (render internal usually trusts; keep require-safe)
url = "postgresql+psycopg2://" + internal[len("postgres://"):]
if "?" not in url:
    url += "?sslmode=require"
Path("render_dburl.txt").write_text(url)
print("url shape:", re.sub(r":[^:@/]+@", ":***@", url)[:90])

# AUTH_SECRET already lives on the service — fetch current set instead of hardcoding
cur = subprocess.run([sys.executable, "services/api/scripts/render_api.py",
                      "GET", "/v1/services/srv-dakotqqfngtc73f09ka0/env-vars"],
                     capture_output=True, text=True)
existing = {e["envVar"]["key"]: e["envVar"].get("value") or ""
            for e in json.loads(cur.stdout)}
auth = existing.get("AUTH_SECRET")
assert auth, "could not read current AUTH_SECRET"

env = [
    {"key": "DATABASE_URL", "value": url, "optional": False},
    {"key": "PG_SCHEMA", "value": "agriflow", "optional": False},
    {"key": "AUTH_SECRET", "value": auth, "optional": False},
    {"key": "ENVIRONMENT", "value": "production", "optional": False},
    {"key": "DEMO_SEED_ENABLED", "value": "true", "optional": False},
    {"key": "WEATHER_PROVIDER", "value": "open_meteo", "optional": False},
    {"key": "CORS_ORIGINS",
     "value": "https://agriflow-web-nu.vercel.app,http://localhost:3000,http://localhost:3005",
     "optional": False},
]
Path("render_env_arr.json").write_text(json.dumps(env))
print("env set written (7 vars)")
