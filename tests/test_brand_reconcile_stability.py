"""裏蓋ブランド上書きの安定化（stabilize_back_brand_override / verify_back_brand_choice）のテスト"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import modules.ai_analyzer as ai
from modules.normalizer import stabilize_back_brand_override


def _counter(values):
    """resample_fn のスタブ。呼ばれた回数も記録する。"""
    it = iter(values)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return next(it, "")
    return fn, calls


def test_no_resample_when_front_equals_back():
    fn, calls = _counter([])
    assert stabilize_back_brand_override("SEIKO", "SEIKO", fn) is True
    assert calls["n"] == 0  # 上書きが起きないので再サンプルしない


def test_no_resample_when_back_is_movement_maker():
    # RONSON/CITIZEN: 裏蓋が製造元 → 上書きされない → 再サンプルなし
    fn, calls = _counter([])
    assert stabilize_back_brand_override("RONSON", "CITIZEN", fn) is True
    assert calls["n"] == 0


def test_no_resample_when_front_empty():
    fn, calls = _counter([])
    assert stabilize_back_brand_override("", "ELGIN", fn) is True
    assert calls["n"] == 0


def test_no_resample_when_back_is_case_maker():
    # CITIZEN/STAR: 裏蓋がケースメーカー刻印 → 上書き対象外 → 再サンプル不要
    fn, calls = _counter([])
    assert stabilize_back_brand_override("CITIZEN", "STAR", fn) is True
    assert calls["n"] == 0


def test_stable_back_is_trusted():
    # ELGIN型: 正面誤読(TAG HEUER) vs 裏蓋ELGINが安定 → 上書き採用
    fn, calls = _counter(["ELGIN", "ELGIN", "ELGIN"])
    assert stabilize_back_brand_override("TAG HEUER", "ELGIN", fn, k=3) is True
    assert calls["n"] == 3


def test_unstable_back_is_rejected():
    # 2924323型: 正面SWATCH(安定) vs 裏蓋がノイズ(空/別) → 上書きせず正面維持
    fn, calls = _counter(["", "", ""])
    assert stabilize_back_brand_override("SWATCH", "ISSEY MIYAKE", fn, k=3) is False
    assert calls["n"] == 3


def test_minority_back_is_rejected():
    # 元1回 + 再サンプルで bb が過半数に届かない → False
    fn, _ = _counter(["ISSEY MIYAKE", "", ""])  # bb=2/4 は過半数でない
    assert stabilize_back_brand_override("SWATCH", "ISSEY MIYAKE", fn, k=3) is False


def test_majority_back_is_trusted():
    # 元1回 + 再サンプルで bb が過半数 → True
    fn, _ = _counter(["ELGIN", "ELGIN", "OTHER"])  # ELGIN=3/4 は過半数
    assert stabilize_back_brand_override("TAG HEUER", "ELGIN", fn, k=3) is True


# === verify_back_brand_choice（二択照合・幻覚ガード） ===

def _choice(monkeypatch, api_result):
    """_call_api をスタブして verify_back_brand_choice を実行する。"""
    if isinstance(api_result, Exception):
        def fake(_prompt, _img):
            raise api_result
    else:
        def fake(_prompt, _img):
            return api_result
    monkeypatch.setattr(ai, "_call_api", fake)
    return ai.verify_back_brand_choice(Path("dummy.jpg"), "BINLUN", "KENTEX")


def test_choice_answer_a_returns_front(monkeypatch):
    assert _choice(monkeypatch, {"answer": "A", "engraved_text": "BINLUN"}) == "front"


def test_choice_answer_b_returns_back(monkeypatch):
    assert _choice(monkeypatch, {"answer": "B", "engraved_text": "KENTEX"}) == "back"


def test_choice_answer_lowercase_is_normalized(monkeypatch):
    assert _choice(monkeypatch, {"answer": " a "}) == "front"


def test_choice_answer_c_returns_unknown(monkeypatch):
    assert _choice(monkeypatch, {"answer": "C"}) == "unknown"


def test_choice_garbage_answer_returns_unknown(monkeypatch):
    assert _choice(monkeypatch, {"answer": "D: 不明"}) == "unknown"


def test_choice_missing_answer_returns_unknown(monkeypatch):
    assert _choice(monkeypatch, {"engraved_text": "MIYOTA"}) == "unknown"


def test_choice_api_exception_returns_unknown(monkeypatch):
    assert _choice(monkeypatch, RuntimeError("api down")) == "unknown"
