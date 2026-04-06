"""title_generator のテスト"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.title_generator import generate_title


class TestGenerateTitle:
    """generate_title の基本動作テスト"""

    def test_all_parts_joined(self):
        """全要素が空白区切りで結合される"""
        title = generate_title(
            brand_en="SEIKO",
            brand_kana="セイコー",
            series_en="PRESAGE",
            model_number="SARX055",
            dial_color="ブルー",
        )
        assert "SEIKO セイコー PRESAGE SARX055 ブルー" == title

    def test_empty_parts_excluded(self):
        """空文字の要素はスキップされる"""
        title = generate_title(brand_en="CASIO", model_number="GA-100")
        assert title == "CASIO GA-100"

    def test_title_prefix_prepended(self):
        """title_prefix が先頭に追加される"""
        title = generate_title(title_prefix="【ジャンク】", brand_en="OMEGA")
        assert title == "【ジャンク】 OMEGA"

    def test_empty_title_prefix_ignored(self):
        """空の title_prefix は無視される"""
        title = generate_title(title_prefix="", brand_en="ROLEX")
        assert title == "ROLEX"

    def test_all_empty_returns_empty(self):
        """全て空なら空文字列"""
        title = generate_title()
        assert title == ""


class TestGenderAdditionalWordOrder:
    """仕様: 性別は additional_word の直前に配置される"""

    def test_gender_before_additional_word(self):
        """性別 → 追加単語 の順序 (仕様Q2: パターンB)"""
        title = generate_title(
            brand_en="CASIO",
            movement_type="クォーツ",
            gender="メンズ",
            additional_word="腕時計",
        )
        # gender が additional_word の直前にあること
        assert "メンズ 腕時計" in title

    def test_gender_only(self):
        """性別だけ、追加単語なし"""
        title = generate_title(brand_en="SEIKO", gender="レディース")
        assert title == "SEIKO レディース"

    def test_additional_word_only(self):
        """追加単語だけ、性別なし"""
        title = generate_title(brand_en="SEIKO", additional_word="腕時計")
        assert title == "SEIKO 腕時計"

    def test_neither_gender_nor_additional_word(self):
        """性別も追加単語もなし"""
        title = generate_title(brand_en="SEIKO", movement_type="クォーツ")
        assert title == "SEIKO クォーツ"

    def test_full_title_order(self):
        """全要素指定時のフル順序確認"""
        title = generate_title(
            title_prefix="【中古】",
            brand_en="CASIO",
            brand_kana="カシオ",
            series_en="G-SHOCK",
            series_kana="ジーショック",
            model_number="GA-100",
            dial_color="ブラック",
            hand_count="3針",
            case_shape="ラウンド",
            material="ステンレス",
            water_resistance="20気圧防水",
            movement_type="クォーツ",
            gender="メンズ",
            additional_word="腕時計",
        )
        expected = (
            "【中古】 CASIO カシオ G-SHOCK ジーショック GA-100 "
            "ブラック 3針 ラウンド ステンレス 20気圧防水 クォーツ メンズ 腕時計"
        )
        assert title == expected
