#!/usr/bin/env python3
"""シリーズ・スローガン複合フィルタの受け入れ検証（実API）。手動・CI対象外。

構造ゲート（純英字3語以上）を通った候補に対し、意味判定 classify_series_is_slogan が
- スローガン（MOST VALUABLE PLAYER）は phrase=True（除外）
- 実在シリーズ（Seven Star Deluxe 等の純英字3語）は name=False（保持・非回帰）
を満たすかを確認する。

使い方: source .venv/bin/activate && python scripts/eval_series_slogan.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ai_analyzer import classify_series_is_slogan
from modules.normalizer import is_multiword_english_phrase_candidate

# (文字列, 期待: True=スローガン除外 / False=シリーズ保持)
CASES = [
    ("MOST VALUABLE PLAYER", True),      # 本命スローガン
    ("SEVEN STAR DELUXE", False),        # 実在シリーズ(CITIZEN)
    ("SEVEN STAR CUSTOM", False),        # 実在シリーズ(CITIZEN)
    ("LORD MATIC SPECIAL", False),       # 実在シリーズ(SEIKO)
    ("KING SEIKO CHRONOMETER", False),   # 実在シリーズ(SEIKO)
    ("KHAKI FIELD MECHANICAL", False),   # 実在シリーズ(HAMILTON)
    ("STAR CUSTOM DELUXE", False),       # 実データ由来(元々nameと判定)
]


def main():
    ok = 0
    for s, expect_exclude in CASES:
        cand = is_multiword_english_phrase_candidate(s)
        slog = classify_series_is_slogan(s) if cand else False
        result = "除外" if slog else "保持"
        good = (slog == expect_exclude)
        ok += good
        print(f"  {s!r}: 候補={cand} スローガン判定={slog} → {result} "
              f"{'OK' if good else 'NG(期待:' + ('除外' if expect_exclude else '保持') + ')'}",
              flush=True)
    print(f"\n合格: {ok}/{len(CASES)}  "
          f"（本命除外 ∧ 実在シリーズ非回帰 が条件）")


if __name__ == "__main__":
    main()
