import os
import re
import gzip
import time
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- Settings ---------------------------------------------------------
SRC = "https://github.com/ferteque/Curated-M3U-Repository/raw/refs/heads/main/epg52.xml.gz"
OLD_PREFIX = "monepg."
NEW_PREFIX = "jutterbox."
TTL = 6 * 3600  # refresh every 6 hours
# -----------------------------------------------------------------------

cache = {"t": 0, "data": b""}
lock = threading.Lock()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def transform(xml):
    """Rename channel IDs: monepg.<group>.<number> -> jutterbox.<group>.<channel-name>."""
    mapping = {}
    used = set()

    for m in re.finditer(
        r'<channel id="([^"]+)">\s*<display-name[^>]*>([^<]+)</display-name>', xml
    ):
        old, name = m.group(1), m.group(2)
        if not old.startswith(OLD_PREFIX):
            continue
        base = re.sub(r"\.\d+$", "", old[len(OLD_PREFIX):])
        new = f"{NEW_PREFIX}{base}.{slug(name)}"
        candidate, i = new, 2
        while candidate in used:
            candidate = f"{new}-{i}"
            i += 1
        used.add(candidate)
        mapping[old] = candidate

    return re.sub(
        r'\b(id|channel)="([^"]+)"',
        lambda m: f'{m.group(1)}="{mapping.get(m.group(2), m.group(2))}"',
        xml,
    )


def refresh():
    req = urllib.request.Request(SRC, headers={"User-Agent": "epg-proxy"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    xml = gzip.decompress(raw).decode("utf-8")
    cache["data"] = gzip.compress(transform(xml).encode("utf-8"))
    cache["t"] = time.time()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/epg.xml.gz"):
            with lock:
                if time.time() - cache["t"] > TTL:
                    try:
                        refresh()
                    except Exception:
                        if not cache["data"]:
                            self.send_response(502)
                            self.end_headers()
                            self.wfile.write(b"Could not fetch source EPG")
                            return
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.send_header("Content-Length", str(len(cache["data"])))
            self.end_headers()
            self.wfile.write(cache["data"])
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"EPG proxy running. Use /epg.xml.gz")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
