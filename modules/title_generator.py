"""
タイトル生成モジュール
空白抜き65文字制限のヤフオクタイトルを生成する

※ヤフオクの文字数カウントは空白を含まないため、
  空白込みの実際の文字列はもっと長くなる。
  例: "SEIKO CHRONOGRAPH セイコー クォーツ ラウンド ブラック 3針 腕時計 7T32-9000"
      空白込み75文字 / 空白抜き62文字 → OK

構成要素の優先順位:
  1. ブランド英字（必須）
  2. ブランドカナ（必須）
  3. シリーズ英字（必須）
  4. シリーズカナ（必須）
  5. 型番（必須）
  6. 文字盤色（強制 - 削除しない）
  7. 針数（強制 - 削除しない）
  8. ケース形状（強制 - 削除しない）
  9. 素材（任意 - 削除優先3番目）
  10. 防水（任意 - 削除優先2番目）
  11. ムーブメント（任意 - 削除優先1番目）
"""

import logging

from config import TITLE_MAX_LENGTH

logger = logging.getLogger(__name__)


def _count_chars_no_spaces(text: str) -> int:
    """空白を除いた文字数を返す"""
    return len(text.replace(" ", "").replace("\u3000", ""))


def generate_title(
    brand_en: str = "",
    brand_kana: str = "",
    series_en: str = "",
    series_kana: str = "",
    model_number: str = "",
    dial_color: str = "",
    hand_count: str = "",
    case_shape: str = "",
    material: str = "",
    water_resistance: str = "",
    movement_type: str = "",
) -> str:
    """
    空白抜き65文字制限のタイトルを生成する。
    超過時は優先度の低い要素から削除する。
    文字盤色・針数・ケース形状は強制的に含め、削除対象にしない。

    Returns:
        生成されたタイトル文字列
    """
    # 必須要素（削除しない）
    required = [
        brand_en,
        brand_kana,
        series_en,
        series_kana,
        model_number,
    ]

    # 強制要素（削除しない: 文字盤色、針数、ケース形状）
    forced = [
        dial_color,
        hand_count,
        case_shape,
    ]

    # 任意要素（削除優先順: ムーブメント → 防水 → 素材）
    optional = [
        ("material", material),
        ("water_resistance", water_resistance),
        ("movement_type", movement_type),
    ]

    # 空文字の要素を除外して結合
    parts = [p for p in required if p]
    parts.extend([p for p in forced if p])

    # 任意要素を追加
    optional_parts = [(name, value) for name, value in optional if value]
    parts.extend([value for _, value in optional_parts])

    # タイトルを結合
    title = " ".join(parts)

    # 空白抜き65文字以下ならそのまま返す
    char_count = _count_chars_no_spaces(title)
    if char_count <= TITLE_MAX_LENGTH:
        logger.debug(f"タイトル生成: 空白抜き{char_count}文字 / 空白込み{len(title)}文字 - {title}")
        return title

    # 超過時: 任意要素を削除優先順に除去
    removal_order = ["movement_type", "water_resistance", "material"]

    for target in removal_order:
        optional_parts = [(n, v) for n, v in optional_parts if n != target]
        parts = [p for p in required if p] + [p for p in forced if p] + [v for _, v in optional_parts]
        title = " ".join(parts)
        char_count = _count_chars_no_spaces(title)

        if char_count <= TITLE_MAX_LENGTH:
            logger.debug(f"タイトル生成（{target}削除）: 空白抜き{char_count}文字 - {title}")
            return title

    # それでも超過する場合: 空白抜きで65文字に収まるよう末尾から削る
    while _count_chars_no_spaces(title) > TITLE_MAX_LENGTH and title:
        title = title[:-1]
    title = title.rstrip()
    logger.warning(f"タイトルを空白抜き{TITLE_MAX_LENGTH}文字に切り詰め: {title}")
    return title