"""Test keyset pagination utilities."""

from app.utils.pagination import KeysetPage, decode_cursor, encode_cursor


def test_encode_decode_roundtrip():
    original = {"v": "2026-01-15T10:30:00", "id": "abc-123"}
    encoded = encode_cursor(original)
    decoded = decode_cursor(encoded)
    assert decoded == original


def test_decode_invalid_cursor():
    assert decode_cursor("not-valid-base64!!!") == {}


def test_keyset_page_model():
    page = KeysetPage(next_cursor="abc", has_more=True, count=50)
    assert page.has_more is True
    assert page.count == 50
