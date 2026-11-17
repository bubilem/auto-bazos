"""Numbered photo collage for pasting into a web LLM chat as ONE image.

Each cell is labelled [1], [2], ... with the same numbering as the downloaded files
(images/01.jpg -> [1]), so the LLM can reference photos and the user can find the original.
Numbering continues across collages: collage_2 starts at [7] when collage_1 holds 6 photos.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

COLS = 3
CELL = (640, 480)
GAP = 6
BG = (24, 24, 24)
JPEG_QUALITY = 85

_FONT_CANDIDATES = ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc")


def _font(size):
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)  # Pillow >= 10.1


def _load(path):
    """Open an image upright and RGB, or None if unreadable."""
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return im.convert("RGB")
    except Exception:
        return None


def _draw_label(draw, xy, number, font):
    text = f"[{number}]"
    x, y = xy
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad = 10
    w, h = right - left, bottom - top
    draw.rounded_rectangle((x, y, x + w + 2 * pad, y + h + 2 * pad), radius=10, fill=(0, 0, 0))
    draw.text((x + pad - left, y + pad - top), text, font=font, fill=(255, 255, 255))


def make_collage(image_paths, out_path, start_number=1):
    """Build one collage (max 6 photos recommended) and return the output path.

    Unreadable files keep their number and show a placeholder, so numbering never shifts.
    """
    paths = list(image_paths)
    if not paths:
        raise ValueError("no images for collage")
    cols = min(COLS, len(paths))
    rows = math.ceil(len(paths) / cols)
    cw, ch = CELL
    canvas = Image.new("RGB", (cols * cw + (cols + 1) * GAP, rows * ch + (rows + 1) * GAP), BG)
    draw = ImageDraw.Draw(canvas)
    big, small = _font(72), _font(32)

    for i, p in enumerate(paths):
        x = GAP + (i % cols) * (cw + GAP)
        y = GAP + (i // cols) * (ch + GAP)
        im = _load(p)
        if im is None:
            draw.rectangle((x, y, x + cw, y + ch), fill=(60, 60, 60))
            draw.text((x + cw // 2, y + ch // 2), "foto nelze načíst", font=small, fill=(200, 200, 200), anchor="mm")
        else:
            canvas.paste(ImageOps.fit(im, CELL, method=Image.LANCZOS), (x, y))
        _draw_label(draw, (x + 12, y + 12), start_number + i, big)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out


def make_collages(image_paths, folder, per_collage=6, max_collages=2):
    """Split photos into collages of `per_collage`; write collage_1.jpg, collage_2.jpg, ...

    Returns the list of file names (relative to `folder`).
    """
    paths = list(image_paths)[: per_collage * max_collages]
    names = []
    for n, start in enumerate(range(0, len(paths), per_collage), start=1):
        name = f"collage_{n}.jpg"
        make_collage(paths[start:start + per_collage], Path(folder) / name, start_number=start + 1)
        names.append(name)
    return names
