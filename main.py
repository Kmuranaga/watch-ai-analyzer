#!/usr/bin/env python3
"""
腕時計AI自動解析システム - テスト版 (v0.1)
Watch AI Auto-Analysis System - CLI Entry Point

使い方:
  # 基本実行（input/ → output/result.csv）
  python main.py

  # フォルダ指定
  python main.py --input ./images/lot001 --output ./results/lot001.csv

  # 個別処理モード（1商品ずつ即座にレスポンス）
  python main.py --mode single --input ./images/item001/

  # バッチモード（Batch API利用・50%割引）
  python main.py --mode batch --input ./images/lot001/

  # Excel出力
  python main.py --format excel --output ./results/lot001.xlsx

  # ドライラン（AIを呼ばずに構造確認のみ）
  python main.py --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, ANTHROPIC_API_KEY
from modules.folder_scanner import scan_folder, ProductImages
from modules.ai_analyzer import (
    analyze_front, analyze_back_cover, analyze_comment,
    create_batch_requests, submit_batch, poll_batch,
    retrieve_batch_results, parse_batch_results_for_product,
)
from modules.normalizer import normalize_all
from modules.category_mapper import CategoryMapper
from modules.title_generator import generate_title
from modules.csv_writer import ProductResult, write_csv, write_excel


def setup_logging(verbose: bool = False) -> None:
    """ログ設定"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def process_single_product(
    product: ProductImages,
    mapper: CategoryMapper,
    dry_run: bool = False,
) -> ProductResult:
    """
    1商品を処理し、結果を返す。

    処理フロー:
      1. フォルダ名から管理番号を取得（システム仕分け済み）
      2. AI解析（正面）→ ブランド・シリーズ・文字盤色・針数
      3. AI解析（裏蓋）→ 型番・素材・防水
      4. AI解析（コメントシール）→ 異常報告
      5. データ正規化
      6. カテゴリマッピング
      7. タイトル生成
    """
    logger = logging.getLogger(__name__)
    result = ProductResult()
    errors = []

    logger.info(f"=== 商品処理開始: {product.product_id} ({product.image_count}枚) ===")

    # --- Step 1: 管理番号（フォルダ名から取得済み） ---
    result.management_number = product.management_number
    if not result.management_number:
        errors.append("管理番号抽出不可（フォルダ名を確認してください）")

    if dry_run:
        result.status = "ドライラン"
        logger.info(f"[{product.product_id}] ドライラン完了 (管理番号: {result.management_number or '不明'})")
        return result

    # --- Step 2: AI解析（正面画像） ---
    front_data = {}
    if product.front_image:
        try:
            front_data = analyze_front(product.front_image)
        except Exception as e:
            logger.error(f"正面画像AI解析エラー: {e}")
            errors.append(f"正面AI解析エラー: {e}")
    else:
        errors.append("正面画像なし")

    # --- Step 3: AI解析（裏蓋画像） ---
    back_data = {}
    if product.back_cover_image:
        try:
            back_data = analyze_back_cover(product.back_cover_image)
        except Exception as e:
            logger.error(f"裏蓋画像AI解析エラー: {e}")
            errors.append(f"裏蓋AI解析エラー: {e}")
    else:
        errors.append("裏蓋画像なし")

    # --- Step 4: AI解析（コメントシール） ---
    comment_data = {}
    if product.has_comments:
        try:
            comment_data = analyze_comment(product.comment_images)
        except Exception as e:
            logger.error(f"コメントシールAI解析エラー: {e}")
            errors.append(f"コメントAI解析エラー: {e}")

    # --- Step 5: データ正規化 ---
    merged_data = {**front_data, **back_data}
    normalized = normalize_all(merged_data)

    # 結果格納
    result.brand_en = normalized.get("brand_en", "")
    result.brand_kana = normalized.get("brand_kana", "")
    result.series_en = normalized.get("series_en", "")
    result.series_kana = normalized.get("series_kana", "")
    result.model_number = normalized.get("model_number", "")
    result.material = normalized.get("material", "")
    result.water_resistance = normalized.get("water_resistance", "")
    result.movement_type = normalized.get("movement_type", "")
    result.dial_color = normalized.get("dial_color", "")
    result.hand_count = normalized.get("hand_count", "")
    result.abnormality_text = comment_data.get("abnormality_text", "")

    # --- Step 6: カテゴリマッピング ---
    # mapping.xlsxのカナ表記でAI結果を補完
    if result.brand_en and not result.brand_kana:
        result.brand_kana = mapper.get_brand_kana(result.brand_en)
    if result.brand_en and result.series_en and not result.series_kana:
        result.series_kana = mapper.get_series_kana(result.brand_en, result.series_en)

    category_id, match_level = mapper.lookup(
        brand_en=result.brand_en,
        series_en=result.series_en,
        gender="",  # テスト版では性別推定なし
        movement_type=result.movement_type,
        hand_count=result.hand_count,
    )
    result.category_id = category_id

    if match_level == "unknown":
        errors.append("カテゴリ未確定")
    elif match_level == "brand_only":
        errors.append("カテゴリ: ブランドのみ一致")

    # --- Step 7: タイトル生成 ---
    result.title = generate_title(
        brand_en=result.brand_en,
        brand_kana=result.brand_kana,
        series_en=result.series_en,
        series_kana=result.series_kana,
        model_number=result.model_number,
        material=result.material,
        water_resistance=result.water_resistance,
        movement_type=result.movement_type,
    )

    # --- ステータス設定 ---
    if errors:
        result.status = " / ".join(errors)
    else:
        result.status = "正常"

    logger.info(f"[{product.product_id}] 処理完了: {result.brand_en} {result.series_en} - {result.status}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="腕時計AI自動解析システム テスト版 (v0.1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python main.py                                    # デフォルト (input/ → output/result.csv)
  python main.py --input ./images --output out.csv  # フォルダ指定
  python main.py --mode single --input ./item001/   # 個別処理
  python main.py --mode batch --input ./lot001/     # バッチ処理 (50%割引)
  python main.py --format excel                     # Excel出力
  python main.py --dry-run                          # AIを呼ばず構造確認のみ
  python main.py -v                                 # 詳細ログ
        """,
    )
    parser.add_argument("--input", "-i", type=str, default=str(DEFAULT_INPUT_DIR),
                        help="入力画像フォルダ (default: ./input)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="出力ファイルパス (default: ./output/result_YYYYMMDD_HHMMSS.csv)")
    parser.add_argument("--mode", "-m", choices=["single", "batch"], default="single",
                        help="処理モード: single=個別処理, batch=Batch API (default: single)")
    parser.add_argument("--format", "-f", choices=["csv", "excel"], default="csv",
                        help="出力形式 (default: csv)")
    parser.add_argument("--dry-run", action="store_true",
                        help="AIを呼ばずにフォルダ構造の確認のみ行う")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細ログを出力")
    parser.add_argument("--mapping", type=str, default=None,
                        help="マッピングファイルパス (default: ./data/mapping.xlsx)")

    args = parser.parse_args()

    # ログ設定
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # バナー表示
    logger.info("=" * 60)
    logger.info("腕時計AI自動解析システム テスト版 (v0.1)")
    logger.info("Watch AI Auto-Analysis System")
    logger.info("=" * 60)

    # APIキーチェック（ドライラン以外）
    if not args.dry_run and not ANTHROPIC_API_KEY:
        logger.error(
            "ANTHROPIC_API_KEY が設定されていません。\n"
            "以下のコマンドで設定してください:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-api03-..."
        )
        sys.exit(1)

    # 入力フォルダ確認
    input_dir = Path(args.input)
    if not input_dir.exists():
        logger.error(f"入力フォルダが見つかりません: {input_dir}")
        sys.exit(1)

    # 出力パス設定
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = ".xlsx" if args.format == "excel" else ".csv"
        output_path = DEFAULT_OUTPUT_DIR / f"result_{timestamp}{ext}"

    # マッピング読み込み
    mapping_path = Path(args.mapping) if args.mapping else None
    try:
        mapper = CategoryMapper(mapping_path)
    except FileNotFoundError as e:
        logger.error(f"マッピングファイルエラー: {e}")
        sys.exit(1)

    # フォルダスキャン
    logger.info(f"入力フォルダ: {input_dir}")
    products = scan_folder(input_dir)

    if not products:
        logger.error("処理対象の商品が見つかりません。")
        sys.exit(1)

    logger.info(f"検出商品数: {len(products)}")

    # === 処理実行 ===
    results: list[ProductResult] = []

    if args.mode == "batch" and not args.dry_run:
        # === Batch APIモード ===
        logger.info("Batch APIモードで処理を開始します（50%割引適用）")

        # Step 1: Batchリクエスト作成・送信
        batch_requests = create_batch_requests(products)
        if not batch_requests:
            logger.error("Batchリクエストが0件です。")
            sys.exit(1)

        batch_id = submit_batch(batch_requests)

        # Step 3: ポーリングで完了を待機
        logger.info(f"Batch処理の完了を待機中... (batch_id={batch_id})")
        logger.info("（通常1時間以内、最大24時間かかる場合があります）")
        try:
            poll_batch(batch_id, poll_interval=60)
        except RuntimeError as e:
            logger.error(f"Batch処理中断: {e}")
            sys.exit(1)

        # Step 4: 結果取得
        batch_results = retrieve_batch_results(batch_id)

        # Step 4: 各商品の結果をパース → 正規化 → マッピング → タイトル生成
        for product in products:
            result = ProductResult()
            errors = []

            # 管理番号（フォルダ名から取得済み）
            result.management_number = product.management_number
            if not result.management_number:
                errors.append("管理番号抽出不可")

            # Batch結果をパース
            front_data, back_data, comment_data = parse_batch_results_for_product(
                product.product_id, batch_results,
            )

            if not front_data and product.front_image:
                errors.append("正面AI解析: 結果なし")
            if not back_data and product.back_cover_image:
                errors.append("裏蓋AI解析: 結果なし")

            # データ正規化
            merged_data = {**front_data, **back_data}
            normalized = normalize_all(merged_data)

            result.brand_en = normalized.get("brand_en", "")
            result.brand_kana = normalized.get("brand_kana", "")
            result.series_en = normalized.get("series_en", "")
            result.series_kana = normalized.get("series_kana", "")
            result.model_number = normalized.get("model_number", "")
            result.material = normalized.get("material", "")
            result.water_resistance = normalized.get("water_resistance", "")
            result.movement_type = normalized.get("movement_type", "")
            result.dial_color = normalized.get("dial_color", "")
            result.hand_count = normalized.get("hand_count", "")
            result.abnormality_text = comment_data.get("abnormality_text", "")

            # カテゴリマッピング（mapping.xlsxのカナ表記で補完）
            if result.brand_en and not result.brand_kana:
                result.brand_kana = mapper.get_brand_kana(result.brand_en)
            if result.brand_en and result.series_en and not result.series_kana:
                result.series_kana = mapper.get_series_kana(result.brand_en, result.series_en)

            category_id, match_level = mapper.lookup(
                brand_en=result.brand_en,
                series_en=result.series_en,
                gender="",
                movement_type=result.movement_type,
                hand_count=result.hand_count,
            )
            result.category_id = category_id

            if match_level == "unknown":
                errors.append("カテゴリ未確定")
            elif match_level == "brand_only":
                errors.append("カテゴリ: ブランドのみ一致")

            # タイトル生成
            result.title = generate_title(
                brand_en=result.brand_en,
                brand_kana=result.brand_kana,
                series_en=result.series_en,
                series_kana=result.series_kana,
                model_number=result.model_number,
                material=result.material,
                water_resistance=result.water_resistance,
                movement_type=result.movement_type,
            )

            result.status = " / ".join(errors) if errors else "正常"
            results.append(result)
            logger.info(f"[{product.product_id}] {result.brand_en} {result.series_en} - {result.status}")

    elif args.mode == "single" or args.dry_run:
        # 個別処理モード
        for i, product in enumerate(products, 1):
            logger.info(f"--- [{i}/{len(products)}] ---")
            result = process_single_product(product, mapper, dry_run=args.dry_run)
            results.append(result)

    # === 出力 ===
    if args.format == "excel":
        write_excel(results, output_path)
    else:
        write_csv(results, output_path)

    # === サマリー ===
    total = len(results)
    ok = sum(1 for r in results if r.status == "正常")
    err = total - ok

    logger.info("=" * 60)
    logger.info(f"処理完了: 合計 {total}件 (正常: {ok}件, エラー/警告: {err}件)")
    logger.info(f"出力ファイル: {output_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
