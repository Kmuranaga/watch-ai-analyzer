"""normalizer モジュールのテスト"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.normalizer import (
    normalize_text,
    normalize_brand,
    normalize_material,
    normalize_movement,
    normalize_water_resistance,
    normalize_case_shape,
    normalize_gender,
    normalize_all,
)


class TestNormalizeText:
    """基本テキスト正規化"""

    def test_strip_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_fullwidth_to_halfwidth(self):
        """全角英数字→半角"""
        assert normalize_text("ＳＥＩＫＯ") == "SEIKO"

    def test_compress_spaces(self):
        assert normalize_text("a   b  c") == "a b c"

    def test_empty(self):
        assert normalize_text("") == ""

    def test_none_like(self):
        assert normalize_text("") == ""


class TestNormalizeBrand:
    """ブランド名正規化"""

    def test_uppercase(self):
        assert normalize_brand("seiko") == "SEIKO"

    def test_fullwidth_and_upper(self):
        assert normalize_brand("ｓｅｉｋｏ") == "SEIKO"

    def test_with_spaces(self):
        assert normalize_brand("  omega  ") == "OMEGA"


class TestNormalizeMaterial:
    """素材名正規化"""

    def test_stainless_steel(self):
        assert normalize_material("Stainless Steel") == "ステンレス"

    def test_ss(self):
        assert normalize_material("SS") == "ステンレス"

    def test_titanium(self):
        assert normalize_material("Titanium") == "チタン"

    def test_gold_plated(self):
        assert normalize_material("GP") == "金メッキ"

    def test_k18(self):
        assert normalize_material("K18") == "18金"

    def test_750(self):
        assert normalize_material("750") == "18金"

    def test_sterling_silver(self):
        assert normalize_material("Sterling Silver") == "シルバー925"

    def test_ceramic(self):
        assert normalize_material("ceramic") == "セラミック"

    def test_resin(self):
        assert normalize_material("Resin") == "樹脂"

    def test_japanese_passthrough(self):
        """日本語素材名はそのまま"""
        assert normalize_material("ステンレス") == "ステンレス"

    def test_unknown_japanese(self):
        """未知の日本語素材名もそのまま"""
        assert normalize_material("カーボン") == "カーボン"

    def test_partial_match(self):
        """部分一致: 'stainless steel case' → ステンレス"""
        assert normalize_material("stainless steel case") == "ステンレス"

    def test_empty(self):
        assert normalize_material("") == ""

    def test_combi(self):
        assert normalize_material("Two-tone") == "コンビ"


class TestNormalizeMovement:
    """ムーブメント正規化"""

    def test_quartz(self):
        assert normalize_movement("Quartz") == "Quartz"

    def test_qz(self):
        assert normalize_movement("Qz") == "Quartz"

    def test_automatic(self):
        assert normalize_movement("Automatic") == "Automatic"

    def test_japanese_auto(self):
        assert normalize_movement("自動巻き") == "Automatic"

    def test_solar(self):
        assert normalize_movement("Solar") == "Solar"

    def test_eco_drive(self):
        assert normalize_movement("Eco-Drive") == "Solar"

    def test_kinetic(self):
        assert normalize_movement("Kinetic") == "Kinetic"

    def test_spring_drive(self):
        assert normalize_movement("Spring Drive") == "Spring Drive"

    def test_hand_wound_excluded(self):
        """手巻きは空文字（出力しない）"""
        assert normalize_movement("Hand-wound") == ""

    def test_hand_wound_japanese(self):
        assert normalize_movement("手巻き") == ""

    def test_manual_excluded(self):
        assert normalize_movement("Manual") == ""

    def test_empty(self):
        assert normalize_movement("") == ""

    def test_unknown_passthrough(self):
        """未知のムーブメントはそのまま"""
        assert normalize_movement("Unknown Type") == "Unknown Type"


class TestNormalizeWaterResistance:
    """防水表記正規化"""

    def test_bar(self):
        assert normalize_water_resistance("10 bar") == "10BAR"

    def test_atm(self):
        assert normalize_water_resistance("5 atm") == "5BAR"

    def test_meters(self):
        """100m → 10BAR"""
        assert normalize_water_resistance("100m") == "10BAR"

    def test_200m(self):
        assert normalize_water_resistance("200m") == "20BAR"

    def test_30m(self):
        """30m → 3BAR"""
        assert normalize_water_resistance("30m") == "3BAR"

    def test_5m_small(self):
        """5m → 0BAR → 日常生活防水"""
        assert normalize_water_resistance("5m") == "日常生活防水"

    def test_water_resistant(self):
        assert normalize_water_resistance("Water Resistant") == "日常生活防水"

    def test_wr(self):
        assert normalize_water_resistance("WR") == "日常生活防水"

    def test_japanese_daily(self):
        assert normalize_water_resistance("日常生活防水") == "日常生活防水"

    def test_empty(self):
        assert normalize_water_resistance("") == ""


class TestNormalizeCaseShape:
    """ケース形状正規化"""

    def test_round(self):
        assert normalize_case_shape("Round") == "ラウンド"

    def test_round_japanese(self):
        assert normalize_case_shape("丸型") == "ラウンド"

    def test_square(self):
        assert normalize_case_shape("Square") == "スクエア"

    def test_rectangular(self):
        assert normalize_case_shape("Rectangular") == "レクタンギュラー"

    def test_long_shape(self):
        assert normalize_case_shape("縦長") == "レクタンギュラー"

    def test_empty(self):
        assert normalize_case_shape("") == ""

    def test_unknown_passthrough(self):
        assert normalize_case_shape("オクタゴン") == "オクタゴン"


class TestNormalizeGender:
    """性別正規化"""

    def test_mens(self):
        assert normalize_gender("Mens") == "メンズ"

    def test_mens_possessive(self):
        assert normalize_gender("Men's") == "メンズ"

    def test_male(self):
        assert normalize_gender("Male") == "メンズ"

    def test_ladies(self):
        assert normalize_gender("Ladies") == "レディース"

    def test_women(self):
        assert normalize_gender("Women") == "レディース"

    def test_female(self):
        assert normalize_gender("Female") == "レディース"

    def test_unisex(self):
        assert normalize_gender("Unisex") == "ユニセックス"

    def test_japanese_male(self):
        assert normalize_gender("男性") == "メンズ"

    def test_japanese_female(self):
        assert normalize_gender("女性") == "レディース"

    def test_unknown(self):
        assert normalize_gender("Unknown") == "不明"

    def test_japanese_unknown(self):
        assert normalize_gender("不明") == "不明"

    def test_empty(self):
        assert normalize_gender("") == ""


class TestNormalizeAll:
    """normalize_all 統合テスト"""

    def test_full_normalization(self):
        data = {
            "brand_en": "seiko",
            "series_en": "presage",
            "material": "Stainless Steel",
            "movement_type": "Automatic",
            "water_resistance": "100m",
            "model_number": "  SARX055  ",
            "case_shape": "Round",
            "gender": "Mens",
        }
        result = normalize_all(data)
        assert result["brand_en"] == "SEIKO"
        assert result["series_en"] == "PRESAGE"
        assert result["material"] == "ステンレス"
        assert result["movement_type"] == "Automatic"
        assert result["water_resistance"] == "10BAR"
        assert result["model_number"] == "SARX055"
        assert result["case_shape"] == "ラウンド"
        assert result["gender"] == "メンズ"

    def test_empty_fields_not_processed(self):
        """空フィールドは処理されない（キーが存在しても空なら正規化スキップ）"""
        data = {"brand_en": "", "material": ""}
        result = normalize_all(data)
        assert result["brand_en"] == ""
        assert result["material"] == ""

    def test_missing_fields_preserved(self):
        """存在しないキーはそのまま"""
        data = {"brand_en": "omega", "extra_field": "test"}
        result = normalize_all(data)
        assert result["extra_field"] == "test"

    def test_original_not_mutated(self):
        """元のdictは変更されない"""
        data = {"brand_en": "seiko"}
        result = normalize_all(data)
        assert data["brand_en"] == "seiko"
        assert result["brand_en"] == "SEIKO"
