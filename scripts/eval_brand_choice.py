#!/usr/bin/env python3
"""裏蓋ブランド二択照合（幻覚ガード）の受け入れ検証（実API）。CI対象外・手動実行。

本番ヘルパー apply_back_brand_stabilization をそのまま実行し、
一貫した幻覚読み（BINLUN→KENTEX）の棄却と、正当な上書き（ELGIN）・
製造元ガード（RONSON）の非回帰を確認する。

- 2951489 (BINLUN): 裏蓋自由読みが KENTEX を幻覚 → 二択照合で棄却 → BINLUN
- ELGIN(2916676): 正面TAG HEUER誤読でも裏蓋ELGINが実刻印 → 照合=back → ELGIN 維持
- RONSON(2924321): 裏蓋CITIZEN=製造元 → 発火条件外（照合を呼ばない） → RONSON

使い方: source .venv/bin/activate && python scripts/eval_brand_choice.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
from modules.ai_analyzer import analyze_front, analyze_back_cover, verify_back_brand_choice
from modules.folder_scanner import ProductImages, extract_management_number
from modules.normalizer import reconcile_brand

IMG = {".jpg", ".jpeg", ".png"}

BINLUN_DIR = ("/private/tmp/claude-501/-Users-muranagakotaro-watch-ai-analyzer/"
              "ac253eb8-08eb-47d4-a3c0-2f79f60f0c71/scratchpad/binlun/2951489")

# (label, folder, 期待ブランド, 照合が発火する見込みか)
CASES = [
    ("BINLUN(2951489)", BINLUN_DIR, "BINLUN", True),
    ("ELGIN(2916676)", "input/エルジン_タグホイヤー", "ELGIN", True),
    ("RONSON(2924321)", "input/ブランドと内部パーツが異なる/2924321_ RONSON_CITIZEN", "RONSON", False),
]


def make_product(folder: str) -> ProductImages:
    p = Path(folder)
    images = sorted(f for f in p.iterdir() if f.suffix.lower() in IMG)
    return ProductImages(
        product_id=p.name,
        management_number=extract_management_number(p.name),
        folder_path=p,
        images=images,
    )


def main():
    all_pass = True
    for label, folder, expect, expect_fire in CASES:
        product = make_product(folder)
        print(f"\n--- {label} (期待={expect}) ---", flush=True)

        front_data = analyze_front(product.front_image, product.diagonal_image)
        back_data = analyze_back_cover(product.back_cover_image)
        fb0 = front_data.get("brand_en", "")
        bb0 = back_data.get("back_brand_en", "")
        print(f"  front読み: {fb0!r}", flush=True)
        print(f"  back読み : {bb0!r}", flush=True)

        # 照合が発火したかを記録しつつ、本番ヘルパーをそのまま実行
        fired = {"n": 0, "choice": None}

        def counted_choice(img, f, b, _fired=fired):
            _fired["n"] += 1
            _fired["choice"] = verify_back_brand_choice(img, f, b)
            print(f"  二択照合: A:{f} / B:{b} -> {_fired['choice']}", flush=True)
            return _fired["choice"]

        orig = main_module.verify_back_brand_choice
        main_module.verify_back_brand_choice = counted_choice
        try:
            f2, b2 = dict(front_data), dict(back_data)
            main_module.apply_back_brand_stabilization(product, f2, b2)
        finally:
            main_module.verify_back_brand_choice = orig

        final, src = reconcile_brand(f2.get("brand_en", ""), b2.get("back_brand_en", ""))
        ok = final == expect
        all_pass = all_pass and ok
        fired_str = f"あり({fired['choice']})" if fired["n"] else "なし"
        if expect_fire and not fired["n"]:
            print("  ※ 照合が発火しなかった（裏蓋読みが今回は幻覚しなかった等）", flush=True)
        print(f"  照合発火: {fired_str} / 最終ブランド: {final!r} (source={src}) "
              f"=> {'PASS' if ok else 'FAIL'}", flush=True)

    print(f"\n=== 総合: {'3/3 PASS' if all_pass else 'FAIL あり'} ===", flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
