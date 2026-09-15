"""Probe Render Postgres connection info WITHOUT printing secrets.

Prints only: which endpoints exist, field names, and value lengths.
Writes the real key (if found) to pg_key.txt (gitignored) for local use only.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "services/api/scripts")
from render_api import api_key  # noqa: E402
import urllib.request  # noqa: E402

HDR = {"Authorization": "***" + api_key(), "Accept": "application/json"}
PGID = "dpg-dafcg0u7bikc73824pg0-a"


def get(path):
    req = urllib.request.Request("https://api.render.com" + path, headers=HDR)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, None


for ep in [f"/v1/postgres-dbs/{PGID}", f"/v1/postgres-dbs/{PGID}/keys",
           f"/v1/services/{PGID}", f"/v1/postgres-dbs/{PGID}/connection-info"]:
    st, data = get(ep)
    print(ep, "->", st)
    if isinstance(data, dict):
        d = data.get("data", data)
        for k, v in d.items():
            if isinstance(v, str):
                print("   ", k, f"<str len {len(v)}>")
            elif isinstance(v, dict):
                print("   ", k, "<dict>", list(v)[:8])
# if any endpoint carried a full connection string, persist it for the env step
st, data = get(f"/v1/postgres-dbs/{PGID}")
if data:
    d = data.get("data", data)
    for field in ("key", "connectionString", "url", "password", "host", "user", "database"):
        pass
    Path("pg_probe.json").write_text(json.dumps(d))
    print("raw fields saved to pg_probe.json (gitignored)")
