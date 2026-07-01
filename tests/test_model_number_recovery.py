"""型番リカバリ（空欄時の裏蓋拡大リトライ＋多数決）のテスト"""

import sys
from pathlib import Path
from pathlib import Path as _P

sys.path.insert(0, str(Path(__file__).parent.parent))

import modules.ai_analyzer as ai
import modules.image_preprocess as ip
from modules.normalizer import majority_nonempty


# === image_preprocess.upscale_to_bytes ===

def test_upscale_to_bytes_doubles(tmp_path):
    from PIL import Image
    import io
    p = tmp_path / "b.jpg"
    Image.new("RGB", (200, 100), (128, 128, 128)).save(p)
    data = ip.upscale_to_bytes(p, scale=2)
    assert isinstance(data, bytes) and len(data) > 0
    assert Image.open(io.BytesIO(data)).size == (400, 200)


# === normalizer.majority_nonempty ===

def test_majority_nonempty():
    assert majority_nonempty(["", "283110", "", "283110", ""]) == "283110"
    assert majority_nonempty(["", "", ""]) == ""
    assert majority_nonempty(["A", "B", "B"]) == "B"


# === ai_analyzer.recover_model_number_upscaled ===

def test_recover_takes_majority_nonempty(monkeypatch):
    monkeypatch.setattr(ip, "upscale_to_bytes", lambda p, scale=2: b"x")
    seq = iter([{"model_number": ""}, {"model_number": "283110"}, {"model_number": "283110"}])
    monkeypatch.setattr(ai, "_call_api_bytes",
                        lambda prompt, b, mime_type="image/jpeg", label="": next(seq))
    out = ai.recover_model_number_upscaled(_P("back.jpg"), k=3)
    assert out == "283110"


def test_recover_returns_empty_when_all_empty(monkeypatch):
    monkeypatch.setattr(ip, "upscale_to_bytes", lambda p, scale=2: b"x")
    monkeypatch.setattr(ai, "_call_api_bytes",
                        lambda prompt, b, mime_type="image/jpeg", label="": {"model_number": ""})
    assert ai.recover_model_number_upscaled(_P("back.jpg"), k=3) == ""


def test_recover_normalizes_module_number(monkeypatch):
    # リカバリ結果も型番正規化を通す（数字のみ4桁以下はモジュール番号として空に）
    monkeypatch.setattr(ip, "upscale_to_bytes", lambda p, scale=2: b"x")
    monkeypatch.setattr(ai, "_call_api_bytes",
                        lambda prompt, b, mime_type="image/jpeg", label="": {"model_number": "5196"})
    assert ai.recover_model_number_upscaled(_P("back.jpg"), k=3) == ""
