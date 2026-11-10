#!/usr/bin/env python3
"""
Build dist/ for local use (file://) and Cloudflare: wraps web/index.html (a page
fragment, as published to the artifact) in a full HTML document and copies the
data and the style kit next to it. Deploy dist/ as static files.
"""
import shutil
from pathlib import Path

WEB, DIST = Path("web"), Path("dist")
if DIST.exists():
    shutil.rmtree(DIST)
DIST.mkdir()
body = (WEB / "index.html").read_text(encoding="utf-8")
head_end = body.index("</style>") + len("</style>")
page = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        + body[:head_end] + "\n</head>\n<body>\n" + body[head_end:] + "\n</body>\n</html>\n")
(DIST / "index.html").write_text(page, encoding="utf-8")
for f in ["data.js", "places.js"]:
    shutil.copy(WEB / f, DIST / f)
shutil.copytree(WEB / "jf-dataviz", DIST / "jf-dataviz")
size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
print(f"dist/: {len(list(DIST.rglob('*.*')))} files, {size // 1024} KB")
