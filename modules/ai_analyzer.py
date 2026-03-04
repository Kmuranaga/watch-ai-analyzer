"""
AI解析エンジンモジュール
Claude Vision APIに画像を送信し、構造化データとして時計情報を取得する
"""

import base64
import json
import logging
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None

from config import (
    ANTHROPIC_API_KEY, AI_MODEL, AI_MAX_TOKENS, AI_TEMPERATURE,
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


def _call_api(prompt: str, image_path: Path) -> dict:
    """
    Claude Vision APIを呼び出し、JSONレスポンスを取得する。
    リトライ付き（指数バックオフ）。
    """
    if anthropic is None:
        raise ImportError(
            "anthropic パッケージが未インストールです。\n"
            "pip install anthropic でインストールしてください。"
        )

    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY が設定されていません。\n"
            "環境変数に設定してください: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    image_data, media_type = _encode_image(image_path)

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=AI_MODEL,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )

            # レスポンスからテキストを抽出
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text

            # JSONパース
            return _parse_json_response(text)

        except anthropic.RateLimitError:
            delay = API_RETRY_BASE_DELAY ** attempt
            logger.warning(f"レートリミット到達。{delay}秒後にリトライ (試行 {attempt}/{API_MAX_RETRIES})")
            time.sleep(delay)

        except anthropic.APIError as e:
            delay = API_RETRY_BASE_DELAY ** attempt
            logger.warning(f"APIエラー: {e}。{delay}秒後にリトライ (試行 {attempt}/{API_MAX_RETRIES})")
            time.sleep(delay)

        except json.JSONDecodeError as e:
            if attempt < API_MAX_RETRIES:
                logger.warning(f"JSON解析失敗: {e}。リトライ (試行 {attempt}/{API_MAX_RETRIES})")
            else:
                logger.error(f"JSON解析失敗（リトライ上限）: {e}")
                return {}

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


# === Batch API対応 ===

def _get_client() -> "anthropic.Anthropic":
    """Anthropicクライアントを生成する（共通処理）"""
    if anthropic is None:
        raise ImportError(
            "anthropic パッケージが未インストールです。\n"
            "pip install anthropic でインストールしてください。"
        )
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY が設定されていません。")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _build_request(custom_id: str, prompt: str, image_path: Path) -> dict:
    """1つのBatch APIリクエストを組み立てる"""
    image_data, media_type = _encode_image(image_path)
    return {
        "custom_id": custom_id,
        "params": {
            "model": AI_MODEL,
            "max_tokens": AI_MAX_TOKENS,
            "temperature": AI_TEMPERATURE,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        },
    }


def create_batch_requests(products: list) -> list[dict]:
    """
    Batch API用のリクエストリストを生成する。
    products は ProductImages のリスト。

    custom_id の命名規則:
      - "{product_id}__front"    → 正面画像解析
      - "{product_id}__back"     → 裏蓋画像解析
      - "{product_id}__comment1" → コメントシール1
      - "{product_id}__comment2" → コメントシール2
    （"__" ダブルアンダースコアで product_id とタイプを区切る）
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
    Batch APIにリクエストを送信する。

    Args:
        requests: create_batch_requests() で生成したリクエストリスト

    Returns:
        batch_id: バッチ処理のID
    """
    client = _get_client()

    logger.info(f"Batch APIに {len(requests)} リクエストを送信中...")
    batch = client.messages.batches.create(requests=requests)

    logger.info(
        f"Batch作成完了: id={batch.id}, "
        f"status={batch.processing_status}, "
        f"expires_at={batch.expires_at}"
    )
    return batch.id


def poll_batch(batch_id: str, poll_interval: int = 60) -> None:
    """
    Batch APIの処理完了をポーリングで待機する。

    Args:
        batch_id: バッチID
        poll_interval: ポーリング間隔（秒、デフォルト60秒）

    Raises:
        RuntimeError: バッチがキャンセル/期限切れの場合
    """
    client = _get_client()

    while True:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        counts = batch.request_counts

        logger.info(
            f"Batch {batch_id}: status={status}, "
            f"processing={counts.processing}, "
            f"succeeded={counts.succeeded}, "
            f"errored={counts.errored}, "
            f"canceled={counts.canceled}, "
            f"expired={counts.expired}"
        )

        if status == "ended":
            logger.info(f"Batch処理完了: {batch_id}")
            return

        if status in ("canceling", "canceled"):
            raise RuntimeError(f"Batchがキャンセルされました: {batch_id}")

        time.sleep(poll_interval)


def retrieve_batch_results(batch_id: str) -> dict[str, dict]:
    """
    Batch APIの結果を取得し、custom_id → パース済みJSONの辞書として返す。

    Args:
        batch_id: バッチID

    Returns:
        {custom_id: parsed_json_dict, ...}
        エラー/期限切れのリクエストは空辞書 {} が入る。
    """
    client = _get_client()
    results = {}

    for entry in client.messages.batches.results(batch_id):
        custom_id = entry.custom_id

        if entry.result.type == "succeeded":
            # レスポンスからテキストを抽出
            text = ""
            for block in entry.result.message.content:
                if block.type == "text":
                    text += block.text

            try:
                parsed = _parse_json_response(text)
            except json.JSONDecodeError as e:
                logger.error(f"[{custom_id}] JSON解析失敗: {e}")
                parsed = {}

            results[custom_id] = parsed

        elif entry.result.type == "errored":
            error = getattr(entry.result, "error", None)
            logger.error(f"[{custom_id}] APIエラー: {error}")
            results[custom_id] = {}

        elif entry.result.type == "expired":
            logger.warning(f"[{custom_id}] リクエスト期限切れ")
            results[custom_id] = {}

        elif entry.result.type == "canceled":
            logger.warning(f"[{custom_id}] リクエストキャンセル")
            results[custom_id] = {}

        else:
            logger.warning(f"[{custom_id}] 不明な結果タイプ: {entry.result.type}")
            results[custom_id] = {}

    logger.info(f"Batch結果取得完了: {len(results)}件")
    return results


def parse_batch_results_for_product(
    product_id: str,
    batch_results: dict[str, dict],
) -> tuple[dict, dict, dict]:
    """
    Batch結果辞書から、特定商品のfront/back/commentデータを取り出す。

    Args:
        product_id: 商品ID
        batch_results: retrieve_batch_results() の返り値

    Returns:
        (front_data, back_data, comment_data) のタプル
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
