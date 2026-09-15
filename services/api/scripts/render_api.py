#!/usr/bin/env python3
"""Render REST helper: read CLI key from ~/.render/cli.yaml at runtime (never printed).

Usage:
  python render_api.py GET /v1/postgres-dbs
  python render_api.py GET /v1/postgres-dbs/<id>/keys
  python render_api.py POST /v1/services -d @payload.json
Secret values are written to a local file (gitignored) instead of stdout when
--out is given.
"""
import json
import sys
import urllib.request
from pathlib import Path

CFG = Path.home() / ".render" / "cli.yaml"


def api_key() -> str:
    for line in CFG.read_text().splitlines():
        line = line.strip()
        if line.startswith("api-key:") or line.startswith("apiKey:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("no api-key in " + str(CFG))


def main() -> None:
    method, path = sys.argv[1], sys.argv[2]
    body, out = None, None
    args = sys.argv[3:]
    i = 0
    while i < len(args):
        if args[i] == "-d":
            i += 1
            v = args[i]
            body = json.loads(Path(v[1:]).read_text()) if v.startswith("@") else json.loads(v)
        elif args[i] == "--out":
            i += 1
            out = args[i]
        i += 1
    req = urllib.request.Request(
        "https://api.render.com" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + api_key(),
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:400], file=sys.stderr)
        raise SystemExit(1)
    if out:
        Path(out).write_text(json.dumps(data, indent=2))
        print("wrote", out)
    else:
        print(json.dumps(data, indent=2)[:3000])


if __name__ == "__main__":
    main()
