"""normalizer モジュールのテスト"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import modules.normalizer as normalizer_module
from modules.normalizer import (
    normalize_text,
    normalize_brand,
    normalize_color,
    normalize_material,
    normalize_movement,
    normalize_water_resistance,
    normalize_case_shape,
    normalize_gender,
    normalize_hand_count,
    normalize_model_number,
    normalize_series,
    normalize_all,
    reconcile_brand,
    set_known_brands,
)


@pytest.fixture()
def known_brands():
    """mapping.xlsx 登録ブランド相当のホワイトリストを設定する（テスト後にクリア）"""
    set_known_brands({"ELGIN", "CITIZEN", "SEIKO", "LONGINES", "OMEGA", "TAG HEUER"})
    yield
    set_known_brands(set())


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


class TestNormalizeColor:
    """色名正規化（複数色の区切り統一）"""

    def test_ideographic_comma_to_space(self):
        """実例 3000959/3000970: コンビの時計で読点区切りが混入する"""
        assert normalize_color("シルバー、ゴールド") == "シルバー ゴールド"

    def test_slash_to_space(self):
        assert normalize_color("シルバー/ゴールド") == "シルバー ゴールド"

    def test_fullwidth_slash_to_space(self):
        assert normalize_color("シルバー／ゴールド") == "シルバー ゴールド"

    def test_halfwidth_comma_to_space(self):
        assert normalize_color("シルバー, ゴールド") == "シルバー ゴールド"

    def test_nakaguro_to_space(self):
        assert normalize_color("シルバー・ゴールド") == "シルバー ゴールド"

    def test_single_color_unchanged(self):
        assert normalize_color("シルバー") == "シルバー"

    def test_empty(self):
        assert normalize_color("") == ""


class TestNormalizeMaterial:
    """素材名正規化"""

    def test_stainless_steel(self):
        assert normalize_material("Stainless Steel") == "ステンレス"

    def test_ss(self):
        assert normalize_material("SS") == "ステンレス"

    def test_titanium(self):
        assert normalize_material("Titanium") == "チタン"

    def test_gold_plated(self):
        """クライアント要望（2026-08）: GP/WGPは金メッキに変換せず刻印どおり出力"""
        assert normalize_material("GP") == "GP"

    def test_wgp(self):
        assert normalize_material("WGP") == "WGP"

    def test_wgp_dotted(self):
        assert normalize_material("W.G.P.") == "WGP"

    def test_k18(self):
        """クライアント要望（2026-08）: K18/18Kは価値が異なるため刻印どおり区別"""
        assert normalize_material("K18") == "K18"

    def test_18k(self):
        assert normalize_material("18K") == "18K"

    def test_18k_gold_electroplated(self):
        """実例 3000915: 「18K GOLD ELECTROPLATED」刻印 → 18K（金に食われない）"""
        assert normalize_material("18K GOLD ELECTROPLATED") == "18K"

    def test_750(self):
        assert normalize_material("750") == "18金"

    def test_925(self):
        """実例 3000921: 925刻印 → シルバー925 SV925（銀だと色と誤認されるため）"""
        assert normalize_material("925") == "シルバー925 SV925"

    def test_silver925_ja(self):
        assert normalize_material("シルバー925") == "シルバー925 SV925"

    def test_sterling_silver(self):
        assert normalize_material("Sterling Silver") == "シルバー925 SV925"

    def test_unknown_ascii_material_disabled(self):
        """実例 3000802: 裏蓋記号「PDP」は素材名ではないため出力しない"""
        assert normalize_material("PDP") == ""

    def test_unknown_japanese_material_kept(self):
        """変換表に無くても日本語なら素材名と判断してそのまま通す"""
        assert normalize_material("サンプラチナ") == "サンプラチナ"
        assert normalize_material("ロジウムメッキ") == "ロジウムメッキ"

    def test_karat_10k_9k(self):
        """10K/9K等の品位刻印も刻印どおり出力する（変換表の抜けで空欄化しない）"""
        assert normalize_material("10K") == "10K"
        assert normalize_material("K10") == "K10"
        assert normalize_material("9K") == "9K"
        assert normalize_material("24K") == "24K"

    def test_karat_wins_over_plating_suffix(self):
        """品位刻印は「金張り」等の後続語より優先（18K GOLD ELECTROPLATED→18K と同方針）"""
        assert normalize_material("10K金張り") == "10K"

    def test_stainless_back_not_material(self):
        """実例 3000677/3000707/3000722/3000752: 「STAINLESS BACK」は裏蓋のみの
        材質でありケース素材ではないため出力しない"""
        assert normalize_material("STAINLESS BACK") == ""
        assert normalize_material("STAINLESSBACK") == ""
        assert normalize_material("Stainless Steel Back") == ""

    def test_compound_karat_and_goldfilled(self):
        """複合刻印は品位・金張りの両方を残す（実行ごとの揺れと情報欠落を防ぐ）"""
        assert normalize_material("14K GF 40 MIC") == "14K金張り"
        assert normalize_material("14K GOLDFILLED") == "14K金張り"
        # 語間に空白がある表記（実例 3000799「FRONT 14K GOLD FILLED BACK STEEL」）
        assert normalize_material("FRONT 14K GOLD FILLED BACK STEEL") == "14K金張り"

    def test_compound_karat_and_rgp(self):
        assert normalize_material("W/10K R.G.P. BEZEL") == "10K RGP"

    def test_compound_karat_and_gp(self):
        assert normalize_material("18K GP") == "18K GP"

    def test_electroplated_stays_karat_only(self):
        """クライアント指定（3000915）: GOLD ELECTROPLATED は品位のみで返す"""
        assert normalize_material("18K GOLD ELECTROPLATED") == "18K"

    def test_karat_alone_unaffected(self):
        assert normalize_material("14K") == "14K"
        assert normalize_material("GF") == "金張り"

    def test_rgp_kept_as_marking(self):
        """R.G.P.（金張り）は品位刻印「10K」に化けさせず刻印どおり残す
        （品位が併記されていれば test_compound_karat_and_rgp のとおり複合表記）"""
        assert normalize_material("R.G.P.") == "RGP"
        assert normalize_material("RGP") == "RGP"

    def test_base_metal_back_not_material(self):
        """「BASE METAL BACK」も裏蓋限定なのでケース素材にしない"""
        assert normalize_material("BASE METAL BACK") == ""

    def test_base_metal_bezel_kept(self):
        """実例 3000719: BEZEL 側の刻印はケース素材として採用する"""
        assert normalize_material("BASE METAL BEZEL") == "ベースメタル"

    def test_stainless_steel_still_works(self):
        """BACK を伴わない STAINLESS STEEL は従来どおりステンレス"""
        assert normalize_material("STAINLESS STEEL") == "ステンレス"

    def test_goldfilled_no_space(self):
        """スペースなしの GOLDFILLED も金張り"""
        assert normalize_material("GOLDFILLED") == "金張り"

    def test_silver_disabled(self):
        """クライアント指示（2026-08・3000921）: 品位刻印のない「銀」は出力しない"""
        assert normalize_material("SILVER") == ""
        assert normalize_material("銀") == ""

    def test_ceramic(self):
        assert normalize_material("ceramic") == "セラミック"

    def test_resin(self):
        """クライアント指示（2026-08）: 質感推測による誤りを避けるため樹脂は出力しない"""
        assert normalize_material("Resin") == ""

    def test_gold_disabled(self):
        """クライアント指示（2026-08・3000658/WGP実例）: 金は出力しない"""
        assert normalize_material("金") == ""

    def test_resin_ja_disabled(self):
        assert normalize_material("樹脂") == ""

    def test_gold_map_disabled(self):
        """MATERIAL_MAP経由で金に変換される入力も最終的に空欄になる"""
        assert normalize_material("GOLD") == ""

    def test_18k_kept(self):
        """刻印ベースの「18金」は維持する（無効化対象は「金」「銀」「樹脂」のみ）"""
        assert normalize_material("18金") == "18金"

    def test_gold_plating_kept(self):
        assert normalize_material("金メッキ") == "金メッキ"

    def test_stainless_unaffected(self):
        assert normalize_material("ステンレス") == "ステンレス"

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
        """(b) ハイフンなしの短い数字（≤4桁、モジュール番号）は型番不明として空"""
        assert normalize_model_number("5196") == ""
        assert normalize_model_number("1647") == ""
        assert normalize_model_number("596") == ""

    def test_b_hyphenated_numeric_ref_kept(self):
        """(b) ハイフン区切りの数字型番（SEIKO/CITIZEN等のヴィンテージ参照番号）は保持"""
        assert normalize_model_number("6119-8030") == "6119-8030"
        assert normalize_model_number("2706-0170") == "2706-0170"
        assert normalize_model_number("11-4210") == "11-4210"
        assert normalize_model_number("4-520190", "CITIZEN") == "4-520190"

    def test_b_long_numeric_ref_kept(self):
        """(b) 5桁以上の数字型番（例 SEIKO 29014, 283110）は保持"""
        assert normalize_model_number("29014") == "29014"
        assert normalize_model_number("283110") == "283110"

    def test_c_function_word_removed(self):
        """(c) 機能語の除去"""
        assert normalize_model_number("SARX055 AUTOMATIC") == "SARX055"

    def test_c2_series_name_removed(self):
        """(c-2) 実例 3000628: 型番 "DIASTAR 8" はシリーズ名混入。除去後の
        「8」は(b)のモジュール番号扱いで空になる"""
        assert normalize_model_number("DIASTAR 8", "RADO", "DIASTAR") == ""

    def test_c2_series_name_removed_keeps_real_ref(self):
        """シリーズ名を除いた本体の型番は残る"""
        assert normalize_model_number(
            "PRESAGE SARX055", "SEIKO", "PRESAGE") == "SARX055"

    def test_c2_brand_name_removed(self):
        assert normalize_model_number("SEIKO 7548-7000", "SEIKO") == "7548-7000"

    def test_c2_short_token_not_removed(self):
        """2文字以下のシリーズ名は正当な型番要素と衝突しうるため除去しない"""
        assert normalize_model_number("LM 5606-7000", "SEIKO", "LM") == "5606-7000"

    def test_c2_no_series_unaffected(self):
        assert normalize_model_number("SARX055", "SEIKO", "") == "SARX055"

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

    def test_d_adjacent_noise_tokens_both_sides_removed(self):
        """(d) gemini-3.6-flash が隣接刻印を含めて返す実例:
        先頭・末尾の3文字以下純英字トークンを除去する"""
        assert normalize_model_number("IT 469658A-6B PR") == "469658A-6B"

    def test_d_adjacent_noise_token_prefix_only(self):
        """(d) 先頭のみノイズトークンがある場合"""
        assert normalize_model_number("PR 6119-8030") == "6119-8030"

    def test_d_adjacent_noise_token_suffix_only(self):
        """(d) 末尾のみノイズトークンがある場合"""
        assert normalize_model_number("6119-8030 IT") == "6119-8030"

    def test_d_no_whitespace_unaffected(self):
        """(d) 空白がない（単一トークン）場合は対象外・変化なし"""
        assert normalize_model_number("DW-8800") == "DW-8800"

    def test_d_all_alpha_tokens_untouched(self):
        """(d) 全トークンが純英字の場合は何もしない（既存の機能語除去が別途担当）"""
        assert normalize_model_number("AUTOMATIC") == ""


class TestNormalizeSeries:
    """シリーズ名正規化（SEIKO略称展開）"""

    def test_lm_expands_to_lord_matic(self):
        """SEIKO の LM → LORD MATIC（2924305 のケース）"""
        assert normalize_series("LM", "SEIKO") == "LORD MATIC"

    def test_lm_lowercase_input(self):
        assert normalize_series("lm", "seiko") == "LORD MATIC"

    def test_ks_gs_expand_for_seiko(self):
        assert normalize_series("KS", "SEIKO") == "KING SEIKO"
        assert normalize_series("GS", "SEIKO") == "GRAND SEIKO"

    def test_no_expand_for_non_seiko(self):
        """SEIKO 以外では略称を展開しない（誤展開防止）"""
        assert normalize_series("LM", "CITIZEN") == "LM"
        assert normalize_series("GS", "") == "GS"

    def test_non_alias_series_passthrough(self):
        """略称表に無いシリーズは大文字化のみ"""
        assert normalize_series("presage", "SEIKO") == "PRESAGE"
        assert normalize_series("CRONOS", "SEIKO") == "CRONOS"

    def test_full_normalization_expands_seiko_lm(self):
        """normalize_all 経由でも LM が展開される（ブランド整合後の brand_en を使用）"""
        data = {"brand_en": "SEIKO", "series_en": "LM", "series_kana": "ロードマチック"}
        result = normalize_all(data)
        assert result["series_en"] == "LORD MATIC"

    def test_lk_expands_to_lukia(self):
        """SEIKO の LK → LUKIA（クライアント報告事象）"""
        assert normalize_series("LK", "SEIKO") == "LUKIA"

    def test_lk_no_expand_for_non_seiko(self):
        """SEIKO 以外では LK を展開しない"""
        assert normalize_series("LK", "CITIZEN") == "LK"


class TestNormalizeSeriesFunctionWords:
    """シリーズの機能語除去（仕様書4.4／型番4.2(c)と対称）"""

    def test_chronograph_only_becomes_empty(self):
        """クライアント報告 2999571: 文字盤の "Chronograph" 印字がシリーズに入る"""
        assert normalize_series("CHRONOGRAPH", "TOWN & COUNTRY SURF DESIGNS") == ""

    def test_lowercase_input(self):
        assert normalize_series("chronograph") == ""

    def test_function_word_removed_from_multiword(self):
        assert normalize_series("SPEEDMASTER CHRONOGRAPH", "OMEGA") == "SPEEDMASTER"

    def test_other_spec_words(self):
        assert normalize_series("QUARTZ") == ""
        assert normalize_series("WATER RESISTANT") == ""
        assert normalize_series("JAPAN MOVT") == ""
        assert normalize_series("STAINLESS STEEL") == ""

    def test_swatch_chrono_is_protected(self):
        """mapping.xlsx 登録の実在シリーズ SWATCH CHRONO は除去しない"""
        assert normalize_series("CHRONO", "SWATCH") == "CHRONO"

    def test_chrono_removed_for_other_brands(self):
        assert normalize_series("CHRONO", "SEIKO") == ""

    def test_substring_not_matched(self):
        """部分一致では消さない（BREITLING CHRONOMAT の保護）"""
        assert normalize_series("CHRONOMAT", "BREITLING") == "CHRONOMAT"

    def test_hyphen_not_split(self):
        """型番と違いハイフンでは分割しない（CHRONO-MATIC / ANA-DIGI 等）"""
        assert normalize_series("CHRONO-MATIC", "BREITLING") == "CHRONO-MATIC"

    def test_real_series_untouched(self):
        for s in ("PRESAGE", "G-SHOCK", "DATA BANK", "TOUGH SOLAR",
                  "SEVEN STAR", "PRO TREK"):
            assert normalize_series(s) == s

    def test_seiko_alias_still_expands(self):
        """略称展開→機能語除去の順序で既存挙動が壊れない"""
        assert normalize_series("LM", "SEIKO") == "LORD MATIC"


class TestNormalizeAllSeriesKana:
    """normalize_all: SEIKO略称展開時の series_kana 上書き"""

    def test_function_word_series_clears_kana(self):
        """series_en が機能語のみで空になったら series_kana も空にする（2999571）"""
        data = {"brand_en": "TOWN & COUNTRY SURF DESIGNS",
                "series_en": "CHRONOGRAPH", "series_kana": "クロノグラフ"}
        result = normalize_all(data)
        assert result["series_en"] == ""
        assert result["series_kana"] == ""

    def test_partial_removal_strips_kana_token(self):
        data = {"brand_en": "OMEGA", "series_en": "SPEEDMASTER CHRONOGRAPH",
                "series_kana": "スピードマスタークロノグラフ"}
        result = normalize_all(data)
        assert result["series_en"] == "SPEEDMASTER"
        assert result["series_kana"] == "スピードマスター"

    def test_swatch_chrono_kana_kept(self):
        data = {"brand_en": "SWATCH", "series_en": "CHRONO", "series_kana": "クロノ"}
        result = normalize_all(data)
        assert result["series_en"] == "CHRONO"
        assert result["series_kana"] == "クロノ"

    def test_kana_less_series_kana_cleared(self):
        """実例 3000910: series_kana="42-20"（カナ無し）は読みではないため除去"""
        data = {"brand_en": "NIXON", "series_en": "THE 42-20",
                "series_kana": "42-20", "model_number": "42-20"}
        result = normalize_all(data)
        assert result["series_en"] == "THE 42-20"
        assert result["series_kana"] == ""

    def test_ascii_token_dup_stripped_from_kana(self):
        """実例 3000693: series_kana="コスモスター V2" の V2 はシリーズ英字の重複なので除去"""
        data = {"brand_en": "CITIZEN", "series_en": "COSMO STAR V2",
                "series_kana": "コスモスター V2"}
        result = normalize_all(data)
        assert result["series_kana"] == "コスモスター"

    def test_brand_kana_dup_stripped_from_series_kana(self):
        """実例 3000772: series_kana="ファイン セイコー" の「セイコー」は
        ブランドカナと重複するため除去"""
        data = {"brand_en": "SEIKO", "brand_kana": "セイコー",
                "series_en": "FINE", "series_kana": "ファイン セイコー"}
        result = normalize_all(data)
        assert result["series_kana"] == "ファイン"

    def test_joined_kana_with_brand_name_kept(self):
        """結合形（レディセイコー/グランドセイコー）は1トークンなので維持"""
        data = {"brand_en": "SEIKO", "brand_kana": "セイコー",
                "series_en": "LADY SEIKO", "series_kana": "レディセイコー"}
        result = normalize_all(data)
        assert result["series_kana"] == "レディセイコー"

    def test_ascii_token_not_in_series_en_kept(self):
        """シリーズ英字に無い英数字トークンは維持する"""
        data = {"brand_en": "SEIKO", "series_en": "LORD MATIC",
                "series_kana": "ロードマチック 25"}
        result = normalize_all(data)
        assert result["series_kana"] == "ロードマチック 25"

    def test_mixed_kana_series_kana_kept(self):
        """カナを含む series_kana（Gショック等）は維持する"""
        data = {"brand_en": "CASIO", "series_en": "G-SHOCK",
                "series_kana": "Gショック"}
        result = normalize_all(data)
        assert result["series_kana"] == "Gショック"

    def test_lk_expansion_overwrites_wrong_kana(self):
        """LK→LUKIA 展開時、AIの誤カナ「エルケー」を「ルキア」で上書きする"""
        data = {"brand_en": "SEIKO", "series_en": "LK", "series_kana": "エルケー"}
        result = normalize_all(data)
        assert result["series_en"] == "LUKIA"
        assert result["series_kana"] == "ルキア"

    def test_lm_expansion_keeps_existing_correct_kana(self):
        """LM→LORD MATIC 展開時、既存の正しいカナはそのまま維持される（既存挙動維持）"""
        data = {"brand_en": "SEIKO", "series_en": "LM", "series_kana": "ロードマチック"}
        result = normalize_all(data)
        assert result["series_en"] == "LORD MATIC"
        assert result["series_kana"] == "ロードマチック"

    def test_direct_lukia_not_expanded_kana_untouched(self):
        """略称でなく直接 LUKIA と表記されている場合は上書きロジックが誤発火しない"""
        data = {"brand_en": "SEIKO", "series_en": "LUKIA", "series_kana": "ルキア"}
        result = normalize_all(data)
        assert result["series_en"] == "LUKIA"
        assert result["series_kana"] == "ルキア"

    def test_unrelated_series_not_affected(self):
        """略称展開に無関係なシリーズは影響を受けない"""
        data = {"brand_en": "SEIKO", "series_en": "SPIRIT", "series_kana": "スピリット"}
        result = normalize_all(data)
        assert result["series_en"] == "SPIRIT"
        assert result["series_kana"] == "スピリット"


class TestSeriesSameAsBrand:
    """シリーズ名がブランド名と完全一致する場合はシリーズを空欄にする（実例 3000161）

    文字盤に「GREENWICH」と1回だけ印字された商品で、AIがブランド名とシリーズ名
    の両方に同じ語を入れ、タイトルが「GREENWICH グリニッジ GREENWICH グリニッジ…」
    と連続重複した。ブランドとシリーズの完全同名は通常あり得ないため除去する。
    部分一致（SEIKO/GRAND SEIKO等）は正常な組み合わせなので対象外。
    """

    def test_series_same_as_brand_is_cleared(self):
        data = {"brand_en": "GREENWICH", "series_en": "GREENWICH", "series_kana": "グリニッジ"}
        result = normalize_all(data)
        assert result["series_en"] == ""
        assert result["series_kana"] == ""

    def test_case_insensitive_match_is_cleared(self):
        """大文字小文字違いでも正規化後比較のため除去される"""
        data = {"brand_en": "GREENWICH", "series_en": "Greenwich", "series_kana": "グリニッジ"}
        result = normalize_all(data)
        assert result["series_en"] == ""
        assert result["series_kana"] == ""

    def test_partial_match_kept(self):
        """部分一致（SEIKO / GRAND SEIKO）は対象外、保持する"""
        data = {"brand_en": "SEIKO", "series_en": "GRAND SEIKO", "series_kana": "グランドセイコー"}
        result = normalize_all(data)
        assert result["series_en"] == "GRAND SEIKO"
        assert result["series_kana"] == "グランドセイコー"

    def test_swatch_chrono_exception_pair_kept(self):
        """既存の機能語除外ペア（SWATCH CHRONO）に影響しない"""
        data = {"brand_en": "SWATCH", "series_en": "CHRONO", "series_kana": "クロノ"}
        result = normalize_all(data)
        assert result["series_en"] == "CHRONO"
        assert result["series_kana"] == "クロノ"

    def test_casio_g_shock_kept(self):
        data = {"brand_en": "CASIO", "series_en": "G-SHOCK", "series_kana": "ジーショック"}
        result = normalize_all(data)
        assert result["series_en"] == "G-SHOCK"
        assert result["series_kana"] == "ジーショック"


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
        """normalize_all 経由で短い数字のみ型番（モジュール番号）が空になる（①(b)）"""
        result = normalize_all({"brand_en": "CASIO", "model_number": "5196"})
        assert result["model_number"] == ""

    def test_model_number_numeric_ref_preserved(self):
        """normalize_all 経由で数字型番（SEIKOヴィンテージ参照番号）が保持される（①(b)）"""
        result = normalize_all({"brand_en": "SEIKO", "model_number": "6119-8030"})
        assert result["model_number"] == "6119-8030"

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
    """ブランド整合 reconcile_brand 単体テスト（文字盤最優先仕様）

    仕様変更（2026-07-24 クライアント合意）: 文字盤で読めたブランドは裏蓋刻印で
    上書きしない。裏蓋は文字盤が判読不可の場合の補完のみで、採用は既知ブランド
    （mapping.xlsx 登録分 = set_known_brands 登録分）に限定する。
    """

    # === ルール1: 文字盤があれば常に文字盤 ===

    def test_front_wins_over_back_movement_maker(self):
        """RONSON(front) + CITIZEN(back, 製造元) → RONSON"""
        brand, source = reconcile_brand("RONSON", "CITIZEN")
        assert brand == "RONSON"
        assert source == "front"

    def test_front_wins_over_back_real_brand(self, known_brands):
        """TAG HEUER(front) + ELGIN(back, 既知ブランド) → front を維持

        仕様変更点: 旧仕様では裏蓋の実ブランドが正面を是正していたが、
        文字盤最優先の合意により、既知ブランド刻印でも上書きしない。
        """
        brand, source = reconcile_brand("TAG HEUER", "ELGIN", front_conf=0.98)
        assert brand == "TAG HEUER"
        assert source == "front"

    def test_front_wins_even_with_low_conf(self, known_brands):
        """front低確信(0.4)でも文字盤を採用（confidence は判定に使わない）"""
        brand, source = reconcile_brand("OMEGA", "ELGIN", front_conf=0.4)
        assert brand == "OMEGA"
        assert source == "front"

    def test_front_wins_over_case_maker_star(self):
        """CITIZEN(front) + STAR(back, ケースメーカー刻印) → front を維持

        実データ: 2959928/2959931/2959883/2959969（□STAR刻印）。
        """
        brand, source = reconcile_brand("CITIZEN", "STAR", front_conf=1.0)
        assert brand == "CITIZEN"
        assert source == "front"

    def test_front_wins_over_band_maker(self, known_brands):
        """OMEGA(front) + ELMITEX(back, ベルトメーカー刻印) → front を維持（実データ 2960103）"""
        brand, source = reconcile_brand("OMEGA", "ELMITEX")
        assert brand == "OMEGA"
        assert source == "front"

    def test_front_wins_over_back_series_engraving(self, known_brands):
        """LONGINES(front) + FLAGSHIP(back, シリーズ刻印) → front を維持（実データ 2968274）"""
        brand, source = reconcile_brand("LONGINES", "FLAGSHIP")
        assert brand == "LONGINES"
        assert source == "front"

    def test_front_equals_back(self):
        """front=back（一致）→ そのブランド"""
        brand, source = reconcile_brand("SEIKO", "seiko")
        assert brand == "SEIKO"
        assert source == "front"

    def test_front_only(self):
        """裏蓋空 → 文字盤優先"""
        brand, source = reconcile_brand("CASIO", "")
        assert brand == "CASIO"
        assert source == "front"

    # === ルール2: 文字盤が空のときのみ、既知ブランドの裏蓋刻印で補完 ===

    def test_back_fills_when_front_empty_and_known(self, known_brands):
        """front空 + ELGIN(back, 既知ブランド) → ELGIN（表判読不可の補完）"""
        brand, source = reconcile_brand("", "ELGIN")
        assert brand == "ELGIN"
        assert source == "back"

    def test_back_unknown_brand_not_adopted_when_front_empty(self, known_brands):
        """front空 + ELMITEX(back, 未登録) → 補完せず空欄（人手確認へ）"""
        brand, source = reconcile_brand("", "ELMITEX")
        assert brand == ""
        assert source == ""

    def test_back_case_maker_not_adopted_when_front_empty(self, known_brands):
        """front空 + STAR(back, ケースメーカー刻印) → 補完せず空欄"""
        brand, source = reconcile_brand("", "STAR")
        assert brand == ""
        assert source == ""

    def test_back_not_adopted_when_no_known_brands_registered(self):
        """ホワイトリスト未登録（起動時に set_known_brands 未呼び出し）なら補完しない"""
        brand, source = reconcile_brand("", "ELGIN")
        assert brand == ""
        assert source == ""

    def test_both_empty(self):
        """両方空 → ''"""
        brand, source = reconcile_brand("", "")
        assert brand == ""
        assert source == ""


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

    def test_case_maker_back_not_leaked_into_series_or_kana(self):
        """CITIZEN(front) + STAR/EVERBRIGHT(back, ケース刻印) → シリーズ・カナに漏れない

        実データ 2959931: 裏蓋の「EVERBRIGHT BACK」（材質表記）が back_series_en に
        読まれ、front のシリーズが空だと補完経由でタイトルに混入していた。
        ケースメーカー・材質刻印はシリーズ補完にも使わない。
        """
        merged = {
            "brand_en": "CITIZEN",
            "brand_kana": "",
            "series_en": "",
            "series_kana": "",
            "back_brand_en": "STAR",
            "back_brand_kana": "スター",
            "back_series_en": "EVERBRIGHT",
            "back_series_kana": "エバーブライト",
            "confidence": {"brand": 1.0},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "CITIZEN"
        assert result["series_en"] == ""
        assert result["series_kana"] == ""
        assert result["brand_kana"] == ""

    def test_case_maker_raw_inscription_variant_not_leaked(self):
        """back_series が刻印生値「EVERBRIGHT BACK」で返ってきても漏れない

        AIは通常「EVERBRIGHT」に切り出すが、刻印どおりの生値で返す可能性もある。
        部分一致にすると実在シリーズ（SEVEN STAR 等）を誤って消すため、
        バリアントはリテラルで CASE_MAKERS に持つ。
        """
        merged = {
            "brand_en": "CITIZEN",
            "series_en": "",
            "back_brand_en": "",
            "back_series_en": "EVERBRIGHT BACK",
            "back_series_kana": "エバーブライトバック",
        }
        result = normalize_all(merged)
        assert result["series_en"] == ""
        assert result["series_kana"] == ""

    def test_real_series_containing_star_is_kept(self):
        """「SEVEN STAR」等、STARを含む実在シリーズは消されない（完全一致ガードの確認）"""
        merged = {
            "brand_en": "CITIZEN",
            "series_en": "",
            "back_brand_en": "",
            "back_series_en": "SEVEN STAR",
            "back_series_kana": "セブンスター",
        }
        result = normalize_all(merged)
        assert result["series_en"] == "SEVEN STAR"
        assert result["series_kana"] == "セブンスター"

    def test_dial_first_front_kept_over_known_back_brand(self, known_brands):
        """LONGINES(front) + FLAGSHIP刻印(back) → 文字盤を維持（実データ 2968274）

        文字盤最優先仕様: 既知/未知に関わらず、文字盤が読めていれば裏蓋で上書きしない。
        """
        merged = {
            "brand_en": "LONGINES",
            "brand_kana": "ロンジン",
            "series_en": "",
            "series_kana": "",
            "back_brand_en": "FLAGSHIP",
            "back_brand_kana": "フラッグシップ",
            "back_series_en": "",
            "back_series_kana": "",
            "confidence": {"brand": 1.0},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "LONGINES"
        assert result["brand_kana"] == "ロンジン"

    def test_back_brand_supplements_when_front_empty(self, known_brands):
        """front空 + ELGIN(back, 既知ブランド) → brand_en=ELGIN、kana/series も back を採用"""
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

    def test_low_conf_front_kept_over_back(self, known_brands):
        """front低確信でも文字盤を採用（文字盤最優先。confidence は判定に使わない）"""
        merged = {
            "brand_en": "OMEGA",
            "back_brand_en": "ELGIN",
            "confidence": {"brand": 0.4},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "OMEGA"
        assert "back_brand_en" not in result

    def test_front_kept_over_back_real_brand(self, known_brands):
        """front(TAG HEUER) + 実ブランド裏蓋(ELGIN) → 文字盤を維持

        仕様変更（2026-07-24 クライアント合意・文字盤最優先）: 旧仕様では
        裏蓋ELGINが正面誤読を是正していたが（実データ2916676）、上書きは廃止。
        文字盤の誤読はそのまま出力され、目視確認で修正する運用となる。
        """
        merged = {
            "brand_en": "TAG HEUER",
            "back_brand_en": "ELGIN",
            "back_series_en": "MOST VALUABLE PLAYER",
            "confidence": {"brand": 0.98},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "TAG HEUER"
        assert "back_brand_en" not in result

    def test_high_conf_front_kept_when_back_is_maker(self):
        """front高確信(SEIKO) + 製造元裏蓋(STP) → SEIKOを維持（退行防止）

        実データ(2924283): 裏蓋STPはムーブメント製造元。製品ブランドSEIKOを維持する。
        """
        merged = {
            "brand_en": "SEIKO",
            "series_en": "CRONOS",
            "back_brand_en": "STP",
            "confidence": {"brand": 0.99},
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "SEIKO"
        assert result["series_en"] == "CRONOS"
        assert "back_brand_en" not in result

    # === brand_source（診断用キー）===

    def test_brand_source_front(self, known_brands):
        """文字盤採用時は brand_source == 'front'"""
        merged = {"brand_en": "SEIKO", "back_brand_en": "ELGIN"}
        result = normalize_all(merged)
        assert result["brand_en"] == "SEIKO"
        assert result["brand_source"] == "front"

    def test_brand_source_back(self, known_brands):
        """裏蓋補完採用時は brand_source == 'back'"""
        merged = {"brand_en": "", "back_brand_en": "ELGIN"}
        result = normalize_all(merged)
        assert result["brand_en"] == "ELGIN"
        assert result["brand_source"] == "back"

    def test_brand_source_empty_when_unresolved(self, known_brands):
        """front空 + 未登録裏蓋ブランド(RONSON) → brand_en=='' かつ brand_source==''"""
        merged = {"brand_en": "", "back_brand_en": "RONSON"}
        result = normalize_all(merged)
        assert result["brand_en"] == ""
        assert result["brand_source"] == ""

    # === DISCARD_NON_PRINTED_BRAND（brand_evidence による破棄）===

    def test_discard_non_printed_brand_when_flag_enabled(self, monkeypatch):
        """DISCARD_NON_PRINTED_BRAND=True + brand_evidence='logo_mark' → front brand を破棄"""
        monkeypatch.setattr(normalizer_module, "DISCARD_NON_PRINTED_BRAND", True)
        merged = {
            "brand_en": "ROLEX",
            "brand_kana": "ロレックス",
            "brand_evidence": "logo_mark",
        }
        result = normalize_all(merged)
        assert result["brand_en"] == ""
        assert result["brand_kana"] == ""

    def test_discard_flag_enabled_but_no_evidence_key_keeps_front(self, monkeypatch):
        """DISCARD_NON_PRINTED_BRAND=True でも brand_evidence キーが無ければ従来どおり採用"""
        monkeypatch.setattr(normalizer_module, "DISCARD_NON_PRINTED_BRAND", True)
        merged = {
            "brand_en": "ROLEX",
            "brand_kana": "ロレックス",
        }
        result = normalize_all(merged)
        assert result["brand_en"] == "ROLEX"
        assert result["brand_kana"] == "ロレックス"

    def test_brand_evidence_not_leaked_into_output(self):
        """brand_evidence は一時キーとして出力に残らない"""
        merged = {
            "brand_en": "SEIKO",
            "brand_evidence": "printed_text",
        }
        result = normalize_all(merged)
        assert "brand_evidence" not in result
