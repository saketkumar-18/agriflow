"""Generate Render API-service payload with fresh secrets (payload holds no
secret values beyond the generated AUTH_SECRET, which belongs to this app)."""
import json
import secrets
import sys

payload = {
    "type": "web_service",
    "name": "agriflow-api",
    "repo": "https://github.com/saketkumar-18/agriflow",
    "branch": "main",
    "runtime": "docker",
    "plan": "free",
    "region": "singapore",
    "autoDeploy": "yes",
    "dockerfilePath": "services/api/Dockerfile",
    "healthCheckPath": "/api/health",
    "envVars": [
        {"key": "DATABASE_URL", "value": "sqlite:////srv/api/data/agriflow.db", "optional": False},
        {"key": "AUTH_SECRET", "value": secrets.token_urlsafe(48), "optional": False},
        {"key": "ENVIRONMENT", "value": "production", "optional": False},
        {"key": "DEMO_SEED_ENABLED", "value": "true", "optional": False},
        {"key": "WEATHER_PROVIDER", "value": "open_meteo", "optional": False},
    ],
    "disk": {
        "name": "agriflow-data",
        "mountPath": "/srv/api/data",
        "sizeGB": 1,
    },
}
json.dump(payload, open(sys.argv[1], "w"))
print("payload written", sys.argv[1])
