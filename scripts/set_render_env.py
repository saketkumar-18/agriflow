"""Set full env on the agriflow-api Render service (PUT replaces the whole set!)."""
import json
import secrets
import subprocess
import sys

SVR = "srv-dakotqqfngtc73f09ka0"
# keep payload out of this file: generate AUTH_SECRET fresh (rotate is fine, new service)
env = [
    {"key": "DATABASE_URL", "value": "sqlite:////srv/api/data/agriflow.db"},
    {"key": "AUTH_SECRET", "value": secrets.token_urlsafe(48)},
    {"key": "ENVIRONMENT", "value": "production"},
    {"key": "DEMO_SEED_ENABLED", "value": "true"},
    {"key": "WEATHER_PROVIDER", "value": "open_meteo"},
    {"key": "CORS_ORIGINS",
     "value": "https://agriflow-web-nu.vercel.app,http://localhost:3000,http://localhost:3005"},
]
payload = [{"name": e["key"], "value": e["value"], "optional": False} for e in env]
json.dump({"envVars": payload}, open("render_env.json", "w"))
r = subprocess.run([sys.executable, "services/api/scripts/render_api.py",
                    "PUT", f"/v1/services/{SVR}/env-vars", "-d", "@render_env.json"],
                   capture_output=True, text=True, cwd=".")
print("PUT status rc=", r.returncode)
print(r.stdout[:400] or r.stderr[:400])
