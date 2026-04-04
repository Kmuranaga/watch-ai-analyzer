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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, GEMINI_API_KEY, MAX_CONCURRENT_PRODUCTS
from modules.folder_scanner import scan_folder, ProductImages
from modules.ai_analyzer import (
    analyze_front, analyze_back_cover, analyze_comment,
    create_batch_requests, submit_batch, poll_batch,
    retrieve_batch_results, parse_batch_results_for_product,
    register_rate_limit_callback,
)
from modules.normalizer import normalize_all
from modules.category_mapper import CategoryMapper
from modules.title_generator import generate_title
from modules.csv_writer import ProductResult, write_csv, write_excel

# レートリミット発生カウンター（CLIメッセージ用）
_cli_rate_limit_count = 0


def _cli_rate_limit_handler(event_type: str, detail: dict):
    """CLI用レートリミット通知ハンドラ"""
    global _cli_rate_limit_count
    cli_logger = logging.getLogger(__name__)

    if event_type == "rate_limit_hit":
        _cli_rate_limit_count += 1
        cli_logger.warning(
            f"[レートリミット] APIの呼び出し上限に到達しました。"
            f"{detail['delay']}秒待機後に自動リトライします "
            f"(リトライ {detail['attempt']}/{detail['max_retries']}回目, 対象: {detail['image_path']})"
        )
        if _cli_rate_limit_count == 1:
            cli_logger.info(
                "[対処方法] そのまま待てば自動的にリトライされます。\n"
                "  頻発する場合の対策:\n"
                "  1. 商品数を分割して実行する（100件以下を推奨）\n"
                "  2. Google AI Studioでレートリミットの引き上げを確認する\n"
                "  3. 時間を空けてから再実行する"
            )
    elif event_type == "rate_limit_retry_exhausted":
        cli_logger.error(
            f"[リトライ失敗] {detail['image_path']} のAI解析に失敗しました（リトライ上限到達）。\n"
            "  → この商品は空データとして出力されます。\n"
            "  → 処理完了後、失敗した商品だけを別フォルダにまとめて再実行してください。"
        )
    elif event_type == "api_key_error":
        cli_logger.error(
            "[APIキーエラー] Gemini APIの認証に失敗しました。\n"
            "  APIキーが無効または間違っている可能性があります。\n"
            "  対処方法:\n"
            "  1. 正しいAPIキーを設定してください: export GEMINI_API_KEY=your-api-key\n"
            "  2. Google AI Studio (aistudio.google.com) でキーを確認できます\n"
            "  3. .envファイルのGEMINI_API_KEYの値を確認してください"
        )


register_rate_limit_callback(_cli_rate_limit_handler)


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

    # --- Step 2-4: AI解析（正面・裏蓋・コメントを並列実行） ---
    front_data = {}
    back_data = {}
    comment_data = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        if product.front_image:
            futures[executor.submit(analyze_front, product.front_image, product.diagonal_image)] = "front"
        else:
            errors.append("正面画像なし")

        if product.back_cover_image:
            futures[executor.submit(analyze_back_cover, product.back_cover_image)] = "back"
        else:
            errors.append("裏蓋画像なし")

        if product.has_comments:
            futures[executor.submit(analyze_comment, product.comment_images)] = "comment"

        for future in as_completed(futures):
            task_type = futures[future]
            try:
                if task_type == "front":
                    front_data = future.result()
                elif task_type == "back":
                    back_data = future.result()
                elif task_type == "comment":
                    comment_data = future.result()
            except Exception as e:
                label = {"front": "正面", "back": "裏蓋", "comment": "コメント"}[task_type]
                logger.error(f"{label}画像AI解析エラー: {e}")
                errors.append(f"{label}AI解析エラー: {e}")

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
    result.case_shape = normalized.get("case_shape", "")
    result.gender = normalized.get("gender", "")
    result.title_prefix = comment_data.get("title_prefix", "")
    result.abnormality_text = comment_data.get("abnormality_text", "")

    # --- Step 6: カテゴリマッピング ---
    # mapping.xlsxのカナ表記でAI結果を補完
    if result.brand_en and not result.brand_kana:
        result.brand_kana = mapper.get_brand_kana(result.brand_en)
    if result.brand_en and result.series_en and not result.series_kana:
        result.series_kana = mapper.get_series_kana(result.brand_en, result.series_en)

    category_id, match_level, matched_entry = mapper.lookup(
        brand_en=result.brand_en,
        series_en=result.series_en,
        gender=result.gender,
        movement_type=result.movement_type,
        hand_count=result.hand_count,
        model_number=result.model_number,
    )

    # 型番マッチ時: マッピングのシリーズ・性別で上書き（空白ならAI解析を使用）
    if match_level == "model_number" and matched_entry:
        if matched_entry["series_en"]:
            result.series_en = matched_entry["series_en"]
        if matched_entry["series_kana"]:
            result.series_kana = matched_entry["series_kana"]
        if matched_entry["gender"]:
            result.gender = matched_entry["gender"]

    # 追加単語: ブランドor型番のどちらかが一致したら追加
    additional_word = mapper.get_additional_word(result.brand_en, result.model_number)

    result.category_id = category_id

    # カテゴリ名の逆引き
    if result.category_id:
        result.category_name = mapper.get_category_name(result.category_id)

    if match_level == "unknown":
        errors.append("カテゴリ未確定")
    elif match_level == "brand_only":
        errors.append("カテゴリ: ブランドのみ一致")

    # --- Step 7: タイトル生成 ---
    result.title = generate_title(
        title_prefix=result.title_prefix,
        brand_en=result.brand_en,
        brand_kana=result.brand_kana,
        series_en=result.series_en,
        series_kana=result.series_kana,
        model_number=result.model_number,
        dial_color=result.dial_color,
        hand_count=result.hand_count,
        case_shape=result.case_shape,
        material=result.material,
        water_resistance=result.water_resistance,
        movement_type=result.movement_type,
        additional_word=additional_word,
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
    if not args.dry_run and not GEMINI_API_KEY:
        logger.error(
            "GEMINI_API_KEY が設定されていません。\n"
            "以下のコマンドで設定してください:\n"
            "  export GEMINI_API_KEY=your-api-key"
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
            result.case_shape = normalized.get("case_shape", "")
            result.gender = normalized.get("gender", "")
            result.title_prefix = comment_data.get("title_prefix", "")
            result.abnormality_text = comment_data.get("abnormality_text", "")

            # カテゴリマッピング（mapping.xlsxのカナ表記で補完）
            if result.brand_en and not result.brand_kana:
                result.brand_kana = mapper.get_brand_kana(result.brand_en)
            if result.brand_en and result.series_en and not result.series_kana:
                result.series_kana = mapper.get_series_kana(result.brand_en, result.series_en)

            category_id, match_level, matched_entry = mapper.lookup(
                brand_en=result.brand_en,
                series_en=result.series_en,
                gender=result.gender,
                movement_type=result.movement_type,
                hand_count=result.hand_count,
                model_number=result.model_number,
            )

            # 型番マッチ時: マッピングのシリーズ・性別で上書き（空白ならAI解析を使用）
            if match_level == "model_number" and matched_entry:
                if matched_entry["series_en"]:
                    result.series_en = matched_entry["series_en"]
                if matched_entry["series_kana"]:
                    result.series_kana = matched_entry["series_kana"]
                if matched_entry["gender"]:
                    result.gender = matched_entry["gender"]

            # 追加単語: ブランドor型番のどちらかが一致したら追加
            additional_word = mapper.get_additional_word(result.brand_en, result.model_number)

            result.category_id = category_id

            # カテゴリ名の逆引き
            if result.category_id:
                result.category_name = mapper.get_category_name(result.category_id)

            if match_level == "unknown":
                errors.append("カテゴリ未確定")
            elif match_level == "brand_only":
                errors.append("カテゴリ: ブランドのみ一致")

            # タイトル生成
            result.title = generate_title(
                title_prefix=result.title_prefix,
                brand_en=result.brand_en,
                brand_kana=result.brand_kana,
                series_en=result.series_en,
                series_kana=result.series_kana,
                model_number=result.model_number,
                dial_color=result.dial_color,
                hand_count=result.hand_count,
                case_shape=result.case_shape,
                material=result.material,
                water_resistance=result.water_resistance,
                movement_type=result.movement_type,
                additional_word=additional_word,
            )

            result.status = " / ".join(errors) if errors else "正常"
            results.append(result)
            logger.info(f"[{product.product_id}] {result.brand_en} {result.series_en} - {result.status}")

    elif args.mode == "single" or args.dry_run:
        # 個別処理モード（複数商品を並列処理）
        if args.dry_run:
            # ドライランは直列で十分
            for i, product in enumerate(products, 1):
                logger.info(f"--- [{i}/{len(products)}] ---")
                result = process_single_product(product, mapper, dry_run=True)
                results.append(result)
        else:
            logger.info(f"並列処理モード: 最大{MAX_CONCURRENT_PRODUCTS}商品を同時処理")
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PRODUCTS) as executor:
                future_to_product = {
                    executor.submit(process_single_product, product, mapper): product
                    for product in products
                }
                for future in as_completed(future_to_product):
                    product = future_to_product[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"[{product.product_id}] 処理失敗: {e}")
                        err_result = ProductResult()
                        err_result.management_number = product.management_number
                        err_result.status = f"処理エラー: {e}"
                        results.append(err_result)

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
    if _cli_rate_limit_count > 0:
        logger.warning(
            f"レートリミット発生回数: {_cli_rate_limit_count}回\n"
            "  空白データの商品がある場合は、該当商品を別フォルダにまとめて再実行してください。"
        )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
