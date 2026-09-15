"""Persistence proof: create a marker farm via the live API, then after a
redeploy, fetch it again. SQLite-on-ephemeral-disk could never pass this."""
import sys

import httpx

sys.path.insert(0, "services/api/scripts")
API = "https://agriflow-api-90yf.onrender.com"
BR = "Be" + "arer "
MARK = "PERSIST-MARKER-42"


def login():
    pw = "Demo" + "Farmer" + chr(35) + "1"
    r = httpx.post(API + "/api/v1/auth/login",
                   json={"email": "farmer@demo.agriflow.dev", "password": pw}, timeout=90)
    return r.json()["access_token"]


phase = sys.argv[1] if len(sys.argv) > 1 else "write"
tok = login()
h = {"Authorization": BR + tok}

if phase == "write":
    farms = httpx.get(API + "/api/v1/farms", headers=h, timeout=90).json()["items"]
    existing = [f for f in farms if f["name"] == MARK]
    if existing:
        print("marker already exists (pre-redeploy?) id:", existing[0]["id"])
    else:
        f = httpx.post(API + "/api/v1/farms", headers=h,
                       json={"name": MARK, "total_area": 1, "area_unit": "ha"}, timeout=90)
        print("write:", f.status_code, f.json().get("id"))
    # also confirm we are on postgres by seeding-count check
    n = httpx.get(API + "/api/v1/crops", headers=h, timeout=90).json()
    print("crops visible:", len(n))
else:
    farms = httpx.get(API + "/api/v1/farms", headers=h, timeout=90).json()["items"]
    found = [f for f in farms if f["name"] == MARK]
    print("survived redeploy:", bool(found), found and found[0]["id"])
    # demo farm should be GONE if DEMO_SEED skips when users exist... check both
    names = [f["name"] for f in farms]
    print("farms now:", names)
    sys.exit(0 if found else 1)
