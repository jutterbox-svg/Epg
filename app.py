import re
import gzip
import time
import threading
import requests
from flask import Flask, Response

# ---- Settings ---------------------------------------------------------
SRC = "https://github.com/ferteque/Curated-M3U-Repository/raw/refs/heads/main/epg52.xml.gz"
OLD_PREFIX = "monepg."
NEW_PREFIX = "jutterbox."
TTL = 6 * 3600  # refresh every 6 hours
# -----------------------------------------------------------------------

app = Flask(__name__)
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
        base = re.sub(r"\.\d+$", "", old[len(OLD_PREFIX):])  # drop trailing number
        new = f"{NEW_PREFIX}{base}.{slug(name)}"
        # avoid duplicate IDs if two channels share a name
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
    r = requests.get(SRC, timeout=120)
    r.raise_for_status()
    xml = gzip.decompress(r.content).decode("utf-8")
    cache["data"] = gzip.compress(transform(xml).encode("utf-8"))
    cache["t"] = time.time()


@app.route("/")
def home():
    return "EPG proxy running. Use /epg.xml.gz"


@app.route("/epg.xml.gz")
def epg():
    with lock:
        if time.time() - cache["t"] > TTL:
            try:
                refresh()
            except Exception:
                if not cache["data"]:
                    raise  # nothing cached yet, so surface the error
    return Response(cache["data"], mimetype="application/gzip")


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
