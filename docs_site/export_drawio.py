"""Export the draw.io diagrams under docs/ to SVG, for the website and GitHub.

    python docs_site/export_drawio.py [file.drawio ...]

Each page (tab) of a ``.drawio`` file becomes ``<page id>.svg`` next to it; the
Markdown pages include the SVG. The ``.drawio`` file is the source: edit it (e.g.
with the Draw.io Integration extension in VS Code), then run this again.

draw.io's own viewer draws the page and headless Edge (or Chrome) hands back the
SVG. The viewer script is downloaded once from viewer.diagrams.net into .cache/ and
runs locally; the diagrams are not sent anywhere. The first run needs internet.
"""

import functools
import html
import http.server
import json
import re
import subprocess
import sys
import threading
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
CACHE = HERE / ".cache"
VIEWER_URL = "https://viewer.diagrams.net/js/viewer-static.min.js"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]

# The viewer draws the page; the SVG is then serialised as XML (so the HTML labels
# keep their XHTML namespace) into a textarea, which --dump-dom prints.
PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="g" class="mxgraph" style="max-width:none" data-mxgraph="{config}"></div>
<textarea id="out"></textarea>
<script src="/viewer-static.min.js"></script>
<script>
var viewer = null;
GraphViewer.createViewerForElement(document.getElementById('g'), function (v) {{ viewer = v; }});
var tries = 0;
function grab() {{
  var s = document.querySelector('#g svg');
  if ((!s || !viewer) && tries++ < 40) {{ setTimeout(grab, 500); return; }}
  var b = viewer.graph.getGraphBounds(), m = 10;
  var w = Math.ceil(b.width + 2 * m), h = Math.ceil(b.height + 2 * m);
  s.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  s.setAttribute('viewBox', [b.x - m, b.y - m, w, h].join(' '));
  s.setAttribute('width', w);
  s.setAttribute('height', h);
  s.setAttribute('style', 'background-color: #ffffff; color-scheme: light;');
  document.getElementById('out').textContent = new XMLSerializer().serializeToString(s);
}}
setTimeout(grab, 1000);
</script></body></html>"""


def find_browser() -> str:
    for path in BROWSERS:
        if Path(path).exists():
            return path
    sys.exit("No Edge or Chrome found; edit BROWSERS in export_drawio.py")


def ensure_viewer() -> None:
    CACHE.mkdir(exist_ok=True)
    (CACHE / ".gitignore").write_text("*\n")
    target = CACHE / "viewer-static.min.js"
    if not target.exists():
        print("downloading the draw.io viewer (once) ...")
        request = urllib.request.Request(VIEWER_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())


def serve() -> http.server.ThreadingHTTPServer:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(CACHE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def export_page(browser: str, port: int, diagram: ET.Element, folder: Path) -> None:
    slug = diagram.get("id")
    single = "<mxfile>" + ET.tostring(diagram, encoding="unicode") + "</mxfile>"
    config = {"xml": single, "toolbar": "", "nav": False, "lightbox": False}
    page = PAGE.format(config=html.escape(json.dumps(config), quote=True))
    work = CACHE / f"_{slug}.html"
    work.write_text(page, encoding="utf-8")
    try:
        dom = subprocess.run(
            [browser, "--headless", "--disable-gpu", "--window-size=2000,2400",
             "--virtual-time-budget=30000", "--dump-dom",
             f"http://127.0.0.1:{port}/{work.name}"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout
    finally:
        work.unlink(missing_ok=True)
    found = re.search(r'<textarea id="out">(.*?)</textarea>', dom, re.S)
    text = html.unescape(found.group(1)) if found else ""
    if not text.startswith("<svg"):
        sys.exit(f"{diagram.get('name')}: the viewer drew nothing")
    svg = folder / f"{slug}.svg"
    svg.write_text(text, encoding="utf-8")
    print(f"  {diagram.get('name')}  ->  {svg.relative_to(DOCS)}")


def main() -> None:
    files = [Path(a).resolve() for a in sys.argv[1:]] or sorted(DOCS.rglob("*.drawio"))
    browser = find_browser()
    ensure_viewer()
    server = serve()
    try:
        for path in files:
            print(path.relative_to(DOCS))
            for diagram in ET.parse(path).getroot().findall("diagram"):
                export_page(browser, server.server_address[1], diagram, path.parent)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
