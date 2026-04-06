"""ai_analyzer モジュールのテスト（API呼び出しを伴わないユニットテスト）"""

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ai_analyzer import (
    _parse_json_response,
    _encode_image,
    parse_batch_results_for_product,
    register_rate_limit_callback,
    _notify_rate_limit,
    _rate_limit_callbacks,
)


class TestParseJsonResponse:
    """_parse_json_response のテスト"""

    def test_plain_json(self):
        text = '{"brand_en": "SEIKO", "model_number": "SARX055"}'
        result = _parse_json_response(text)
        assert result["brand_en"] == "SEIKO"
        assert result["model_number"] == "SARX055"

    def test_json_in_code_block(self):
        """```json ... ``` ブロックを除去してパース"""
        text = '```json\n{"brand_en": "OMEGA"}\n```'
        result = _parse_json_response(text)
        assert result["brand_en"] == "OMEGA"

    def test_json_with_generic_code_block(self):
        """``` ... ``` (langなし) でも対応"""
        text = '```\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result["key"] == "value"

    def test_json_with_whitespace(self):
        text = '  \n  {"key": "value"}  \n  '
        result = _parse_json_response(text)
        assert result["key"] == "value"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json")

    def test_nested_json(self):
        text = '{"confidence": {"brand": 0.95, "model": 0.8}}'
        result = _parse_json_response(text)
        assert result["confidence"]["brand"] == 0.95


class TestEncodeImage:
    """_encode_image のテスト"""

    def test_jpg_encoding(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0test_image_data")

        data, media_type = _encode_image(img)
        assert media_type == "image/jpeg"
        decoded = base64.standard_b64decode(data)
        assert decoded == b"\xff\xd8\xff\xe0test_image_data"

    def test_png_encoding(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"png_data")

        data, media_type = _encode_image(img)
        assert media_type == "image/png"

    def test_heic_encoding(self, tmp_path):
        img = tmp_path / "test.heic"
        img.write_bytes(b"heic_data")

        _, media_type = _encode_image(img)
        assert media_type == "image/heic"

    def test_unknown_extension_defaults_jpeg(self, tmp_path):
        img = tmp_path / "test.xyz"
        img.write_bytes(b"data")

        _, media_type = _encode_image(img)
        assert media_type == "image/jpeg"


class TestParseBatchResultsForProduct:
    """parse_batch_results_for_product のテスト"""

    def test_full_results(self):
        batch_results = {
            "prod1__front": {"brand_en": "SEIKO", "gender": "メンズ"},
            "prod1__back": {"model_number": "SARX055", "material": "ステンレス"},
            "prod1__comment1": {"title_prefix": "【中古】", "abnormality_text": "キズあり", "abnormality_type": "傷"},
        }
        front, back, comment = parse_batch_results_for_product("prod1", batch_results)
        assert front["brand_en"] == "SEIKO"
        assert back["model_number"] == "SARX055"
        assert comment["title_prefix"] == "【中古】"
        assert comment["abnormality_text"] == "キズあり"

    def test_missing_front(self):
        batch_results = {
            "prod1__back": {"model_number": "SARX055"},
        }
        front, back, comment = parse_batch_results_for_product("prod1", batch_results)
        assert front == {}
        assert back["model_number"] == "SARX055"

    def test_two_comments_combined(self):
        batch_results = {
            "prod1__comment1": {"abnormality_text": "キズあり", "abnormality_type": "傷"},
            "prod1__comment2": {"abnormality_text": "電池切れ", "abnormality_type": "電池"},
        }
        _, _, comment = parse_batch_results_for_product("prod1", batch_results)
        assert "キズあり" in comment["abnormality_text"]
        assert "電池切れ" in comment["abnormality_text"]
        assert " / " in comment["abnormality_text"]
        assert "傷" in comment["abnormality_type"]
        assert "電池" in comment["abnormality_type"]

    def test_no_comments(self):
        batch_results = {
            "prod1__front": {"brand_en": "SEIKO"},
        }
        _, _, comment = parse_batch_results_for_product("prod1", batch_results)
        assert comment["title_prefix"] == ""
        assert comment["abnormality_text"] == ""

    def test_title_prefix_from_later_comment(self):
        """後のコメントの title_prefix が優先"""
        batch_results = {
            "prod1__comment1": {"title_prefix": "【ジャンク】"},
            "prod1__comment2": {"title_prefix": "【中古】"},
        }
        _, _, comment = parse_batch_results_for_product("prod1", batch_results)
        assert comment["title_prefix"] == "【中古】"

    def test_nonexistent_product(self):
        batch_results = {"other__front": {"brand_en": "SEIKO"}}
        front, back, comment = parse_batch_results_for_product("prod1", batch_results)
        assert front == {}
        assert back == {}
        assert comment["abnormality_text"] == ""


class TestRateLimitCallback:
    """レートリミットコールバック登録・通知のテスト"""

    def test_callback_called(self):
        events = []

        def cb(event_type, detail):
            events.append((event_type, detail))

        # コールバック登録
        register_rate_limit_callback(cb)

        try:
            _notify_rate_limit("rate_limit_hit", {"attempt": 1, "delay": 5})
            assert len(events) >= 1
            last = events[-1]
            assert last[0] == "rate_limit_hit"
            assert last[1]["attempt"] == 1
        finally:
            # テスト後にコールバックを除去（グローバルステートの汚染防止）
            _rate_limit_callbacks.remove(cb)

    def test_callback_exception_ignored(self):
        """コールバックが例外を投げても他に影響しない"""
        def bad_cb(event_type, detail):
            raise RuntimeError("test error")

        register_rate_limit_callback(bad_cb)
        try:
            # 例外が伝播しないことを確認
            _notify_rate_limit("test_event", {})
        finally:
            _rate_limit_callbacks.remove(bad_cb)
