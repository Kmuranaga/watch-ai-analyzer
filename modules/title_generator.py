"""
タイトル生成モジュール
65文字制限のヤフオクタイトルを生成する

構成要素の優先順位:
  1. ブランド英字（必須）
  2. ブランドカナ（必須）
  3. シリーズ英字（必須）
  4. シリーズカナ（必須）
  5. 型番（必須）
  6. 素材（任意 - 削除優先3番目）
  7. 防水（任意 - 削除優先2番目）
  8. ムーブメント（任意 - 削除優先1番目）
"""

import logging

from config import TITLE_MAX_LENGTH

logger = logging.getLogger(__name__)


def generate_title(
    brand_en: str = "",
    brand_kana: str = "",
    series_en: str = "",
    series_kana: str = "",
    model_number: str = "",
    material: str = "",
    water_resistance: str = "",
    movement_type: str = "",
) -> str:
    """
    65文字制限のタイトルを生成する。
    超過時は優先度の低い要素から削除する。

    Returns:
        生成されたタイトル文字列
    """
    # 必須要素
    required = [
        brand_en,
        brand_kana,
        series_en,
        series_kana,
        model_number,
    ]

    # 任意要素（削除優先順: ムーブメント → 防水 → 素材）
    optional = [
        ("material", material),
        ("water_resistance", water_resistance),
        ("movement_type", movement_type),
    ]

    # 空文字の必須要素を除外
    parts = [p for p in required if p]

    # 任意要素を追加
    optional_parts = [(name, value) for name, value in optional if value]
    parts.extend([value for _, value in optional_parts])

    # タイトルを結合
    title = " ".join(parts)

    # 65文字以下ならそのまま返す
    if len(title) <= TITLE_MAX_LENGTH:
        logger.debug(f"タイトル生成: {len(title)}文字 - {title}")
        return title

    # 超過時: 任意要素を削除優先順に除去
    # 削除順: ムーブメント(1番目) → 防水(2番目) → 素材(3番目)
    removal_order = ["movement_type", "water_resistance", "material"]

    for target in removal_order:
        optional_parts = [(n, v) for n, v in optional_parts if n != target]
        parts = [p for p in required if p] + [v for _, v in optional_parts]
        title = " ".join(parts)

        if len(title) <= TITLE_MAX_LENGTH:
            logger.debug(f"タイトル生成（{target}削除）: {len(title)}文字 - {title}")
            return title

    # それでも超過する場合: 先頭から65文字で切り詰め
    title = title[:TITLE_MAX_LENGTH]
    logger.warning(f"タイトルを{TITLE_MAX_LENGTH}文字に切り詰め: {title}")
    return title
