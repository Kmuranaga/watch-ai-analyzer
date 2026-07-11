"""
AI解析エンジンモジュール
Gemini Vision APIに画像を送信し、構造化データとして時計情報を取得する
"""

import base64
import json
import logging
import threading
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
    PROMPTS_DIR, API_MAX_RETRIES, API_RETRY_BASE_DELAY, API_RETRY_MAX_DELAY,
)

logger = logging.getLogger(__name__)

# === グローバルレートリミッター ===
# 429発生時に全スレッドを一斉に待機させる
_rate_limit_lock = threading.Lock()
_rate_limit_until = 0.0  # このUNIX時刻まで全スレッド待機

# === レートリミット通知コールバック ===
# 外部（app.py等）から登録して、レートリミット発生時にUI通知を受け取る
_rate_limit_callbacks: list = []


def register_rate_limit_callback(callback):
    """
    レートリミット発生時に呼ばれるコールバックを登録する。

    callback(event_type, detail):
        event_type: "rate_limit_hit" | "rate_limit_waiting" | "rate_limit_retry_exhausted"
        detail: dict with keys like attempt, max_retries, delay, image_path
    """
    _rate_limit_callbacks.append(callback)


def _notify_rate_limit(event_type: str, detail: dict):
    """登録済みコールバックに通知"""
    for cb in _rate_limit_callbacks:
        try:
            cb(event_type, detail)
        except Exception:
            pass


def _load_prompt(filename: str) -> str:
    """プロンプトファイルを読み込む"""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {path}")
    return path.read_text(encoding="utf-8")


def _load_comment_prompt() -> str:
    """コメント解析プロンプトを読み込み、針数ラベル定義を注入する。"""
    from modules.hand_count_policy import labels_for_prompt
    return _load_prompt("comment_analysis.txt").replace("{HAND_COUNT_LABELS}", labels_for_prompt())


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


def _wait_for_rate_limit():
    """グローバルレートリミットの待機が必要なら待つ"""
    global _rate_limit_until
    now = time.time()
    if now < _rate_limit_until:
        wait = _rate_limit_until - now
        logger.info(f"レートリミット待機中... {wait:.1f}秒")
        time.sleep(wait)


def _set_rate_limit_cooldown(delay: float):
    """全スレッドに対してレートリミットのクールダウンを設定"""
    global _rate_limit_until
    with _rate_limit_lock:
        new_until = time.time() + delay
        if new_until > _rate_limit_until:
            _rate_limit_until = new_until


def _call_api(prompt: str, image_path: Path, extra_images: list[Path] | None = None) -> dict:
    """
    Gemini Vision APIを呼び出し、JSONレスポンスを取得する（画像パス入力）。
    リトライ付き（指数バックオフ + グローバルレートリミッター）。

    Args:
        prompt: プロンプトテキスト
        image_path: メイン画像パス
        extra_images: 追加画像パスのリスト（任意）
    """
    # メイン画像（APIキー/genai 未設定の検証は _call_api_core で行う）
    image_data, media_type = _encode_image(image_path)
    image_parts = [
        types.Part.from_bytes(
            data=base64.standard_b64decode(image_data),
            mime_type=media_type,
        )
    ]

    # 追加画像
    if extra_images:
        for extra_path in extra_images:
            extra_data, extra_media_type = _encode_image(extra_path)
            image_parts.append(
                types.Part.from_bytes(
                    data=base64.standard_b64decode(extra_data),
                    mime_type=extra_media_type,
                )
            )

    return _call_api_core(prompt, image_parts, label=image_path.name)


def _call_api_bytes(prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg",
                    label: str = "cropped") -> dict:
    """
    Gemini Vision APIを呼び出す（画像バイト列入力）。クロップ画像など、
    一時ファイルを作らずメモリ上の画像を送るために使う。
    """
    image_parts = [types.Part.from_bytes(data=image_bytes, mime_type=mime_type)]
    return _call_api_core(prompt, image_parts, label=label)


def _call_text_api(prompt: str, label: str = "text") -> dict:
    """画像なしのテキストプロンプトで Gemini を呼び、JSON を返す（分類等に使う）。"""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
    return _call_api_core(prompt, [], label=label)


def _call_api_core(prompt: str, image_parts: list, label: str) -> dict:
    """画像パーツ列とプロンプトから JSON レスポンスを取得する共通リトライ処理。"""
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

    config = types.GenerateContentConfig(
        max_output_tokens=AI_MAX_TOKENS,
        temperature=AI_TEMPERATURE,
    )

    for attempt in range(1, API_MAX_RETRIES + 1):
        # 他スレッドが設定したレートリミット待機
        _wait_for_rate_limit()

        try:
            response = client.models.generate_content(
                model=AI_MODEL,
                contents=[*image_parts, prompt],
                config=config,
            )

            text = response.text
            if text is None:
                raise ValueError("APIレスポンスのテキストがNullです（画像の読み取りに失敗した可能性）")

            # JSONパース
            return _parse_json_response(text)

        except Exception as e:
            error_str = str(e)
            # APIキー不正・認証エラー → リトライ不要、即座に通知して中断
            if any(keyword in error_str for keyword in ("400", "401", "403", "API_KEY_INVALID", "PermissionDenied", "INVALID_ARGUMENT")):
                logger.error(f"APIキーエラー: {e}")
                _notify_rate_limit("api_key_error", {
                    "error": error_str,
                    "image_path": str(label),
                })
                return {}
            if "429" in error_str or "ResourceExhausted" in error_str:
                delay = min(API_RETRY_BASE_DELAY * (2 ** (attempt - 1)), API_RETRY_MAX_DELAY)
                logger.warning(f"レートリミット到達。{delay}秒後にリトライ (試行 {attempt}/{API_MAX_RETRIES}) - {label}")
                _notify_rate_limit("rate_limit_hit", {
                    "attempt": attempt,
                    "max_retries": API_MAX_RETRIES,
                    "delay": delay,
                    "image_path": str(label),
                })
                _set_rate_limit_cooldown(delay)
                time.sleep(delay)
            elif isinstance(e, json.JSONDecodeError):
                if attempt < API_MAX_RETRIES:
                    logger.warning(f"JSON解析失敗: {e}。リトライ (試行 {attempt}/{API_MAX_RETRIES})")
                else:
                    logger.error(f"JSON解析失敗（リトライ上限）: {e}")
                    return {}
            else:
                delay = min(API_RETRY_BASE_DELAY * (2 ** (attempt - 1)), API_RETRY_MAX_DELAY)
                logger.warning(f"APIエラー: {e}。{delay}秒後にリトライ (試行 {attempt}/{API_MAX_RETRIES})")
                time.sleep(delay)

    logger.error(f"API呼び出し失敗（リトライ上限到達）: {label}")
    _notify_rate_limit("rate_limit_retry_exhausted", {
        "image_path": str(label),
    })
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

def analyze_front(image_path: Path, diagonal_image_path: Path | None = None) -> dict:
    """
    正面画像を解析し、ブランド・シリーズ・文字盤色・針数・ムーブメントを取得する。
    2枚目（斜め画像）が渡された場合、バンド形状等からgender判定の精度を向上させる。

    Returns:
        {
            "brand_en": str,
            "brand_kana": str,
            "series_en": str,
            "series_kana": str,
            "body_color": str,
            "dial_color": str,
            "hand_count": str,
            "movement_type": str,
            "case_shape": str,
            "gender": str,
            "confidence": dict,
        }
    """
    logger.info(f"正面画像解析: {image_path}")
    if diagonal_image_path:
        logger.info(f"斜め画像も使用: {diagonal_image_path}")
    prompt = _load_prompt("front_analysis.txt")
    extra_images = [diagonal_image_path] if diagonal_image_path else None
    result = _call_api(prompt, image_path, extra_images=extra_images)

    # デフォルト値の補完
    defaults = {
        "brand_en": "",
        "brand_kana": "",
        "series_en": "",
        "series_kana": "",
        "body_color": "",
        "dial_color": "",
        "hand_count": "",
        "movement_type": "",
        "case_shape": "",
        "gender": "",
        "confidence": {},
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    return result


def analyze_back_cover(image_path: Path) -> dict:
    """
    裏蓋画像を解析し、型番・素材・防水性能・裏蓋刻印ブランドを取得する。

    裏蓋ブランド/シリーズは front を上書きしないよう back_ 接頭辞の別キーで返す。
    （正面・裏蓋の整合判定は normalizer.reconcile_brand / normalize_all で行う）

    Returns:
        {
            "model_number": str,
            "material": str,
            "water_resistance": str,
            "back_brand_en": str,
            "back_brand_kana": str,
            "back_series_en": str,
            "back_series_kana": str,
            "back_confidence": dict,
        }
    """
    logger.info(f"裏蓋画像解析: {image_path}")
    prompt = _load_prompt("back_analysis.txt")
    result = _call_api(prompt, image_path)

    defaults = {
        "model_number": "",
        "material": "",
        "water_resistance": "",
        "back_brand_en": "",
        "back_brand_kana": "",
        "back_series_en": "",
        "back_series_kana": "",
        "back_confidence": {},
    }
    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    return result


def verify_back_brand_choice(back_image_path: Path, front_brand: str, back_brand: str) -> str:
    """裏蓋の刻印がどちらのブランドかを二択で照合する（幻覚検出用）。

    自由読み（analyze_back_cover）はムーブメント刻印等から実在しないブランドを
    一貫して幻覚することがある（例: BINLUN の裏蓋を KENTEX と誤読）。候補を提示した
    照合タスクにすると文字パターンの突き合わせになり、誤りにくい。

    Returns:
        "front" / "back" / "unknown"（判定不能・API失敗時は "unknown"）
    """
    prompt = (
        "この腕時計の裏蓋画像を注意深く見てください。ケースまたは裏蓋に実際に刻印されている"
        "「製品ブランド名」は、次のどれですか。ムーブメント製造元（MIYOTA等）や機能語・"
        "数字は無視してください。\n"
        f"A: {front_brand}\n"
        f"B: {back_brand}\n"
        "C: どちらの文字も刻印されていない／判読不能\n"
        '出力は厳密にJSONのみ: {"answer": "A|B|C", "engraved_text": "実際に見えた文字"}'
    )
    try:
        result = _call_api(prompt, back_image_path)
    except Exception:
        return "unknown"
    answer = str(result.get("answer", "")).strip().upper()
    if answer == "A":
        return "front"
    if answer == "B":
        return "back"
    return "unknown"


def analyze_comment(image_paths: list[Path]) -> dict:
    """
    コメントシール画像を解析し、異常報告テキスト・針数コメントを取得する。
    複数枚ある場合は結合する（針数コメントは最初の非空値を採用）。

    Returns:
        {
            "abnormality_text": str,
            "abnormality_type": str,
            "hand_count_comment": str,
            "confidence": dict,
        }
    """
    if not image_paths:
        return {"title_prefix": "", "abnormality_text": "", "abnormality_type": "",
                "hand_count_comment": "", "confidence": {}}

    prompt = _load_comment_prompt()
    all_prefixes = []
    all_texts = []
    all_types = []
    hand_count_comment = ""

    for image_path in image_paths:
        logger.info(f"コメントシール解析: {image_path}")
        result = _call_api(prompt, image_path)

        # ＃コメントは複数枚あっても全て採用（連結）
        prefix = result.get("title_prefix", "")
        if prefix:
            all_prefixes.append(prefix)

        text = result.get("abnormality_text", "")
        atype = result.get("abnormality_type", "")
        if text:
            all_texts.append(text)
        if atype:
            all_types.append(atype)

        hcc = result.get("hand_count_comment", "")
        if hcc and not hand_count_comment:
            hand_count_comment = hcc

    return {
        "title_prefix": " ".join(all_prefixes) if all_prefixes else "",
        "abnormality_text": " / ".join(all_texts) if all_texts else "",
        "abnormality_type": ", ".join(all_types) if all_types else "",
        "hand_count_comment": hand_count_comment,
        "confidence": result.get("confidence", {}) if image_paths else {},
    }


# 針数専用パスのクロップ倍率（短辺比）。複数倍率で針数を取り「少ない本数」を採用する。
# モデルは過剰検出が run ごとに揺れる（temp0でも）ため、倍率を増やすほど 2針 読みを
# 捕捉しやすい。実測（0.60/0.55/0.50/0.45）でクリーンな過剰検出3件を是正し、本物の
# 3針は全16観測で 3針 を維持（タイトな0.45でも回帰なし）。
HAND_COUNT_CROP_FRACS = (0.60, 0.55, 0.50, 0.45)


def analyze_hand_count_cropped(front_image_path: Path,
                               fracs: tuple = HAND_COUNT_CROP_FRACS) -> dict:
    """文字盤を複数倍率でクロップ＋拡大し針数を判定、最も少ない本数を採用する。

    正面解析の過剰検出（2針→3針）を抑制するための独立パス。各クロップに対し
    正面解析プロンプトで針数を取得し、fewest_hand_count で最少本数を返す。

    Returns:
        {"hand_count": str, "per_crop": {frac: hand_count}}
    """
    from modules.image_preprocess import crop_dial_to_bytes
    from modules.normalizer import normalize_hand_count, fewest_hand_count

    prompt = _load_prompt("front_analysis.txt")
    per_crop = {}
    counts = []
    for frac in fracs:
        image_bytes = crop_dial_to_bytes(front_image_path, frac)
        result = _call_api_bytes(prompt, image_bytes,
                                 label=f"{front_image_path.name}#crop{frac}")
        hc = normalize_hand_count(result.get("hand_count", ""))
        per_crop[str(frac)] = hc
        counts.append(hc)

    return {"hand_count": fewest_hand_count(counts), "per_crop": per_crop}


# 型番リカバリ設定（初回の裏蓋読みで型番が空だった時のみ発火）
MODEL_RECOVERY_SCALE = 2     # 裏蓋を拡大する倍率
MODEL_RECOVERY_SAMPLES = 3   # 拡大画像を読む回数（多数決）


def recover_model_number_upscaled(back_image_path: Path,
                                  k: int = MODEL_RECOVERY_SAMPLES,
                                  scale: int = MODEL_RECOVERY_SCALE) -> str:
    """裏蓋を拡大して k 回読み、型番の最頻非空値を返す。

    初回の裏蓋解析で型番が空だった商品のリカバリ用。刻印は読めるのに単発だと空に
    なるジッター（例: 2924286）を、拡大＋多数決で回収する。読めなければ空を返す。
    """
    from modules.image_preprocess import upscale_to_bytes
    from modules.normalizer import normalize_model_number, majority_nonempty

    prompt = _load_prompt("back_analysis.txt")
    reads = []
    for _ in range(k):
        data = upscale_to_bytes(back_image_path, scale)
        r = _call_api_bytes(prompt, data, label=f"{back_image_path.name}#up{scale}")
        reads.append(normalize_model_number(r.get("model_number", "")))
    return majority_nonempty(reads)


def classify_series_is_slogan(series: str) -> bool:
    """シリーズ文字列が英語の慣用句/スローガンか（True）、シリーズ・商品名か（False）を判定する。

    複合スローガンフィルタの意味判定ゲート。純英字3語以上の「候補」に対してのみ呼ぶ想定。
    実在シリーズ（例 Seven Star Deluxe, Lord Matic Special）を誤って消さないよう、
    判断に迷う場合・API失敗時は False（＝シリーズ名として保持）に倒す。
    """
    if not series:
        return False
    prompt = (
        "次の文字列は腕時計の文字盤や裏蓋から読み取ったものです。これが\n"
        "(A) 英語として意味の通る一般的な慣用句・宣伝文句（スローガン）なのか、\n"
        "(B) 時計のシリーズ名・商品名（固有名詞）なのか、を判定してください。\n"
        "重要: 判断に少しでも迷う場合は必ず B（name）と答えること。"
        "実在するシリーズ名（例: Seven Star Deluxe, Lord Matic Special 等、"
        "商品名として不自然でない造語の並び）を誤ってスローガンと判定してはいけません。\n"
        "スローガンの例: MOST VALUABLE PLAYER（一般的な慣用句）。\n"
        '出力は厳密にJSONのみ: {"type": "phrase"} または {"type": "name"}\n\n'
        f'文字列: "{series}"'
    )
    try:
        result = _call_text_api(prompt, label=f"slogan:{series[:20]}")
    except Exception:
        return False
    return str(result.get("type", "")).strip().lower() == "phrase"


# === Batch API対応 ===

def _build_batch_request(custom_id: str, prompt: str, image_path: Path, extra_images: list[Path] | None = None) -> dict:
    """1つのBatch APIリクエストを組み立てる（InlinedRequest形式）"""
    image_data, media_type = _encode_image(image_path)
    image_bytes = base64.standard_b64decode(image_data)

    parts = [types.Part.from_bytes(data=image_bytes, mime_type=media_type)]

    if extra_images:
        for extra_path in extra_images:
            extra_data, extra_media_type = _encode_image(extra_path)
            extra_bytes = base64.standard_b64decode(extra_data)
            parts.append(types.Part.from_bytes(data=extra_bytes, mime_type=extra_media_type))

    parts.append(types.Part.from_text(text=prompt))

    return {
        "metadata": {"custom_id": custom_id},
        "contents": [
            types.Content(
                role="user",
                parts=parts,
            )
        ],
        "config": types.GenerateContentConfig(
            max_output_tokens=AI_MAX_TOKENS,
            temperature=AI_TEMPERATURE,
        ),
    }


def _build_batch_request_bytes(custom_id: str, prompt: str, image_bytes: bytes,
                               mime_type: str = "image/jpeg") -> dict:
    """1つのBatch APIリクエストを画像バイト列から組み立てる（クロップ画像用）。"""
    parts = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        types.Part.from_text(text=prompt),
    ]
    return {
        "metadata": {"custom_id": custom_id},
        "contents": [
            types.Content(
                role="user",
                parts=parts,
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
      - "{product_id}__comment1"〜"__commentN" → コメントシール（最大 COMMENT_IMAGE_COUNT 枚）
    """
    requests = []
    front_prompt = _load_prompt("front_analysis.txt")
    back_prompt = _load_prompt("back_analysis.txt")
    comment_prompt = _load_comment_prompt()

    for product in products:
        pid = product.product_id

        if product.front_image:
            extra = [product.diagonal_image] if product.diagonal_image else None
            requests.append(_build_batch_request(f"{pid}__front", front_prompt, product.front_image, extra_images=extra))

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

    # コメントデータ: comment1〜commentN を結合（＃コメント複数枚は連結・針数は最初の非空値）
    from config import COMMENT_IMAGE_COUNT
    all_prefixes = []
    all_texts = []
    all_types = []
    hand_count_comment = ""
    last_confidence = {}

    for i in range(1, COMMENT_IMAGE_COUNT + 1):
        key = f"{product_id}__comment{i}"
        cdata = batch_results.get(key)
        if cdata:
            prefix = cdata.get("title_prefix", "")
            if prefix:
                all_prefixes.append(prefix)
            text = cdata.get("abnormality_text", "")
            atype = cdata.get("abnormality_type", "")
            if text:
                all_texts.append(text)
            if atype:
                all_types.append(atype)
            hcc = cdata.get("hand_count_comment", "")
            if hcc and not hand_count_comment:
                hand_count_comment = hcc
            last_confidence = cdata.get("confidence", {})

    comment_data = {
        "title_prefix": " ".join(all_prefixes) if all_prefixes else "",
        "abnormality_text": " / ".join(all_texts) if all_texts else "",
        "abnormality_type": ", ".join(all_types) if all_types else "",
        "hand_count_comment": hand_count_comment,
        "confidence": last_confidence,
    }

    return front_data, back_data, comment_data


def parse_hand_count_result_for_product(
    product_id: str,
    batch_results: dict[str, dict],
) -> dict:
    """結果辞書から特定商品の針数専用パス（クロップ別）の結果をまとめ、
    最も少ない本数を採用して返す（無ければ空dict）。

    Returns:
        {"hand_count": str, "per_crop": {key: hand_count}} または {}
    """
    from modules.normalizer import normalize_hand_count, fewest_hand_count

    per_crop = {}
    counts = []
    for i in range(len(HAND_COUNT_CROP_FRACS)):
        key = f"{product_id}__hand_c{i}"
        cdata = batch_results.get(key)
        if cdata:
            hc = normalize_hand_count(cdata.get("hand_count", ""))
            per_crop[key] = hc
            counts.append(hc)

    if not counts:
        return {}
    return {"hand_count": fewest_hand_count(counts), "per_crop": per_crop}
