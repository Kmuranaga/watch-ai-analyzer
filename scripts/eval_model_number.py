#!/usr/bin/env python3
"""型番リカバリ（空欄時の裏蓋拡大リトライ＋多数決）の受け入れ検証（実API）。手動・CI対象外。

本番と同じ条件付きロジックを再現:
  裏蓋を1回読む → 型番が空なら recover_model_number_upscaled で拡大リトライ＋多数決。

- 2924286: 初回が空になりやすいジッター → リカバリで 283110 を回収できるか
- 2924290: 初回で読める → リカバリ発火せず 469658A-6B 維持（回帰なし）
- 2897878: 判読不能 → リカバリしても空のまま（誤って捏造しないこと）

使い方: source .venv/bin/activate && python scripts/eval_model_number.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ai_analyzer import analyze_back_cover, recover_model_number_upscaled
from modules.normalizer import normalize_model_number

IMG = {".jpg", ".jpeg", ".png"}
ROOT = Path("input")


def back_image(pid: str):
    for d in ROOT.rglob(f"{pid}*"):
        if d.is_dir():
            im = sorted(f for f in d.iterdir() if f.suffix.lower() in IMG)
            if len(im) > 7:
                return im[7]
    return None


# pid, GT型番, N, 期待
CASES = [
    ("2924286", "283110", 4, "recover"),
    ("2924290", "469658A-6B", 2, "keep"),
    ("2897878", "", 2, "stay-empty"),
]


def main():
    for pid, gt, n, kind in CASES:
        back = back_image(pid)
        print(f"\n--- {pid} (GT={gt!r}, {kind}) x{n} ---", flush=True)
        for i in range(n):
            first = normalize_model_number(analyze_back_cover(back).get("model_number", ""))
            if first:
                final, fired = first, False
            else:
                final, fired = recover_model_number_upscaled(back), True
            ok = (final.upper() == gt.upper())
            print(f"  run{i+1}: 初回={first!r} リカバリ発火={fired} 最終={final!r} "
                  f"{'OK' if ok else 'NG'}", flush=True)


if __name__ == "__main__":
    main()
