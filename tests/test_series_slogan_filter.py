"""シリーズのスローガン除外（複合フィルタ）のテスト"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import modules.ai_analyzer as ai
from modules.normalizer import is_multiword_english_phrase_candidate


# === 構造ゲート: is_multiword_english_phrase_candidate ===

def test_candidate_true_for_3plus_pure_english():
    assert is_multiword_english_phrase_candidate("MOST VALUABLE PLAYER") is True
    assert is_multiword_english_phrase_candidate("SEVEN STAR DELUXE") is True  # 実シリーズも候補にはなる


def test_candidate_false_for_1_2_words():
    assert is_multiword_english_phrase_candidate("ANGEL") is False
    assert is_multiword_english_phrase_candidate("LORD MATIC") is False
    assert is_multiword_english_phrase_candidate("SEVEN STAR") is False
    assert is_multiword_english_phrase_candidate("") is False


def test_candidate_false_when_hyphen_or_digit():
    # G-SHOCK/EL-330 等の型番的語を含むものは候補にしない（保護）
    assert is_multiword_english_phrase_candidate("G-SHOCK CODE NAME") is False
    assert is_multiword_english_phrase_candidate("SEIKO 5 SPORTS") is False


# === 意味ゲート: classify_series_is_slogan ===

def test_classify_returns_true_on_phrase(monkeypatch):
    monkeypatch.setattr(ai, "_call_text_api", lambda prompt, label="": {"type": "phrase"})
    assert ai.classify_series_is_slogan("MOST VALUABLE PLAYER") is True


def test_classify_returns_false_on_name(monkeypatch):
    monkeypatch.setattr(ai, "_call_text_api", lambda prompt, label="": {"type": "name"})
    assert ai.classify_series_is_slogan("SEVEN STAR DELUXE") is False


def test_classify_defaults_to_false_on_error(monkeypatch):
    def boom(prompt, label=""):
        raise RuntimeError("api down")
    monkeypatch.setattr(ai, "_call_text_api", boom)
    # 失敗時は保持（False）に倒す
    assert ai.classify_series_is_slogan("ANYTHING LONG PHRASE") is False


def test_classify_defaults_to_false_on_empty_result(monkeypatch):
    monkeypatch.setattr(ai, "_call_text_api", lambda prompt, label="": {})
    assert ai.classify_series_is_slogan("SOME LONG PHRASE") is False


# === 複合の考え方の確認（構造で候補を絞ってから意味判定）===

def test_compound_protects_dictionary_word_series_without_api(monkeypatch):
    # 1語の英単語シリーズ(ANGEL/IRONY)は構造ゲートで候補外 → 意味判定を呼ばない
    called = {"n": 0}
    monkeypatch.setattr(ai, "_call_text_api",
                        lambda prompt, label="": called.__setitem__("n", called["n"] + 1) or {"type": "phrase"})
    for s in ["ANGEL", "IRONY", "SEVEN STAR", "LORD MATIC"]:
        if is_multiword_english_phrase_candidate(s):
            ai.classify_series_is_slogan(s)
    assert called["n"] == 0  # どれも候補外なのでAPIは一度も呼ばれない
