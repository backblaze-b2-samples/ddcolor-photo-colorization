"""Unit tests for upload object-key minting.

The API mints the object key from the declared filename at presign time; the
browser never chooses where its bytes land. B2 buckets are always versioned, so
re-uploading the same name just creates a new version — there is no duplicate
rejection.
"""

from app.service.upload import _validate_declared


def test_key_uses_original_filename():
    key = _validate_declared("scan.jpg", "image/jpeg", 5)
    assert key == "colorization/grayscale/scan.jpg"


def test_duplicate_filename_yields_same_key():
    # No dedup: two uploads of the same name resolve to the same key, and B2
    # versioning keeps both. Minting is deterministic, so the keys match.
    first = _validate_declared("scan.jpg", "image/jpeg", 5)
    second = _validate_declared("scan.jpg", "image/jpeg", 9)
    assert first == second == "colorization/grayscale/scan.jpg"


def test_key_is_sanitised():
    key = _validate_declared("../../etc/my scan.jpg", "image/jpeg", 5)
    assert key == "colorization/grayscale/my_scan.jpg"
