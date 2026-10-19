#!/usr/bin/env python3
"""Capture the static architecture diagram from the SAME HTML as the animation.

Rendering both from one source means the still and the walkthrough cannot drift
apart: change the HTML, re-run both, and they agree by construction.

The capture waits past the animation's lead-in and lands on a frame with every
zone in its resting state, then clears the step HUD so the still does not look
like a paused video.

    python render_static.py            # -> pipeline_architecture.png + .svg
"""

from __future__ import annotations

import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", default=str(HERE / "pipeline_animated.html"))
    parser.add_argument("--out", default=str(HERE / "pipeline_architecture.png"))
    parser.add_argument("--scale", type=int, default=2, help="device pixel ratio")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("pip install playwright && playwright install chromium") from None

    out = Path(args.out)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1660, "height": 880}, device_scale_factor=args.scale
        )
        page.goto(Path(args.html).resolve().as_uri())
        # Past the 1s lead-in and the first tick: clearing before it fires would
        # just be undone, re-lighting step 1's nodes in the "static" diagram.
        page.wait_for_timeout(1500)

        # A still should show the architecture, not a frozen animation frame:
        # stop the loop, drop the per-step highlighting, the step counter and
        # the progress bar, then trim the canvas to the content.
        page.evaluate("""() => {
            // The interval id is not exposed, so clear the whole timer range.
            const last = setInterval(() => {}, 1e6);
            for (let i = 0; i <= last; i++) { clearInterval(i); clearTimeout(i); }

            document.querySelectorAll('.tool.lit,.zone.lit')
                    .forEach(e => e.classList.remove('lit'));
            document.querySelectorAll('.glow.on')
                    .forEach(e => e.classList.remove('on'));
            // Set as an inline style by tick(), so a class reset misses it.
            const tf = document.getElementById('p-tf');
            if (tf) tf.style.borderColor = 'var(--grid)';

            const hud = document.querySelector('.hud');
            if (hud) hud.style.display = 'none';
            const bar = document.getElementById('pbar');
            if (bar) bar.style.width = '0%';

            // The animation canvas leaves room the still does not need.
            const d = document.getElementById('D');
            if (d) d.style.height = '620px';
        }""")
        page.wait_for_timeout(250)

        diagram = page.locator(".diagram")
        diagram.screenshot(path=str(out))

        # An SVG wrapper keeps the asset scalable in the README without
        # re-rasterising; the PNG is embedded so it stays a single file.
        import base64

        box = diagram.bounding_box()
        data = base64.b64encode(out.read_bytes()).decode()
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{int(box["width"])}" height="{int(box["height"])}" '
            f'viewBox="0 0 {int(box["width"])} {int(box["height"])}">'
            f'<image width="{int(box["width"])}" height="{int(box["height"])}" '
            f'xlink:href="data:image/png;base64,{data}"/></svg>'
        )
        out.with_suffix(".svg").write_text(svg)
        browser.close()

    print(out)
    print(out.with_suffix(".svg"))


if __name__ == "__main__":
    main()
