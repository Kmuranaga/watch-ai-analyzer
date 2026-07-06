"""針数クロップ・アンサンブル（過剰検出抑制）のテスト"""

import sys
from pathlib import Path
from pathlib import Path as _P

sys.path.insert(0, str(Path(__file__).parent.parent))

import modules.ai_analyzer as ai
import modules.image_preprocess as ip
from modules.normalizer import (
    fewest_hand_count, should_run_hand_count_pass, apply_hand_count_override,
)


# === image_preprocess ===

def test_crop_dial_center_and_bytes(tmp_path):
    from PIL import Image
    p = tmp_path / "img.jpg"
    Image.new("RGB", (800, 600), (255, 255, 255)).save(p)
    out = ip.crop_dial_center(p, frac=0.5, size=256)
    assert out.size == (256, 256)
    b = ip.crop_dial_to_bytes(p, frac=0.5, size=256)
    assert isinstance(b, bytes) and len(b) > 0


# === normalizer: fewest_hand_count ===

def test_fewest_hand_count():
    assert fewest_hand_count(["3針", "2針"]) == "2針"        # 少ない方
    assert fewest_hand_count(["3針", "3針"]) == "3針"
    assert fewest_hand_count(["クロノグラフ", "3針"]) == "3針"  # クロノより3針が少ない
    assert fewest_hand_count(["", "2針"]) == "2針"           # 空は無視
    assert fewest_hand_count(["", ""]) == ""


# === normalizer: should_run / apply_override ===

def test_should_run_skips_digital():
    assert should_run_hand_count_pass("デジタル") is False
    assert should_run_hand_count_pass("digital") is False


def test_should_run_for_analog_and_empty():
    assert should_run_hand_count_pass("3針") is True
    assert should_run_hand_count_pass("2針") is True
    assert should_run_hand_count_pass("") is True


def test_override_replaces_analog_and_is_nondestructive():
    merged = {"hand_count": "3針", "brand_en": "SEIKO"}
    out = apply_hand_count_override(merged, {"hand_count": "2針"})
    assert out["hand_count"] == "2針"
    assert out["brand_en"] == "SEIKO"
    assert merged["hand_count"] == "3針"


def test_override_skips_digital_and_empty():
    assert apply_hand_count_override({"hand_count": "デジタル"}, {"hand_count": "2針"})["hand_count"] == "デジタル"
    assert apply_hand_count_override({"hand_count": "2針"}, {})["hand_count"] == "2針"
    assert apply_hand_count_override({"hand_count": "2針"}, {"hand_count": ""})["hand_count"] == "2針"


def test_override_rejects_nonhand_result():
    # クロップに部分LCD等が写り専用パスが「デジタル」を返しても、
    # アナログ(3針)を誤って デジタル に下げない（既知の針数のみ採用）
    assert apply_hand_count_override({"hand_count": "3針"}, {"hand_count": "デジタル"})["hand_count"] == "3針"
    assert apply_hand_count_override({"hand_count": "3針"}, {"hand_count": "なし"})["hand_count"] == "3針"


# === ai_analyzer: analyze_hand_count_cropped ===

def test_analyze_hand_count_cropped_takes_fewest(monkeypatch):
    monkeypatch.setattr(ip, "crop_dial_to_bytes", lambda p, frac, size=1024: b"x")
    seq = iter([{"hand_count": "3針"}, {"hand_count": "2針"}])
    monkeypatch.setattr(ai, "_call_api_bytes",
                        lambda prompt, b, mime_type="image/jpeg", label="": next(seq))
    # フラクションは明示し、デフォルト個数に依存しないようにする
    out = ai.analyze_hand_count_cropped(_P("front.jpg"), fracs=(0.55, 0.50))
    assert out["hand_count"] == "2針"
    assert len(out["per_crop"]) == 2


def test_default_crop_fracs_has_multiple():
    # 過剰検出の揺れに対応するため複数倍率を使う
    assert len(ai.HAND_COUNT_CROP_FRACS) >= 3


# === ai_analyzer: batch ===

def test_create_batch_requests_excludes_cropped_hand(monkeypatch):
    # 針数コメント対応により、AI針数パイプライン（クロップ・アンサンブル）は
    # パイプラインから撤去された（コスト削減）。クロップ要求が生成されないことを検証。
    calls = []
    monkeypatch.setattr(ai, "_build_batch_request",
                        lambda cid, *a, **k: (calls.append(cid), {"metadata": {"custom_id": cid}})[1])
    monkeypatch.setattr(ai, "_build_batch_request_bytes",
                        lambda cid, *a, **k: (calls.append(cid), {"metadata": {"custom_id": cid}})[1])

    class FakeProduct:
        product_id = "P1"
        front_image = _P("f.jpg")
        diagonal_image = None
        back_cover_image = None
        comment_images = []

    ai.create_batch_requests([FakeProduct()])
    assert "P1__front" in calls
    assert not any("hand_c" in c for c in calls)


def test_parse_hand_count_result_fewest():
    from modules.ai_analyzer import parse_hand_count_result_for_product
    res = {"P1__hand_c0": {"hand_count": "3針"}, "P1__hand_c1": {"hand_count": "2針"}}
    assert parse_hand_count_result_for_product("P1", res)["hand_count"] == "2針"
    assert parse_hand_count_result_for_product("P2", res) == {}
