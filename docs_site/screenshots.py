"""Screenshots of the Studio's Results page for the docs: one PNG per panel.

Starts the Studio headless on its own port, ticks the runs of one experiment, opens
each tab and saves every card (``section``) it shows into
``docs/using/studio/results/img/<tab>-<card>.png``. Run it again after a Studio change and
the docs' pictures follow:

    python docs_site/screenshots.py
    python docs_site/screenshots.py --runs results_format-moreUpd

Needs Playwright and its Chromium in the environment (``pip install playwright``,
then ``python -m playwright install chromium``). The runs must be on this PC: a
cluster's runs once synced.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/using/studio/results/img"
PORT = 8097
# The tabs, and the panels some tabs switch between.
TABS = {"Validation": [None], "Learning": ["Evaluation", "Timing"], "Market": [None],
        "Grid": [None]}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def wait_for_port(port: int, seconds: int = 120) -> None:
    for _ in range(seconds):
        try:
            socket.create_connection(("127.0.0.1", port), 1).close()
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"The Studio did not start on port {port}")


def cards(page: Page, prefix: str) -> list[str]:
    """Save every visible card of the open tab; return the files written."""
    saved = []

    for card in page.locator(".mls-card").all():
        if not card.is_visible():
            continue
        title = card.locator(".mls-card-title").first
        name = title.inner_text().strip() if title.count() else ""
        if not name:
            continue
        card.scroll_into_view_if_needed()
        page.mouse.move(0, 0)  # no chart toolbar or hover label
        page.wait_for_timeout(800)  # let a chart finish drawing
        path = OUT / f"{prefix}-{slug(name)}.png"
        card.screenshot(path=str(path))
        saved.append(path.name)

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", default="results_format-moreUpd",
                        help="the filter that picks the runs to tick")
    parser.add_argument("--wait", type=int, default=12, help="seconds per tab")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ, MARLEM_STUDIO_PORT=str(PORT), MARLEM_STUDIO_SHOW="0",
               PYTHONIOENCODING="utf-8")
    studio = subprocess.Popen([sys.executable, "-m", "studio.app"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_port(PORT)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.goto(f"http://127.0.0.1:{PORT}/results")
            page.wait_for_timeout(4000)
            # The header is fixed: it would cover the top of a tall panel.
            page.add_style_tag(content=".q-header { display: none !important; }")
            page.get_by_placeholder("Filter runs").fill(args.runs)
            page.wait_for_timeout(1500)
            page.get_by_role("button", name="Tick shown").click()
            page.wait_for_timeout(args.wait * 1000)
            page.screenshot(path=str(OUT / "page.png"))

            for tab, panels in TABS.items():
                page.get_by_role("tab", name=tab).first.click()
                page.wait_for_timeout(args.wait * 1000)

                for panel in panels:
                    if panel:
                        page.get_by_role("tab", name=panel).first.click()
                        page.wait_for_timeout(args.wait * 1000)
                    prefix = slug(tab if not panel else f"{tab} {panel}")
                    print(prefix, cards(page, prefix))

            browser.close()
    finally:
        studio.terminate()


if __name__ == "__main__":
    main()
