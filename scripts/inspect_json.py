"""Inspect a saved Render API JSON: print field names + value lengths, and if a
full connection string/key exists, write DATABASE_URL to render_dburl.txt
(gitignored). Secrets never go to stdout."""
import json
import re
import sys
from pathlib import Path

d = json.load(open(sys.argv[1]))
if isinstance(d, dict):
    d = d.get("data", d)
for k, v in (d.items() if isinstance(d, dict) else []):
    if isinstance(v, str):
        print(f"{k}: str len={len(v)}" + ("  (looks like a secret)" if len(v) > 12 else f" = {v}"))
    elif isinstance(v, (int, float, bool)) or v is None:
        print(f"{k}: {v}")
    elif isinstance(v, dict):
        print(f"{k}: dict keys={list(v)[:10]}")
    elif isinstance(v, list):
        print(f"{k}: list[{len(v)}]")

# hunt for anything URL-shaped across the doc
blob = json.dumps(d)
urls = re.findall(r"postgres(?:ql)?(?:\+\w+)?://[^\\\"']+", blob)
if urls:
    Path("render_dburl.txt").write_text(urls[0])
    print(f"FOUND {len(urls)} connection string(s) -> render_dburl.txt")
else:
    print("no inline connection string present")
