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
        return {"abnormality_text": "", "abnormality_type": "", "confidence": {}}

    prompt = _load_prompt("comment_analysis.txt")
    all_texts = []
    all_types = []

    for image_path in image_paths:
        logger.info(f"コメントシール解析: {image_path}")
        result = _call_api(prompt, image_path)

        text = result.get("abnormality_text", "")
        atype = result.get("abnormality_type", "")
        if text:
            all_texts.append(text)
        if atype:
            all_types.append(atype)

    return {
        "abnormality_text": " / ".join(all_texts) if all_texts else "",
        "abnormality_type": ", ".join(all_types) if all_types else "",
        "confidence": result.get("confidence", {}) if image_paths else {},
    }


# === Batch API対応（Geminiでは逐次処理で代替） ===

def _build_request(custom_id: str, prompt: str, image_path: Path) -> dict:
    """1つのリクエスト情報を組み立てる"""
    return {
        "custom_id": custom_id,
        "prompt": prompt,
        "image_path": image_path,
    }


def create_batch_requests(products: list) -> list[dict]:
    """
    バッチ用のリクエストリストを生成する。
    products は ProductImages のリスト。
    """
    requests = []
    front_prompt = _load_prompt("front_analysis.txt")
    back_prompt = _load_prompt("back_analysis.txt")
    comment_prompt = _load_prompt("comment_analysis.txt")

    for product in products:
        pid = product.product_id

        if product.front_image:
            requests.append(_build_request(f"{pid}__front", front_prompt, product.front_image))

        if product.back_cover_image:
            requests.append(_build_request(f"{pid}__back", back_prompt, product.back_cover_image))

        for i, comment_img in enumerate(product.comment_images):
            requests.append(_build_request(f"{pid}__comment{i+1}", comment_prompt, comment_img))

    logger.info(f"Batchリクエスト生成完了: {len(requests)}件")
    return requests


def submit_batch(requests: list[dict]) -> str:
    """
    リクエストを逐次実行する（Geminiにはバッチ APIがないため）。
    結果は内部に保持し、batch_idとして"local"を返す。
    """
    logger.info(f"{len(requests)} リクエストを逐次処理中...")

    results = {}
    for i, req in enumerate(requests, 1):
        custom_id = req["custom_id"]
        logger.info(f"[{i}/{len(requests)}] 処理中: {custom_id}")
        try:
            parsed = _call_api(req["prompt"], req["image_path"])
            results[custom_id] = parsed
        except Exception as e:
            logger.error(f"[{custom_id}] エラー: {e}")
            results[custom_id] = {}

    # グローバルに結果を保持
    global _batch_results_store
    _batch_results_store = results

    logger.info(f"逐次処理完了: {len(results)}件")
    return "local"


# 逐次処理の結果を保持するストア
_batch_results_store: dict[str, dict] = {}


def poll_batch(batch_id: str, poll_interval: int = 60) -> None:
    """Geminiでは逐次処理のため、即座に完了"""
    logger.info("逐次処理モード: ポーリング不要（処理済み）")


def retrieve_batch_results(batch_id: str) -> dict[str, dict]:
    """逐次処理の結果を返す"""
    global _batch_results_store
    results = _batch_results_store
    _batch_results_store = {}
    logger.info(f"結果取得完了: {len(results)}件")
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
    last_confidence = {}

    for i in range(1, 3):  # comment1, comment2
        key = f"{product_id}__comment{i}"
        cdata = batch_results.get(key)
        if cdata:
            text = cdata.get("abnormality_text", "")
            atype = cdata.get("abnormality_type", "")
            if text:
                all_texts.append(text)
            if atype:
                all_types.append(atype)
            last_confidence = cdata.get("confidence", {})

    comment_data = {
        "abnormality_text": " / ".join(all_texts) if all_texts else "",
        "abnormality_type": ", ".join(all_types) if all_types else "",
        "confidence": last_confidence,
    }

    return front_data, back_data, comment_data
