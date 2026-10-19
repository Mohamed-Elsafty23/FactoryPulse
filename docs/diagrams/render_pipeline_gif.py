#!/usr/bin/env python3
"""
Render pipeline_animated.html to GIF, WebM, or MP4 without screen recording.

Uses headless Chromium (Playwright) for frames, then ffmpeg.

Best visual quality: use .webm or .mp4 (full color, no 256-color GIF limit).
GIF is best only when the viewer requires GIF (e.g. some chat apps).

Requires: pip install playwright && playwright install chromium, and ffmpeg.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def infer_format(output: Path, explicit: str) -> str:
    if explicit != "auto":
        return explicit
    suf = output.suffix.lower()
    if suf == ".webm":
        return "webm"
    if suf in (".mp4", ".m4v"):
        return "mp4"
    return "gif"


def ffmpeg_encode_video(
    tmp_path: Path,
    out: Path,
    fps: float,
    scale_width: int,
    fmt: str,
    crf: int | None,
    lossless: bool,
) -> list[str]:
    """Build ffmpeg argv for WebM (VP9) or MP4 (H.264)."""
    # -2 rather than -1: keep the aspect ratio but round the derived height to
    # an even number. H.264 with yuv420p subsamples chroma 2x2 and refuses odd
    # dimensions ("height not divisible by 2"), which silently produced a
    # zero-byte .mp4. VP9 tolerates odd heights, so this only ever bit MP4.
    scale_vf = f"fps={fps},scale={scale_width}:-2:flags=lanczos+accurate_rnd+full_chroma_int"
    base = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(tmp_path / "frame_%05d.png"),
    ]
    if fmt == "webm":
        cmd = base + ["-vf", scale_vf, "-an"]
        if lossless:
            cmd += [
                "-c:v",
                "libvpx-vp9",
                "-lossless",
                "1",
                "-row-mt",
                "1",
            ]
        else:
            c = crf if crf is not None else 26
            cmd += [
                "-c:v",
                "libvpx-vp9",
                "-crf",
                str(c),
                "-b:v",
                "0",
                "-row-mt",
                "1",
                "-deadline",
                "good",
                "-cpu-used",
                "0",
            ]
        cmd.append(str(out))
        return cmd

    # mp4
    c = crf if crf is not None else 18
    vf = scale_vf + ",format=yuv420p"
    return base + [
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-crf",
        str(c),
        "-preset",
        "slow",
        "-movflags",
        "+faststart",
        "-an",
        str(out),
    ]


def ffmpeg_encode_gif(
    tmp_path: Path,
    out: Path,
    fps: float,
    scale_width: int,
    dither: str,
    fast_encode: bool,
) -> list[str]:
    stats = "single" if fast_encode else "full"
    if dither == "none":
        dither_opt = "dither=none"
    elif dither == "bayer":
        dither_opt = "dither=bayer:bayer_scale=5"
    else:
        dither_opt = "dither=floyd_steinberg"
    vf = (
        f"fps={fps},"
        f"scale={scale_width}:-1:flags=lanczos+accurate_rnd+full_chroma_int,"
        f"split[s0][s1];"
        f"[s0]palettegen=max_colors=256:reserve_transparent=0:stats_mode={stats}[p];"
        f"[s1][p]paletteuse={dither_opt}:diff_mode=rectangle"
    )
    return [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(tmp_path / "frame_%05d.png"),
        "-vf",
        vf,
        "-loop",
        "0",
        str(out),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render pipeline_animated.html to GIF / WebM / MP4 (Playwright + ffmpeg)."
    )
    here = Path(__file__).resolve().parent
    parser.add_argument(
        "--html",
        type=Path,
        default=here / "pipeline_animated.html",
        help="Path to pipeline_animated.html",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=here / "pipeline_animated.gif",
        help="Output path (.gif, .webm, or .mp4 — format is inferred from extension if --format auto)",
    )
    parser.add_argument(
        "--format",
        choices=("auto", "gif", "webm", "mp4"),
        default="auto",
        help="Output container (default: infer from -o suffix; else GIF)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=36.0,
        help=(
            "How long to capture (seconds). Default 36 ≈ one full 8-step loop in pipeline_animated.html "
            "(STEP_MS=4200, START_DELAY_MS=1000). Shorten for a clip, lengthen to repeat the loop."
        ),
    )
    parser.add_argument("--fps", type=float, default=8.0, help="Frames per second")
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=1680,
        help="Browser viewport width (diagram is 1620px wide)",
    )
    parser.add_argument(
        "--viewport-height",
        type=int,
        default=880,
        help="Browser viewport height",
    )
    parser.add_argument(
        "--scale-width",
        type=int,
        default=1620,
        help="Output width in pixels (height keeps aspect ratio). Use 1920 for extra sharpness.",
    )
    parser.add_argument(
        "--device-scale",
        type=float,
        default=2.0,
        help="Playwright DPR (2–3 recommended; higher = sharper capture, slower, heavier PNGs)",
    )
    parser.add_argument(
        "--dither",
        choices=("floyd_steinberg", "bayer", "none"),
        default="floyd_steinberg",
        help="GIF only: palette dithering",
    )
    parser.add_argument(
        "--fast-encode",
        action="store_true",
        help="GIF only: faster encode, slightly worse colors",
    )
    parser.add_argument(
        "--video-crf",
        type=int,
        default=None,
        help="WebM/MP4 only: quality (lower = better/larger). Defaults: VP9≈26, H.264≈18",
    )
    parser.add_argument(
        "--lossless-webm",
        action="store_true",
        help="WebM only: lossless VP9 (largest files, pixel-perfect vs PNG frames)",
    )
    args = parser.parse_args()

    html = args.html.resolve()
    if not html.is_file():
        print(f"Not found: {html}", file=sys.stderr)
        return 1

    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found. Install it (e.g. sudo apt install ffmpeg).", file=sys.stderr)
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install Playwright: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    out = args.output.resolve()
    fmt = infer_format(out, args.format)
    if args.lossless_webm and fmt != "webm":
        print("--lossless-webm only applies to WebM; use -o out.webm", file=sys.stderr)
        return 1

    url = html.as_uri()
    interval_s = 1.0 / args.fps
    n_frames = max(1, int(args.duration * args.fps))

    with tempfile.TemporaryDirectory(prefix="pipeline_gif_") as tmp:
        tmp_path = Path(tmp)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": args.viewport_width, "height": args.viewport_height},
                device_scale_factor=args.device_scale,
            )
            page.goto(url, wait_until="load", timeout=60_000)
            page.wait_for_timeout(500)

            for i in range(n_frames):
                frame_path = tmp_path / f"frame_{i:05d}.png"
                page.screenshot(path=str(frame_path), type="png")
                page.wait_for_timeout(int(interval_s * 1000))

            browser.close()

        out.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "gif":
            cmd = ffmpeg_encode_gif(
                tmp_path,
                out,
                args.fps,
                args.scale_width,
                args.dither,
                args.fast_encode,
            )
        else:
            cmd = ffmpeg_encode_video(
                tmp_path,
                out,
                args.fps,
                args.scale_width,
                fmt,
                args.video_crf,
                args.lossless_webm,
            )

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr or r.stdout, file=sys.stderr)
            if fmt == "webm" and "libvpx-vp9" in (r.stderr or ""):
                print(
                    "Hint: install libvpx for VP9 (e.g. sudo apt install ffmpeg — full build).",
                    file=sys.stderr,
                )
            return r.returncode

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
