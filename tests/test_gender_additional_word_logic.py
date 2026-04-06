"""
性別・追加単語の決定ロジックのテスト

仕様書の6項目を検証:
1. 性別の追記位置 → additional_word の直前
2. ブランドあり＆マッピング性別空 → 何も追記しない
3. ブランドなし＆性別「不明」→ 追記しない / 判別できた → 追記
4. 汎用カテゴリに追加単語列がある
5. ブランドなし時の順番: 性別 → 追加単語
6. ブランドあり → ブランド別マッピングの追加単語のみ使用
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.title_generator import generate_title


def determine_title_gender_and_additional_word(
    match_level: str,
    matched_entry: dict | None,
    ai_gender: str,
    mapper_get_additional_word_result: str,
) -> tuple[str, str]:
    """
    app.py / main.py に3回重複しているロジックを再現。
    テスト対象はこのロジックそのもの。
    """
    if match_level in ("model_number", "brand+series", "brand_only"):
        title_gender = matched_entry.get("gender", "") if matched_entry else ""
        additional_word = mapper_get_additional_word_result
    elif match_level == "generic" and matched_entry:
        title_gender = ai_gender if ai_gender and ai_gender != "不明" else ""
        additional_word = matched_entry.get("additional_word", "")
    else:
        title_gender = ai_gender if ai_gender and ai_gender != "不明" else ""
        additional_word = ""
    return title_gender, additional_word


class TestBrandMatchGenderLogic:
    """仕様1-Q2: ブランドあり時の性別決定"""

    def test_brand_match_gender_present(self):
        """マッピングに性別あり → その性別を使用"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="brand+series",
            matched_entry={"gender": "メンズ", "additional_word": ""},
            ai_gender="レディース",  # AI結果は無視される
            mapper_get_additional_word_result="",
        )
        assert gender == "メンズ"

    def test_brand_match_gender_empty(self):
        """仕様1-Q2: マッピングの性別が空 → 何も追記しない"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="brand+series",
            matched_entry={"gender": "", "additional_word": ""},
            ai_gender="メンズ",  # AI結果があっても無視
            mapper_get_additional_word_result="",
        )
        assert gender == ""

    def test_brand_only_gender(self):
        """ブランドのみ一致でも同じルール"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="brand_only",
            matched_entry={"gender": "レディース"},
            ai_gender="",
            mapper_get_additional_word_result="",
        )
        assert gender == "レディース"

    def test_model_number_match_gender(self):
        """型番一致でも同じルール"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="model_number",
            matched_entry={"gender": ""},
            ai_gender="メンズ",
            mapper_get_additional_word_result="",
        )
        assert gender == ""


class TestGenericGenderLogic:
    """仕様1-Q3: ブランドなし（汎用カテゴリ）時の性別決定"""

    def test_generic_gender_known(self):
        """ブランドなし＆性別判別できた → AI性別を追記"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="generic",
            matched_entry={"gender": "メンズ", "additional_word": "腕時計"},
            ai_gender="メンズ",
            mapper_get_additional_word_result="",
        )
        assert gender == "メンズ"

    def test_generic_gender_unknown(self):
        """仕様1-Q3: ブランドなし＆性別「不明」→ 追記しない"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="generic",
            matched_entry={"gender": "", "additional_word": "腕時計"},
            ai_gender="不明",
            mapper_get_additional_word_result="",
        )
        assert gender == ""

    def test_generic_gender_empty(self):
        """ブランドなし＆AI性別が空 → 追記しない"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="generic",
            matched_entry={"gender": "", "additional_word": ""},
            ai_gender="",
            mapper_get_additional_word_result="",
        )
        assert gender == ""

    def test_unknown_level_gender_known(self):
        """unknown レベルでも性別判別時は追記"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="unknown",
            matched_entry=None,
            ai_gender="レディース",
            mapper_get_additional_word_result="",
        )
        assert gender == "レディース"

    def test_unknown_level_gender_unknown(self):
        """unknown レベルで性別「不明」→ 追記しない"""
        gender, _ = determine_title_gender_and_additional_word(
            match_level="unknown",
            matched_entry=None,
            ai_gender="不明",
            mapper_get_additional_word_result="",
        )
        assert gender == ""


class TestAdditionalWordLogic:
    """仕様2: 追加単語の決定ロジック"""

    def test_brand_match_uses_brand_additional_word(self):
        """仕様2-Q3: ブランドあり → ブランド別マッピングの追加単語"""
        _, word = determine_title_gender_and_additional_word(
            match_level="brand+series",
            matched_entry={"gender": "", "additional_word": "ENTRY_WORD"},
            ai_gender="",
            mapper_get_additional_word_result="BRAND_WORD",
        )
        # get_additional_word の結果を使う（汎用カテゴリの値ではない）
        assert word == "BRAND_WORD"

    def test_generic_uses_generic_additional_word(self):
        """仕様2-Q1: ブランドなし → 汎用カテゴリの追加単語"""
        _, word = determine_title_gender_and_additional_word(
            match_level="generic",
            matched_entry={"gender": "メンズ", "additional_word": "腕時計"},
            ai_gender="メンズ",
            mapper_get_additional_word_result="SHOULD_NOT_USE",
        )
        assert word == "腕時計"

    def test_unknown_no_additional_word(self):
        """unknown → 追加単語なし"""
        _, word = determine_title_gender_and_additional_word(
            match_level="unknown",
            matched_entry=None,
            ai_gender="",
            mapper_get_additional_word_result="",
        )
        assert word == ""

    def test_model_number_uses_brand_additional_word(self):
        """型番一致でもブランド別追加単語を使用"""
        _, word = determine_title_gender_and_additional_word(
            match_level="model_number",
            matched_entry={"gender": "メンズ", "additional_word": ""},
            ai_gender="",
            mapper_get_additional_word_result="腕時計",
        )
        assert word == "腕時計"


class TestTitleIntegration:
    """仕様2-Q2: タイトル生成時の性別→追加単語の順序（統合テスト）"""

    def test_generic_gender_then_additional_word(self):
        """ブランドなし: ...クォーツ メンズ 腕時計 の順"""
        gender, additional_word = determine_title_gender_and_additional_word(
            match_level="generic",
            matched_entry={"gender": "メンズ", "additional_word": "腕時計"},
            ai_gender="メンズ",
            mapper_get_additional_word_result="",
        )
        title = generate_title(
            movement_type="クォーツ",
            gender=gender,
            additional_word=additional_word,
        )
        assert title == "クォーツ メンズ 腕時計"

    def test_brand_with_gender_and_additional_word(self):
        """ブランドあり: ...SEIKO セイコー PRESAGE ... メンズ 腕時計"""
        gender, additional_word = determine_title_gender_and_additional_word(
            match_level="brand+series",
            matched_entry={"gender": "メンズ"},
            ai_gender="",
            mapper_get_additional_word_result="腕時計",
        )
        title = generate_title(
            brand_en="SEIKO",
            brand_kana="セイコー",
            series_en="PRESAGE",
            gender=gender,
            additional_word=additional_word,
        )
        assert "SEIKO セイコー PRESAGE メンズ 腕時計" == title

    def test_brand_gender_empty_no_gender_in_title(self):
        """ブランドあり＆性別空 → タイトルに性別なし"""
        gender, additional_word = determine_title_gender_and_additional_word(
            match_level="brand+series",
            matched_entry={"gender": ""},
            ai_gender="メンズ",
            mapper_get_additional_word_result="腕時計",
        )
        title = generate_title(
            brand_en="SEIKO",
            gender=gender,
            additional_word=additional_word,
        )
        assert title == "SEIKO 腕時計"
        assert "メンズ" not in title

    def test_generic_unknown_gender_no_gender_in_title(self):
        """ブランドなし＆性別不明 → タイトルに性別なし"""
        gender, additional_word = determine_title_gender_and_additional_word(
            match_level="generic",
            matched_entry={"gender": "", "additional_word": "腕時計"},
            ai_gender="不明",
            mapper_get_additional_word_result="",
        )
        title = generate_title(
            movement_type="クォーツ",
            gender=gender,
            additional_word=additional_word,
        )
        assert title == "クォーツ 腕時計"
        assert "不明" not in title
