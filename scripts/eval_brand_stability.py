#!/usr/bin/env python3
"""裏蓋ブランド上書き安定化の受け入れ検証（実API）。CI対象外・手動実行。

各商品で本番フロー（正面解析→裏蓋解析→stabilize_back_brand_override→reconcile_brand）を
N回実行し、最終ブランドの分布を確認する。
- ELGIN: 正面TAG HEUER誤読でも裏蓋ELGIN安定 → ELGIN 維持（非回帰）
- RONSON: 裏蓋CITIZEN=製造元 → 再サンプルせず RONSON 維持（非回帰）
- 2924323: 正面SWATCH安定、裏蓋がたまにISSEY MIYAKE → 再サンプルで棄却し SWATCH 安定

使い方: source .venv/bin/activate && python scripts/eval_brand_stability.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.ai_analyzer import analyze_front, analyze_back_cover
from modules.normalizer import stabilize_back_brand_override, reconcile_brand

IMG = {".jpg", ".jpeg", ".png"}

# (label, folder, 期待ブランド, N)
CASES = [
    ("2924323", "input/結果が正しい商品/2924323", "SWATCH", 8),
    ("ELGIN(2916676)", "input/エルジン_タグホイヤー", "ELGIN", 4),
    ("RONSON(2924321)", "input/ブランドと内部パーツが異なる/2924321_ RONSON_CITIZEN", "RONSON", 3),
]


def images(folder):
    return sorted(f for f in Path(folder).iterdir() if f.suffix.lower() in IMG)


def main():
    for label, folder, expect, n in CASES:
        im = images(folder)
        front, diag = im[0], (im[1] if len(im) > 1 else None)
        back = im[7] if len(im) > 7 else None
        print(f"\n--- {label} (期待={expect}) x{n} ---", flush=True)
        finals = Counter()
        for i in range(n):
            fb = analyze_front(front, diag).get("brand_en", "")
            bb = analyze_back_cover(back).get("back_brand_en", "") if back else ""
            trust = stabilize_back_brand_override(
                fb, bb, resample_fn=lambda: analyze_back_cover(back).get("back_brand_en", "")
            )
            eff_bb = bb if trust else ""
            final, src = reconcile_brand(fb, eff_bb)
            finals[final] += 1
            note = "" if (bb and not trust) else ""
            print(f"  run{i+1}: front={fb!r} back={bb!r} trust={trust} -> {final!r}", flush=True)
        ok = all(k == expect for k in finals)
        print(f"  => 分布 {dict(finals)}  {'OK' if ok else 'NG'}", flush=True)


if __name__ == "__main__":
    main()
