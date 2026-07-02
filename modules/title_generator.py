"""
タイトル生成モジュール
各要素を結合してタイトルを生成する
"""

import logging

logger = logging.getLogger(__name__)


def generate_title(
    title_prefix: str = "",
    brand_en: str = "",
    brand_kana: str = "",
    series_en: str = "",
    series_kana: str = "",
    model_number: str = "",
    body_color: str = "",
    dial_color: str = "",  # タイトルには含めない（下記 parts を参照）。CSV出力には別途保持。
    hand_count: str = "",
    case_shape: str = "",
    material: str = "",
    water_resistance: str = "",
    movement_type: str = "",
    gender: str = "",
    additional_word: str = "",
) -> str:
    """
    全要素を結合してタイトルを生成する。

    Returns:
        生成されたタイトル文字列
    """
    # 文字盤色(dial_color)はタイトルに含めない。
    # 画質・主観に依存し精度が相対的に低い(≈87%)ため、タイトルからは除外し、
    # CSV等の出力結果にのみ表示する方針（本体色 body_color はタイトルに残す）。
    parts = [
        brand_en,
        brand_kana,
        series_en,
        series_kana,
        model_number,
        body_color,
        hand_count,
        case_shape,
        material,
        water_resistance,
        movement_type,
        gender,
        additional_word,
    ]

    # 空文字の要素を除外して結合
    title = " ".join(p for p in parts if p)

    # title_prefix を先頭に追加
    if title_prefix:
        title = f"{title_prefix} {title}"

    logger.debug(f"タイトル生成: {len(title)}文字 - {title}")
    return title