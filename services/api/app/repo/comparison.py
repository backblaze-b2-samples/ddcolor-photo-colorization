"""Side-by-side comparison composite: original | colorized, with a caption strip."""

import io

from PIL import Image, ImageDraw, ImageFont

# Each panel is scaled to this height (never upscaled), so a comparison stays a
# light review asset even for a 50-megapixel scan.
PANEL_MAX_HEIGHT = 1024
CAPTION_HEIGHT = 36
GUTTER = 8
_BACKGROUND = (24, 24, 27)
_TEXT = (244, 244, 245)


def _panel(img: Image.Image, height: int) -> Image.Image:
    if img.height == height:
        return img
    width = max(1, round(img.width * height / img.height))
    return img.resize((width, height), Image.Resampling.LANCZOS)


def build_comparison(original: Image.Image, colorized: Image.Image, caption: str) -> bytes:
    """Compose original (left) and colorized (right) above a caption. Returns JPEG bytes."""
    height = min(PANEL_MAX_HEIGHT, original.height, colorized.height)
    left = _panel(original.convert("RGB"), height)
    right = _panel(colorized.convert("RGB"), height)
    width = left.width + GUTTER + right.width
    canvas = Image.new("RGB", (width, height + CAPTION_HEIGHT), _BACKGROUND)
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + GUTTER, 0))

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=16)
    baseline = height + (CAPTION_HEIGHT - 16) // 2
    draw.text((10, baseline), "Original", fill=_TEXT, font=font)
    draw.text((left.width + GUTTER + 10, baseline), caption, fill=_TEXT, font=font)

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=88)
    return buf.getvalue()
