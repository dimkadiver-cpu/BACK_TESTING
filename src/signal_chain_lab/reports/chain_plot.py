"""Chain plot utilities for equity curve and event annotations."""
from __future__ import annotations

import html
import struct
import zlib
from datetime import datetime
from pathlib import Path

from src.signal_chain_lab.domain.results import EventLogEntry


def _realized_pnl(entry: EventLogEntry) -> float | None:
    value = entry.state_after.get("realized_pnl")
    if isinstance(value, int | float):
        return float(value)
    return None


def build_equity_curve(entries: list[EventLogEntry]) -> list[tuple[datetime, float]]:
    """Build an equity curve from event log snapshots."""
    points: list[tuple[datetime, float]] = []
    current = 0.0
    for entry in sorted(entries, key=lambda item: item.timestamp):
        pnl = _realized_pnl(entry)
        if pnl is not None:
            current = pnl
        points.append((entry.timestamp, current))
    return points


def _draw_line_chart(points: list[tuple[datetime, float]], width: int = 960, height: int = 480) -> bytes:
    if not points:
        points = [(datetime(1970, 1, 1), 0.0)]

    padding = 30
    values = [point[1] for point in points]
    min_y = min(values)
    max_y = max(values)
    span_y = (max_y - min_y) or 1.0

    canvas = bytearray([255] * (width * height * 3))

    def set_px(x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if x < 0 or x >= width or y < 0 or y >= height:
            return
        idx = (y * width + x) * 3
        canvas[idx : idx + 3] = bytes(rgb)

    def map_point(index: int, value: float) -> tuple[int, int]:
        x = padding + int((index / max(len(points) - 1, 1)) * (width - (2 * padding)))
        y_ratio = (value - min_y) / span_y
        y = height - padding - int(y_ratio * (height - (2 * padding)))
        return x, y

    # Axes
    for x in range(padding, width - padding):
        set_px(x, height - padding, (180, 180, 180))
    for y in range(padding, height - padding):
        set_px(padding, y, (180, 180, 180))

    # Bresenham line for equity
    coords = [map_point(index, value) for index, (_, value) in enumerate(points)]
    for i in range(1, len(coords)):
        x0, y0 = coords[i - 1]
        x1, y1 = coords[i]
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            set_px(x0, y0, (34, 139, 230))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    # Annotate points as red squares
    for x, y in coords:
        for ox in range(-2, 3):
            for oy in range(-2, 3):
                set_px(x + ox, y + oy, (214, 39, 40))

    raw = bytearray()
    row_bytes = width * 3
    for row in range(height):
        raw.append(0)
        start = row * row_bytes
        raw.extend(canvas[start : start + row_bytes])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def write_chain_plot_png(entries: list[EventLogEntry], output_path: str | Path) -> Path:
    curve = build_equity_curve(entries)
    png_bytes = _draw_line_chart(curve)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)
    return path


def write_chain_plot_html(entries: list[EventLogEntry], output_path: str | Path, title: str = "Chain equity") -> Path:
    points = build_equity_curve(entries)
    if not points:
        polyline = ""
    else:
        values = [value for _, value in points]
        min_y = min(values)
        max_y = max(values)
        span_y = (max_y - min_y) or 1.0
        coords = []
        for index, (_, value) in enumerate(points):
            x = 50 + int((index / max(len(points) - 1, 1)) * 850)
            y = 430 - int(((value - min_y) / span_y) * 360)
            coords.append(f"{x},{y}")
        polyline = " ".join(coords)

    body = f"""<!DOCTYPE html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>{html.escape(title)}</title></head>
<body>
<h1>{html.escape(title)}</h1>
<svg width=\"960\" height=\"480\" xmlns=\"http://www.w3.org/2000/svg\">
  <line x1=\"50\" y1=\"430\" x2=\"910\" y2=\"430\" stroke=\"#999\" />
  <line x1=\"50\" y1=\"20\" x2=\"50\" y2=\"430\" stroke=\"#999\" />
  <polyline points=\"{polyline}\" fill=\"none\" stroke=\"#228be6\" stroke-width=\"2\" />
</svg>
</body>
</html>
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
