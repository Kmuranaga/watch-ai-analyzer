"""
AI解析エンジンモジュール
Gemini Vision APIに画像を送信し、構造化データとして時計情報を取得する
"""

import base64
import json
import logging
import time
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from config import (
    GEMINI_API_KEY, AI_MODEL, AI_MAX_TOKENS, AI_TEMPERATURE,
    PROMPTS_DIR, API_MAX_RETRIES, API_RETRY_BASE_DELAY,
)

logger = logging.getLogger(__name__)


def _load_prompt(filename: str) -> str:
    """プロンプトファイルを読み込む"""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def _encode_image(image_path: Path) -> tuple[str, str]:
    """画像をBase64エンコードし、メディアタイプを返す"""
    suffix = image_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }
    media_type = media_type_map.get(suffix, "image/jpeg")

    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    return data, media_type


def _get_client() -> "genai.Client":
    """Geminiクライアントを生成する（共通処理）"""
    if genai is None:
        raise ImportError(
            "google-genai パッケージが未インストールです。\n"
            "pip install google-genai でインストールしてください。"
        )
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
    return genai.Client(api_key=GEMINI_API_KEY)


def _call_api(prompt: str, image_path: Path) -> dict:
    """
    Gemini Vision APIを呼び出し、JSONレスポンスを取得する。
    リトライ付き（指数バックオフ）。
    """
    if genai is None:
        raise ImportError(
            "google-genai パッケージが未インストールです。\n"
            "pip install google-genai でインストールしてください。"
        )

    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY が設定されていません。\n"
            "環境変数に設定してください: export GEMINI_API_KEY=your-api-key"
        )

    client = _get_client()
    image_data, media_type = _encode_image(image_path)

    image_part = types.Part.from_bytes(
        data=base64.standard_b64decode(image_data),
        mime_type=media_type,
    )

    config = types.GenerateContentConfig(
        max_output_tokens=AI_MAX_TOKENS,
        temperature=AI_TEMPERATURE,
    )

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=AI_MODEL,
                contents=[image_part, prompt],
                config=config,
            )

            text = response.text
            if text is None:
                raise ValueError("APIレスポンスのテキストがNullです（画像の読み取りに失敗した可能性）")

            # JSONパース
            return _parse_json_response(text)

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "ResourceExhausted" in error_str:
                delay = API_RETRY_BASE_DELAY ** attempt
                logger.warning(f"レートリミット到達。{delay}秒後にリトライ (試行 {attempt}/{API_MAX_RETRIES})")
                time.sleep(delay)
            elif isinstance(e, json.JSONDecodeError):
                if attempt < API_MAX_RETRIES:
                    logger.warning(f"JSON解析失敗: {e}。リトライ (試行 {attempt}/{API_MAX_RETRIES})")
                else:
                    logger.error(f"JSON解析失敗（リトライ上限）: {e}")
                    return {}
            else:
                delay = API_RETRY_BASE_DELAY ** attempt
                logger.warning(f"APIエラー: {e}。{delay}秒後にリトライ (試行 {attempt}/{API_MAX_RETRIES})")
                time.sleep(delay)

    logger.error(f"API呼び出し失敗（リトライ上限到達）: {image_path}")
    return {}


def _parse_json_response(text: str) -> dict:
    """APIレスポンスのテキストからJSONを抽出・パースする"""
    text = text.strip()

    # ```json ... ``` ブロックを除去
    if text.startswith("```"):
        lines = text.split("\n")
        # 先頭行と末尾行を除去
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    return json.loads(text)


# === 各解析関数 ===

def analyze_front(image_path: Path) -> dict:
    """
    正面画像を解析し、ブランド・シリーズ・文字盤色・針数・ムーブメントを取得する。

    Returns:
        {
            "brand_en": str,
            "brand_kana": str,
            "series_en": str,
            "series_kana": str,
            "dial_color": str,
            "hand_count": str,
            "movement_type": str,
            "confidence": dict,
        }
    """
    logger.info(f"正面画像解析: {image_path}")
    prompt = _load_prompt("front_analysis.txt")
    result = _call_api(prompt, image_path)

    # デフォルト値の補完
    defaults = {
        "brand_en": "",
        "brand_kana": "",
        "series_en": "",
        "series_kana": "",
        "dial_color": "",
        "hand_count": "",
        "movement_type": "",
        "case_shape": "",
        "confidence": {},
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    return result


def analyze_back_cover(image_path: Path) -> dict:
    """
    裏蓋画像を解析し、型番・素材・防水性能を取得する。

    Returns:
        {
            "model_number": str,
            "material": str,
            "water_resistance": str,
            "confidence": dict,
        }
    """
    logger.info(f"裏蓋画像解析: {image_path}")
    prompt = _load_prompt("back_analysis.txt")
    result = _call_api(prompt, image_path)

    defaults = {
        "model_number": "",
        "material": "",
        "water_resistance": "",
        "confidence": {},
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    return result


def analyze_comment(image_paths: list[Path]) -> dict:
    """
    コメントシール画像を解析し、異常報告テキストを取得する。
    複数枚ある場合は結合する。

    Returns:
        {
            "abnormality_text": str,
            "abnormality_type": str,
            "confidence": dict,
        }
    """
    if not image_paths:
        return {"title_prefix": "", "abnormality_text": "", "abnormality_type": "", "confidence": {}}

    prompt = _load_prompt("comment_analysis.txt")
    all_texts = []
    all_types = []
    title_prefix = ""

    for image_path in image_paths:
        logger.info(f"コメントシール解析: {image_path}")
        result = _call_api(prompt, image_path)

        prefix = result.get("title_prefix", "")
        if prefix:
            title_prefix = prefix

        text = result.get("abnormality_text", "")
        atype = result.get("abnormality_type", "")
        if text:
            all_texts.append(text)
        if atype:
            all_types.append(atype)

    return {
        "title_prefix": title_prefix,
        "abnormality_text": " / ".join(all_texts) if all_texts else "",
        "abnormality_type": ", ".join(all_types) if all_types else "",
        "confidence": result.get("confidence", {}) if image_paths else {},
    }


# === Batch API対応 ===

def _build_batch_request(custom_id: str, prompt: str, image_path: Path) -> dict:
    """1つのBatch APIリクエストを組み立てる（InlinedRequest形式）"""
    image_data, media_type = _encode_image(image_path)
    image_bytes = base64.standard_b64decode(image_data)

    return {
        "metadata": {"custom_id": custom_id},
        "contents": [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                    types.Part.from_text(text=prompt),
                ],
            )
        ],
        "config": types.GenerateContentConfig(
            max_output_tokens=AI_MAX_TOKENS,
            temperature=AI_TEMPERATURE,
        ),
    }


def create_batch_requests(products: list) -> list[dict]:
    """
    Batch API用のリクエストリストを生成する。
    products は ProductImages のリスト。

    custom_id（key）の命名規則:
      - "{product_id}__front"    → 正面画像解析
      - "{product_id}__back"     → 裏蓋画像解析
      - "{product_id}__comment1" → コメントシール1
      - "{product_id}__comment2" → コメントシール2
    """
    requests = []
    front_prompt = _load_prompt("front_analysis.txt")
    back_prompt = _load_prompt("back_analysis.txt")
    comment_prompt = _load_prompt("comment_analysis.txt")

    for product in products:
        pid = product.product_id

        if product.front_image:
            requests.append(_build_batch_request(f"{pid}__front", front_prompt, product.front_image))

        if product.back_cover_image:
            requests.append(_build_batch_request(f"{pid}__back", back_prompt, product.back_cover_image))

        for i, comment_img in enumerate(product.comment_images):
            requests.append(_build_batch_request(f"{pid}__comment{i+1}", comment_prompt, comment_img))

    logger.info(f"Batchリクエスト生成完了: {len(requests)}件")
    return requests


def submit_batch(requests: list[dict]) -> str:
    """
    Gemini Batch APIにリクエストを送信する。

    Args:
        requests: create_batch_requests() で生成したリクエストリスト

    Returns:
        batch_name: バッチジョブの名前（例: "batches/xxx"）
    """
    client = _get_client()

    logger.info(f"Batch APIに {len(requests)} リクエストを送信中...")
    batch_job = client.batches.create(
        model=AI_MODEL,
        src=requests,
        config={
            "display_name": f"watch-analyzer-{int(time.time())}",
        },
    )

    logger.info(
        f"Batch作成完了: name={batch_job.name}, "
        f"state={batch_job.state}"
    )
    return batch_job.name


def poll_batch(batch_id: str, poll_interval: int = 60) -> None:
    """
    Batch APIの処理完了をポーリングで待機する。

    Args:
        batch_id: バッチジョブ名
        poll_interval: ポーリング間隔（秒、デフォルト60秒）

    Raises:
        RuntimeError: バッチが失敗/キャンセル/期限切れの場合
    """
    client = _get_client()
    completed_states = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED",
                        "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}

    while True:
        batch_job = client.batches.get(name=batch_id)
        state = batch_job.state.name if hasattr(batch_job.state, "name") else str(batch_job.state)

        logger.info(f"Batch {batch_id}: state={state}")

        if state in completed_states:
            if state == "JOB_STATE_SUCCEEDED":
                logger.info(f"Batch処理完了: {batch_id}")
                return
            else:
                raise RuntimeError(f"Batchが異常終了しました: {batch_id} (state={state})")

        time.sleep(poll_interval)


def retrieve_batch_results(batch_id: str) -> dict[str, dict]:
    """
    Batch APIの結果を取得し、key → パース済みJSONの辞書として返す。

    Args:
        batch_id: バッチジョブ名

    Returns:
        {custom_id: parsed_json_dict, ...}
    """
    client = _get_client()
    results = {}

    batch_job = client.batches.get(name=batch_id)

    if batch_job.dest and hasattr(batch_job.dest, "inlined_responses") and batch_job.dest.inlined_responses:
        for entry in batch_job.dest.inlined_responses:
            # metadataからcustom_idを取得
            key = None
            if hasattr(entry, "metadata") and entry.metadata:
                key = entry.metadata.get("custom_id")
            if not key:
                continue

            if hasattr(entry, "response") and entry.response:
                try:
                    text = entry.response.candidates[0].content.parts[0].text
                    parsed = _parse_json_response(text)
                    results[key] = parsed
                except (IndexError, AttributeError, json.JSONDecodeError) as e:
                    logger.error(f"[{key}] 結果解析失敗: {e}")
                    results[key] = {}
            elif hasattr(entry, "error") and entry.error:
                logger.error(f"[{key}] APIエラー: {entry.error}")
                results[key] = {}
            else:
                logger.warning(f"[{key}] 不明な結果")
                results[key] = {}

    elif batch_job.dest and hasattr(batch_job.dest, "file_name") and batch_job.dest.file_name:
        # ファイル出力の場合
        file_content = client.files.download(file=batch_job.dest.file_name)
        import io
        for line in io.StringIO(file_content.decode("utf-8")):
            line = line.strip()
            if not line:
                continue
            try:
                entry_data = json.loads(line)
                key = entry_data.get("metadata", {}).get("custom_id", "")
                response = entry_data.get("response", {})
                text = response.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    results[key] = _parse_json_response(text)
                else:
                    results[key] = {}
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                logger.error(f"Batch結果行の解析失敗: {e}")

    logger.info(f"Batch結果取得完了: {len(results)}件")
    return results


def parse_batch_results_for_product(
    product_id: str,
    batch_results: dict[str, dict],
) -> tuple[dict, dict, dict]:
    """
    結果辞書から、特定商品のfront/back/commentデータを取り出す。
    """
    front_data = batch_results.get(f"{product_id}__front", {})
    back_data = batch_results.get(f"{product_id}__back", {})

    # コメントデータ: comment1, comment2 を結合
    all_texts = []
    all_types = []
    title_prefix = ""
    last_confidence = {}

    for i in range(1, 3):  # comment1, comment2
        key = f"{product_id}__comment{i}"
        cdata = batch_results.get(key)
        if cdata:
            prefix = cdata.get("title_prefix", "")
            if prefix:
                title_prefix = prefix
            text = cdata.get("abnormality_text", "")
            atype = cdata.get("abnormality_type", "")
            if text:
                all_texts.append(text)
            if atype:
                all_types.append(atype)
            last_confidence = cdata.get("confidence", {})

    comment_data = {
        "title_prefix": title_prefix,
        "abnormality_text": " / ".join(all_texts) if all_texts else "",
        "abnormality_type": ", ".join(all_types) if all_types else "",
        "confidence": last_confidence,
    }

    return front_data, back_data, comment_data
