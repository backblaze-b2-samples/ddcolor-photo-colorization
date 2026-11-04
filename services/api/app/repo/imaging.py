"""Pillow helpers shared by ingest, inference and comparisons (core deps only).

Pillow is a core dependency, so everything here runs without the optional ML
stack: decoding scans (including 16-bit TIFFs), measuring colour saturation at
ingest, and encoding the colorized output.
"""

import io

from PIL import Image, ImageOps, ImageStat

# Mean HSV saturation (0-1) above which an ingested scan is treated as a colour
# photo. Neutral grayscale scans measure ~0; warm-toned sepia prints land around
# 0.05-0.15; ordinary colour photos sit well above 0.2.
COLOR_SATURATION_THRESHOLD = 0.18

_ENCODERS: dict[str, tuple[str, str, dict]] = {
    "jpeg": ("JPEG", "image/jpeg", {"quality": 92, "subsampling": 0}),
    "png": ("PNG", "image/png", {"optimize": True}),
    "webp": ("WEBP", "image/webp", {"quality": 90, "method": 4}),
}
_EXTENSIONS = {"jpeg": "jpg", "png": "png", "webp": "webp"}


class ImageDecodeError(ValueError):
    """The bytes are not an image Pillow can read."""


def open_image(data: bytes, max_pixels: int | None = None) -> Image.Image:
    """Decode bytes into an upright RGB image (EXIF orientation applied).

    16-bit and 32-bit grayscale TIFFs are scaled to 8 bits rather than clipped.
    Raises ImageDecodeError for unreadable data or more than `max_pixels` pixels.
    """
    try:
        img = Image.open(io.BytesIO(data))
        if max_pixels is not None and img.width * img.height > max_pixels:
            raise ImageDecodeError(
                f"{img.width}x{img.height} exceeds the {max_pixels:,}-pixel limit "
                "(MAX_PHOTO_PIXELS)"
            )
        img = ImageOps.exif_transpose(img)
        if img.mode in ("I;16", "I;16B", "I;16L", "I;16N"):
            img = img.point(lambda v: v * (1 / 256)).convert("L")
        elif img.mode in ("I", "F"):
            lo, hi = img.getextrema()
            scale = 255 / (hi - lo) if hi > lo else 0
            img = img.point(lambda v: (v - lo) * scale).convert("L")
        if img.mode in ("RGBA", "LA", "P", "PA"):
            img = img.convert("RGBA")
            background = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(background, img)
        return img.convert("RGB")
    except ImageDecodeError:
        raise
    except Exception as e:  # Pillow raises a broad family of errors
        raise ImageDecodeError(f"cannot decode image: {e}") from e


def mean_saturation(img: Image.Image) -> float:
    """Mean HSV saturation in [0, 1], measured on a small thumbnail."""
    thumb = img.copy()
    thumb.thumbnail((256, 256))
    saturation = thumb.convert("HSV").getchannel("S")
    return ImageStat.Stat(saturation).mean[0] / 255.0


def is_color(img: Image.Image) -> bool:
    return mean_saturation(img) > COLOR_SATURATION_THRESHOLD


def to_grayscale_rgb(img: Image.Image) -> Image.Image:
    """Desaturate to luminance, kept as 3-channel RGB (what DDColor expects)."""
    return img.convert("L").convert("RGB")


def encode(img: Image.Image, output_format: str) -> tuple[bytes, str]:
    """Encode `img` as jpeg | png | webp. Returns (bytes, content type)."""
    fmt, content_type, options = _ENCODERS[output_format]
    buf = io.BytesIO()
    img.save(buf, format=fmt, **options)
    return buf.getvalue(), content_type


def extension_for(output_format: str) -> str:
    return _EXTENSIONS[output_format]
