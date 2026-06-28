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
    normalize_hand_count,
    normalize_model_number,
    normalize_all,
    reconcile_brand,
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


class TestNormalizeHandCount:
    """針数正規化（③ 表記ゆれ吸収）"""

    def test_arabic(self):
        assert normalize_hand_count("2針") == "2針"

    def test_kanji(self):
        assert normalize_hand_count("二針") == "2針"

    def test_with_space(self):
        assert normalize_hand_count("3 針") == "3針"

    def test_hon(self):
        assert normalize_hand_count("3本") == "3針"

    def test_digital_english(self):
        assert normalize_hand_count("digital") == "デジタル"

    def test_digital_japanese(self):
        assert normalize_hand_count("デジタル表示") == "デジタル"

    def test_chronograph(self):
        assert normalize_hand_count("クロノグラフ") == "クロノグラフ"

    def test_chronograph_english(self):
        assert normalize_hand_count("Chronograph") == "クロノグラフ"

    def test_empty(self):
        assert normalize_hand_count("") == ""


class TestNormalizeModelNumber:
    """型番正規化（① 3類型 + 基本正規化）"""

    def test_basic_uppercase_strip(self):
        """基本正規化: 前後空白除去・大文字化"""
        assert normalize_model_number("  sarx055  ") == "SARX055"

    def test_fullwidth(self):
        """全角→半角"""
        assert normalize_model_number("ＧＡ－１００") == "GA-100"

    def test_hyphen_spaces(self):
        """ハイフン前後の空白除去"""
        assert normalize_model_number("GA - 100") == "GA-100"

    def test_a_module_prefix_removed(self):
        """(a) 先頭モジュール番号 5081- を除去"""
        assert normalize_model_number("5081-GA-100CF") == "GA-100CF"

    def test_a_module_prefix_3digit(self):
        assert normalize_model_number("596-EQB-501") == "EQB-501"

    def test_b_module_only_numeric(self):
        """(b) 数字だけ（英字なし）は型番不明として空"""
        assert normalize_model_number("5196") == ""
        assert normalize_model_number("1647") == ""

    def test_b_module_only_with_hyphen(self):
        """数字とハイフンだけも英字を含まないため空"""
        assert normalize_model_number("5081-100") == ""

    def test_c_function_word_removed(self):
        """(c) 機能語の除去"""
        assert normalize_model_number("SARX055 AUTOMATIC") == "SARX055"

    def test_c_multiple_function_words(self):
        assert normalize_model_number("GA-100 QUARTZ CHRONOGRAPH") == "GA-100"

    def test_c_diamond_removed(self):
        assert normalize_model_number("ABC-123 DIAMOND") == "ABC-123"

    def test_c_function_word_hyphen_joined(self):
        """(c) ハイフンで結合した機能語も除去（顧客実例 AUTOMATIC-UNI5901）"""
        assert normalize_model_number("AUTOMATIC-UNI5901", "CITIZEN") == "UNI5901"

    def test_empty(self):
        assert normalize_model_number("") == ""

    def test_only_function_word_becomes_empty(self):
        """機能語のみなら空になる"""
        assert normalize_model_number("AUTOMATIC") == ""

    def test_normal_model_passthrough(self):
        """通常の型番はそのまま"""
        assert normalize_model_number("EQB-501XDB-2A") == "EQB-501XDB-2A"


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
            "body_color": " シルバー ",
            "dial_color": "ブラック",
            "hand_count": "二針",
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
        assert result["body_color"] == "シルバー"
        assert result["dial_color"] == "ブラック"
        assert result["hand_count"] == "2針"

    def test_model_number_module_prefix_in_normalize_all(self):
        """normalize_all 経由で型番のモジュール番号が除去される（①(a)）"""
        result = normalize_all({"brand_en": "CASIO", "model_number": "5081-GA-100CF"})
        assert result["model_number"] == "GA-100CF"

    def test_model_number_module_only_emptied(self):
        """normalize_all 経由で数字のみ型番が空になる（①(b)）"""
        result = normalize_all({"brand_en": "CASIO", "model_number": "5196"})
        assert result["model_number"] == ""

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


class TestReconcileBrand:
    """裏蓋ブランド整合 reconcile_brand 単体テスト"""

    def test_front_product_back_movement_maker(self):
        """RONSON(front) + CITIZEN(back, 製造元) → RONSON"""
        brand, source = reconcile_brand("RONSON", "CITIZEN")
        assert brand == "RONSON"
        assert source == "front"

    def test_front_empty_back_real_brand(self):
        """front空 + ELGIN(back) → ELGIN（仕様1: 表判読不可の補完）"""
        brand, source = reconcile_brand("", "ELGIN")
        assert brand == "ELGIN"
        assert source == "back"

    def test_front_equals_back(self):
        """front=back（一致）→ そのブランド"""
        brand, source = reconcile_brand("SEIKO", "seiko")
        assert brand == "SEIKO"
        assert source == "front"

    def test_front_low_conf_back_real_brand(self):
        """front低確信(0.4) + 別の実ブランド(back) → back"""
        brand, source = reconcile_brand("OMEGA", "ELGIN", front_conf=0.4)
        assert brand == "ELGIN"
        assert source == "back"

    def test_front_high_conf_back_real_brand(self):
        """front高確信 + 別ブランド(back, 製造元でない) → front（文字盤優先）"""
        brand, source = reconcile_brand("OMEGA", "ELGIN", front_conf=0.95)
        assert brand == "OMEGA"
        assert source == "front"

    def test_both_empty(self):
        """両方空 → ''"""
        brand, source = reconcile_brand("", "")
        assert brand == ""
        assert source == ""

    def test_low_conf_but_back_is_movement_maker(self):
        """front低確信でも裏蓋が製造元なら front を維持（RONSON対策優先）"""
        brand, source = reconcile_brand("RONSON", "CITIZEN", front_conf=0.4)
        assert brand == "RONSON"
        assert source == "front"

    def test_front_only(self):
        """裏蓋空 → 文字盤優先"""
        brand, source = reconcile_brand("CASIO", "")
        assert brand == "CASIO"
        assert source == "front"


class TestNormalizeAllReconcile:
    """normalize_all でのブランド整合 + 一時キー削除 統合テスト"""

    def test_front_brand_kept_when_back_is_maker(self):
        """RONSON(front) + CITIZEN(back製造元) → brand_en=RONSON、back_*削除"""
        merged = {
            "brand_en": "RONSON",
            "brand_kana": "ロンソン",
            "series_en": "CLASSIC",
            "series_kana": "クラシック",
            "back_brand_en": "CITIZEN",
            "back_brand_kana": "シチズン",
            "back_series_en": "",
            "back_series_kana": "",
            "confidence": {"brand": 0.9},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "RONSON"
        assert result["series_en"] == "CLASSIC"
        assert result["brand_kana"] == "ロンソン"
        # 一時キーは出力に残らない
        for key in ("back_brand_en", "back_brand_kana",
                    "back_series_en", "back_series_kana", "back_confidence"):
            assert key not in result

    def test_back_brand_supplements_when_front_empty(self):
        """front空 + ELGIN(back) → brand_en=ELGIN、kana/series も back を採用"""
        merged = {
            "brand_en": "",
            "brand_kana": "",
            "series_en": "",
            "series_kana": "",
            "back_brand_en": "ELGIN",
            "back_brand_kana": "エルジン",
            "back_series_en": "DELUXE",
            "back_series_kana": "デラックス",
            "confidence": {},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "ELGIN"
        assert result["brand_kana"] == "エルジン"
        assert result["series_en"] == "DELUXE"
        assert result["series_kana"] == "デラックス"
        assert "back_brand_en" not in result

    def test_low_conf_front_overridden_by_back(self):
        """front低確信 + 実ブランド裏蓋 → 裏蓋採用"""
        merged = {
            "brand_en": "OMEGA",
            "back_brand_en": "ELGIN",
            "confidence": {"brand": 0.4},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "ELGIN"
        assert "back_brand_en" not in result
