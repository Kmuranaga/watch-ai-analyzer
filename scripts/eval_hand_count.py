#!/usr/bin/env python3
"""針数クロップ・アンサンブルの受け入れ検証（実API）。CI対象外・手動実行。

正面解析の hand_count（baseline）と、本番の analyze_hand_count_cropped（クロップ
複数倍率＋少ない本数採用）を比較し、過剰検出の是正と本物の3針の非回帰を確認する。
GEMINI_API_KEY が必要。

使い方: source .venv/bin/activate && python scripts/eval_hand_count.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ai_analyzer import analyze_front, analyze_hand_count_cropped
from modules.normalizer import normalize_hand_count

B = "input/結果がまちがっていた商品"
B2 = "input/結果が正しい商品"

# (商品ID, 正面フォルダ, GT針数, 期待: 'fix'=是正対象 / 'keep'=非回帰)
CASES = [
    ("2924278", B, "2針", "fix"),
    ("2924299", B, "2針", "fix"),   # 実はスモールセコンド有（GT自体が疑問）
    ("2924315", B, "2針", "fix"),
    ("2924319", B, "2針", "fix"),
    ("2924285", B, "3針", "fix"),   # 3針目が視認困難（GT自体が疑問・過少方向）
    ("2924275", B, "3針", "keep"),  # 本物の3針 非回帰
    ("2924288", B, "3針", "keep"),
    ("2924290", B, "3針", "keep"),
    ("2924301", B, "3針", "keep"),
    ("2924274", B, "2針", "keep"),  # 本物の2針 非回帰
    ("2924276", B, "2針", "keep"),
    ("2924279", B2, "2針", "keep"),
]

IMG = {".jpg", ".jpeg", ".png"}


def front_image(folder: str, pid: str) -> Path:
    d = Path(folder) / pid
    return sorted(f for f in d.iterdir() if f.suffix.lower() in IMG)[0]


def main():
    rows = []
    for pid, base, gt, kind in CASES:
        front = front_image(base, pid)
        before = normalize_hand_count(analyze_front(front).get("hand_count", ""))
        after = normalize_hand_count(analyze_hand_count_cropped(front).get("hand_count", ""))
        ok = (after == gt)
        rows.append((pid, kind, gt, before, after, ok))
        print(f"{pid} [{kind}] GT={gt} baseline={before} cropped={after} {'OK' if ok else 'NG'}",
              flush=True)

    fixed = sum(1 for r in rows if r[1] == "fix" and r[5])
    fix_total = sum(1 for r in rows if r[1] == "fix")
    kept = sum(1 for r in rows if r[1] == "keep" and r[5])
    keep_total = sum(1 for r in rows if r[1] == "keep")
    print("\n=== 受け入れ判定（クロップ・アンサンブル）===")
    print(f"是正: {fixed}/{fix_total}")
    print(f"非回帰(本物の3針/2針 維持): {kept}/{keep_total}")
    if kept < keep_total:
        print("⚠️ 非回帰が崩れている。クロップ率の調整 or 不採用を検討。")


if __name__ == "__main__":
    main()
