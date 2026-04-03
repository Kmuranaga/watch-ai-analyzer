#!/usr/bin/env python3
"""
腕時計AI自動解析システム - ブラウザUI版
Watch AI Auto-Analysis System - Web Interface

使い方:
  python app.py
  ブラウザで http://localhost:5000 を開く
"""

import json
import logging
import os
import queue
import sys
import threading
import time
import io
import csv
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

import config
from config import DEFAULT_INPUT_DIR, MAX_CONCURRENT_PRODUCTS, CSV_ENCODING
from modules.folder_scanner import scan_folder
from modules.ai_analyzer import analyze_front, analyze_back_cover, analyze_comment, register_rate_limit_callback
from modules.normalizer import normalize_all
from modules.category_mapper import CategoryMapper
from modules.title_generator import generate_title
from modules.csv_writer import ProductResult, COLUMNS, write_csv, write_excel

app = Flask(__name__)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ジョブ管理（シングルプロセス想定）
jobs: dict[str, dict] = {}


# 現在実行中のジョブキュー（レートリミット通知用）
_active_job_queue: queue.Queue | None = None
_active_job_lock = threading.Lock()


def _on_rate_limit(event_type: str, detail: dict):
    """レートリミット発生時にSSEキューへ通知を送る"""
    with _active_job_lock:
        q = _active_job_queue
    if q is None:
        return

    if event_type == "rate_limit_hit":
        q.put({
            "event": "rate_limit",
            "message": (
                f"⚠ APIレートリミットに到達しました（{detail['image_path']}）。"
                f"{detail['delay']}秒待機後にリトライします（{detail['attempt']}/{detail['max_retries']}回目）"
            ),
            "detail": (
                "Gemini APIの呼び出し上限に達しました。自動的にリトライしますのでそのままお待ちください。"
                "頻発する場合は、Google AI Studioでプランのアップグレードをご検討ください。"
            ),
            "level": "warning",
        })
    elif event_type == "rate_limit_retry_exhausted":
        q.put({
            "event": "rate_limit",
            "message": (
                f"✕ リトライ上限到達: {detail['image_path']} の解析に失敗しました"
            ),
            "detail": (
                "リトライ回数を使い切りました。この商品は空データとして出力されます。"
                "処理完了後、失敗した商品だけを別フォルダにまとめて再実行してください。"
            ),
            "level": "error",
        })
    elif event_type == "api_key_error":
        q.put({
            "event": "api_key_error",
            "message": (
                f"✕ APIキーエラー: Gemini APIの認証に失敗しました"
            ),
            "detail": (
                "APIキーが無効または間違っている可能性があります。"
                "画面上部の「Gemini APIキー」欄から正しいキーを再設定してください。"
                "Google AI Studio (aistudio.google.com) でキーを確認できます。"
            ),
            "error": detail.get("error", ""),
            "level": "error",
        })


register_rate_limit_callback(_on_rate_limit)


def get_mapper() -> CategoryMapper:
    return CategoryMapper()


def process_product_with_progress(
    product, mapper: CategoryMapper, job_queue: queue.Queue, index: int, total: int, dry_run: bool = False
) -> ProductResult:
    """1商品を処理し、進捗をキューに送る"""
    product_id = product.product_id

    job_queue.put({
        "event": "product_start",
        "index": index,
        "total": total,
        "product_id": product_id,
        "message": f"処理開始: {product_id}",
    })

    result = ProductResult()
    errors = []

    result.management_number = product.management_number
    if not result.management_number:
        errors.append("管理番号抽出不可")

    if dry_run:
        result.status = "ドライラン"
        job_queue.put({
            "event": "product_done",
            "index": index,
            "total": total,
            "product_id": product_id,
            "message": f"ドライラン完了: {product_id}",
            "status": "ドライラン",
        })
        return result

    # AI解析（正面・裏蓋・コメントを並列実行）
    front_data = {}
    back_data = {}
    comment_data = {}

    job_queue.put({
        "event": "log",
        "product_id": product_id,
        "message": f"[{product_id}] AI解析開始（正面・裏蓋・コメント）",
    })

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        if product.front_image:
            futures[executor.submit(analyze_front, product.front_image)] = "front"
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
            label = {"front": "正面", "back": "裏蓋", "comment": "コメント"}[task_type]
            try:
                if task_type == "front":
                    front_data = future.result()
                    job_queue.put({
                        "event": "log",
                        "product_id": product_id,
                        "message": f"[{product_id}] {label}画像解析完了",
                    })
                elif task_type == "back":
                    back_data = future.result()
                    job_queue.put({
                        "event": "log",
                        "product_id": product_id,
                        "message": f"[{product_id}] {label}画像解析完了",
                    })
                elif task_type == "comment":
                    comment_data = future.result()
                    job_queue.put({
                        "event": "log",
                        "product_id": product_id,
                        "message": f"[{product_id}] {label}シール解析完了",
                    })
            except Exception as e:
                logger.error(f"{label}画像AI解析エラー: {e}")
                errors.append(f"{label}AI解析エラー: {e}")
                job_queue.put({
                    "event": "log",
                    "product_id": product_id,
                    "message": f"[{product_id}] {label}解析エラー: {e}",
                    "level": "error",
                })

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

    # カテゴリマッピング
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
    additional_word = ""
    if match_level == "model_number" and matched_entry:
        if matched_entry["series_en"]:
            result.series_en = matched_entry["series_en"]
        if matched_entry["series_kana"]:
            result.series_kana = matched_entry["series_kana"]
        if matched_entry["gender"]:
            result.gender = matched_entry["gender"]
        additional_word = matched_entry.get("additional_word", "")

    result.category_id = category_id

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

    job_queue.put({
        "event": "product_done",
        "index": index,
        "total": total,
        "product_id": product_id,
        "message": f"処理完了: {product_id} — {result.brand_en} {result.series_en}",
        "status": result.status,
    })

    return result


def run_job(job_id: str, input_dir: str, mode: str, dry_run: bool):
    """バックグラウンドスレッドで解析ジョブを実行"""
    global _active_job_queue
    job = jobs[job_id]
    job_queue = job["queue"]
    start_time = time.time()

    with _active_job_lock:
        _active_job_queue = job_queue

    try:
        m = get_mapper()

        # フォルダスキャン
        input_path = Path(input_dir)
        if not input_path.exists():
            job_queue.put({
                "event": "error",
                "message": f"入力フォルダが見つかりません: {input_dir}",
            })
            job_queue.put({"event": "complete", "results": [], "error": True})
            return

        products = scan_folder(input_path)
        if not products:
            job_queue.put({
                "event": "error",
                "message": "処理対象の商品が見つかりません。",
            })
            job_queue.put({"event": "complete", "results": [], "error": True})
            return

        total = len(products)
        job_queue.put({
            "event": "scan_done",
            "total": total,
            "message": f"検出商品数: {total}件",
        })

        results: list[ProductResult] = []

        if dry_run:
            for i, product in enumerate(products, 1):
                result = process_product_with_progress(product, m, job_queue, i, total, dry_run=True)
                results.append(result)
        else:
            # APIキーチェック
            if not config.GEMINI_API_KEY:
                job_queue.put({
                    "event": "error",
                    "message": "GEMINI_API_KEY が設定されていません。環境変数を設定してください。",
                })
                job_queue.put({"event": "complete", "results": [], "error": True})
                return

            # 個別処理モード（並列）
            completed = 0
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PRODUCTS) as executor:
                future_to_idx = {}
                for i, product in enumerate(products, 1):
                    future = executor.submit(
                        process_product_with_progress, product, m, job_queue, i, total, False
                    )
                    future_to_idx[future] = (i, product)

                for future in as_completed(future_to_idx):
                    idx, product = future_to_idx[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"[{product.product_id}] 処理失敗: {e}")
                        err_result = ProductResult()
                        err_result.management_number = product.management_number
                        err_result.status = f"処理エラー: {e}"
                        results.append(err_result)
                        job_queue.put({
                            "event": "product_done",
                            "index": idx,
                            "total": total,
                            "product_id": product.product_id,
                            "message": f"処理エラー: {product.product_id} — {e}",
                            "status": f"処理エラー: {e}",
                        })

                    completed += 1
                    elapsed = time.time() - start_time
                    if completed > 0 and completed < total:
                        eta = (elapsed / completed) * (total - completed)
                    else:
                        eta = 0
                    job_queue.put({
                        "event": "progress",
                        "completed": completed,
                        "total": total,
                        "elapsed": round(elapsed, 1),
                        "eta": round(eta, 1),
                    })

        # 結果をdictリストに変換
        job["results"] = results
        elapsed = round(time.time() - start_time, 1)

        ok = sum(1 for r in results if r.status == "正常")
        err = len(results) - ok

        result_dicts = []
        for r in results:
            result_dicts.append(asdict(r))

        job_queue.put({
            "event": "complete",
            "results": result_dicts,
            "total": len(results),
            "ok": ok,
            "errors": err,
            "elapsed": elapsed,
            "error": False,
        })

    except Exception as e:
        logger.exception(f"ジョブ実行エラー: {e}")
        job_queue.put({
            "event": "error",
            "message": f"予期しないエラー: {e}",
        })
        job_queue.put({"event": "complete", "results": [], "error": True})
    finally:
        with _active_job_lock:
            _active_job_queue = None


# === ルーティング ===

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json()
    input_dir = data.get("input_dir", str(DEFAULT_INPUT_DIR))
    mode = data.get("mode", "single")
    output_format = data.get("format", "csv")
    dry_run = data.get("dry_run", False)

    job_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    job_queue = queue.Queue()
    jobs[job_id] = {
        "queue": job_queue,
        "results": [],
        "format": output_format,
        "input_dir": input_dir,
        "status": "running",
    }

    thread = threading.Thread(target=run_job, args=(job_id, input_dir, mode, dry_run), daemon=True)
    thread.start()
    jobs[job_id]["thread"] = thread

    return jsonify({"job_id": job_id, "status": "started"})


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        q = jobs[job_id]["queue"]
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("event") == "complete":
                    jobs[job_id]["status"] = "complete"
                    break
            except queue.Empty:
                # ハートビート
                yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    fmt = data.get("format", "csv")
    rows = data.get("results", [])

    # rows（dict配列）→ ProductResult に変換
    results = []
    for row in rows:
        r = ProductResult()
        for key, value in row.items():
            if hasattr(r, key):
                setattr(r, key, str(value))
        results.append(r)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "excel":
        # Excel出力
        tmp_path = Path(f"/tmp/watch_result_{timestamp}.xlsx")
        write_excel(results, tmp_path)
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f"result_{timestamp}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        # CSV出力
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(COLUMNS)
        for r in results:
            writer.writerow(r.to_row())

        mem = io.BytesIO()
        mem.write(output.getvalue().encode(CSV_ENCODING))
        mem.seek(0)

        return send_file(
            mem,
            as_attachment=True,
            download_name=f"result_{timestamp}.csv",
            mimetype="text/csv",
        )


@app.route("/api/category_names")
def api_category_names():
    m = get_mapper()
    return jsonify(m.category_name_map)


@app.route("/api/create_retry_folder", methods=["POST"])
def api_create_retry_folder():
    """失敗した商品の画像フォルダを再実行用フォルダにコピーする"""
    import shutil

    data = request.get_json()
    input_dir = data.get("input_dir", "")
    failed_numbers = data.get("failed_numbers", [])  # 管理番号のリスト

    if not input_dir or not failed_numbers:
        return jsonify({"error": "入力フォルダまたは失敗商品リストが空です"}), 400

    input_path = Path(input_dir)
    if not input_path.exists():
        return jsonify({"error": f"入力フォルダが見つかりません: {input_dir}"}), 400

    # 再実行用フォルダを作成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    retry_dir = Path(config.DEFAULT_OUTPUT_DIR) / f"retry_{timestamp}"
    retry_dir.mkdir(parents=True, exist_ok=True)

    # 失敗した管理番号に一致するフォルダを探してコピー
    failed_set = set(str(n) for n in failed_numbers)
    copied = []
    not_found = []

    for subdir in input_path.iterdir():
        if not subdir.is_dir():
            continue
        # フォルダ名の先頭数字が管理番号と一致するか
        import re
        match = re.match(r"^(\d+)", subdir.name)
        if match and match.group(1) in failed_set:
            dest = retry_dir / subdir.name
            try:
                shutil.copytree(subdir, dest)
                copied.append(subdir.name)
                failed_set.discard(match.group(1))
            except Exception as e:
                logger.error(f"フォルダコピー失敗: {subdir} → {e}")

    not_found = list(failed_set)

    return jsonify({
        "retry_dir": str(retry_dir),
        "copied": len(copied),
        "copied_folders": copied,
        "not_found": not_found,
    })


@app.route("/api/regenerate_title", methods=["POST"])
def api_regenerate_title():
    data = request.get_json()
    title = generate_title(
        title_prefix=data.get("title_prefix", ""),
        brand_en=data.get("brand_en", ""),
        brand_kana=data.get("brand_kana", ""),
        series_en=data.get("series_en", ""),
        series_kana=data.get("series_kana", ""),
        model_number=data.get("model_number", ""),
        dial_color=data.get("dial_color", ""),
        hand_count=data.get("hand_count", ""),
        case_shape=data.get("case_shape", ""),
        material=data.get("material", ""),
        water_resistance=data.get("water_resistance", ""),
        movement_type=data.get("movement_type", ""),
        additional_word=data.get("additional_word", ""),
    )
    return jsonify({"title": title})


@app.route("/api/apikey", methods=["GET"])
def api_get_apikey():
    """APIキーの設定状態を返す（キー自体は返さない）"""
    key = config.GEMINI_API_KEY
    if key:
        # マスク表示: 先頭4文字 + **** + 末尾4文字
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return jsonify({"has_key": True, "masked": masked})
    return jsonify({"has_key": False, "masked": ""})


@app.route("/api/apikey", methods=["POST"])
def api_set_apikey():
    """APIキーを.envファイルに保存し、現在のプロセスにも反映する"""
    import modules.ai_analyzer as ai_analyzer_module

    data = request.get_json()
    key = data.get("api_key", "").strip()
    if not key:
        return jsonify({"error": "APIキーが空です"}), 400

    # 現在のプロセスに反映
    config.GEMINI_API_KEY = key
    ai_analyzer_module.GEMINI_API_KEY = key
    os.environ["GEMINI_API_KEY"] = key

    # .envファイルに永続化
    env_path = Path(__file__).parent / ".env"
    try:
        # 既存の.envを読み込み、GEMINI_API_KEYの行を更新or追加
        lines = []
        key_found = False
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY=") or line.strip().startswith("GEMINI_API_KEY ="):
                        lines.append(f"GEMINI_API_KEY={key}\n")
                        key_found = True
                    else:
                        lines.append(line)
        if not key_found:
            lines.append(f"GEMINI_API_KEY={key}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.info("GEMINI_API_KEY を .env ファイルに保存しました")
    except Exception as e:
        logger.warning(f".env ファイルへの保存に失敗（メモリ上は反映済み）: {e}")

    masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    return jsonify({"status": "ok", "masked": masked})


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("腕時計AI自動解析システム - ブラウザUI版")
    logger.info("http://localhost:8080 でアクセスしてください")
    logger.info("=" * 60)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
