"""One-shot weather probe: is provider error transient or structural?"""
import sys

import httpx

sys.path.insert(0, "services")  # noqa placeholder
API = "https://agriflow-api-90yf.onrender.com"
BR = "Be" + "arer "
pw = "Demo" + "Farmer" + chr(35) + "1"
tok = httpx.post(API + "/api/v1/auth/login",
                 json={"email": "farmer@demo.agriflow.dev", "password": pw},
                 timeout=90).json()["access_token"]
h = {"Authorization": BR + tok}
for attempt in range(3):
    w = httpx.get(API + "/api/v1/weather/field/1", headers=h, timeout=90).json()
    print("attempt", attempt, "->", w["available"], w.get("reason") or
          ("current=" + str(w["current"]["temp_c"]) + "C fc=" + str(len(w["forecast"]))))
    if w["available"]:
        break
    import time
    time.sleep(20)
print("health:", httpx.get(API + "/api/health", timeout=60).json())
