"""folder_scanner モジュールのテスト"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.folder_scanner import extract_management_number, scan_folder, ProductImages


class TestExtractManagementNumber:
    """管理番号抽出のテスト"""

    def test_number_underscore(self):
        assert extract_management_number("1234567_時計") == "1234567"

    def test_number_space(self):
        assert extract_management_number("1234567 SEIKO 時計") == "1234567"

    def test_number_only(self):
        assert extract_management_number("1234567") == "1234567"

    def test_no_leading_number(self):
        assert extract_management_number("ABC_時計") == ""

    def test_empty_string(self):
        assert extract_management_number("") == ""

    def test_mixed_start(self):
        assert extract_management_number("99ABC") == "99"


class TestProductImages:
    """ProductImages データクラスのプロパティテスト"""

    def _make_product(self, num_images: int) -> ProductImages:
        """テスト用に指定枚数の画像パスを持つProductImagesを作成"""
        images = [Path(f"/tmp/img_{i:03d}.jpg") for i in range(num_images)]
        return ProductImages(
            product_id="test_product",
            management_number="1234567",
            folder_path=Path("/tmp/test"),
            images=images,
        )

    def test_front_image_exists(self):
        p = self._make_product(9)
        assert p.front_image == Path("/tmp/img_000.jpg")

    def test_front_image_empty(self):
        p = self._make_product(0)
        assert p.front_image is None

    def test_diagonal_image(self):
        p = self._make_product(9)
        assert p.diagonal_image == Path("/tmp/img_001.jpg")

    def test_diagonal_image_only_one(self):
        p = self._make_product(1)
        assert p.diagonal_image is None

    def test_back_cover_image(self):
        p = self._make_product(9)
        assert p.back_cover_image == Path("/tmp/img_007.jpg")

    def test_back_cover_image_insufficient(self):
        p = self._make_product(7)
        assert p.back_cover_image is None

    def test_comment_images_none(self):
        """9枚 → コメントシールなし"""
        p = self._make_product(9)
        assert p.comment_images == []
        assert p.has_comments is False

    def test_comment_images_one(self):
        """10枚 → コメントシール1枚"""
        p = self._make_product(10)
        assert len(p.comment_images) == 1
        assert p.comment_images[0] == Path("/tmp/img_009.jpg")
        assert p.has_comments is True

    def test_comment_images_two(self):
        """11枚 → コメントシール2枚"""
        p = self._make_product(11)
        assert len(p.comment_images) == 2
        assert p.has_comments is True

    def test_image_count(self):
        p = self._make_product(9)
        assert p.image_count == 9


class TestScanFolder:
    """scan_folder のテスト"""

    def _create_product_folder(self, parent: Path, name: str, num_images: int):
        """テスト用商品フォルダを作成"""
        folder = parent / name
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(num_images):
            (folder / f"{i + 1:03d}.jpg").touch()

    def test_scan_multiple_products(self, tmp_path):
        self._create_product_folder(tmp_path, "1234567_SEIKO", 9)
        self._create_product_folder(tmp_path, "1234568_OMEGA", 11)

        products = scan_folder(tmp_path)
        assert len(products) == 2
        ids = {p.product_id for p in products}
        assert "1234567_SEIKO" in ids
        assert "1234568_OMEGA" in ids

    def test_scan_empty_folder(self, tmp_path):
        """空フォルダ → 空リスト"""
        products = scan_folder(tmp_path)
        assert products == []

    def test_scan_images_sorted(self, tmp_path):
        """画像がファイル名ソート順であること"""
        folder = tmp_path / "1234567_test"
        folder.mkdir()
        for name in ["003.jpg", "001.jpg", "002.jpg"]:
            (folder / name).touch()

        products = scan_folder(tmp_path)
        assert len(products) == 1
        assert products[0].images[0].name == "001.jpg"
        assert products[0].images[1].name == "002.jpg"
        assert products[0].images[2].name == "003.jpg"

    def test_scan_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            scan_folder(Path("/nonexistent/path"))

    def test_scan_ignores_non_image_files(self, tmp_path):
        """画像以外のファイルは無視"""
        folder = tmp_path / "1234567_test"
        folder.mkdir()
        (folder / "001.jpg").touch()
        (folder / "readme.txt").touch()
        (folder / "data.csv").touch()

        products = scan_folder(tmp_path)
        assert len(products) == 1
        assert products[0].image_count == 1

    def test_scan_no_subdirs_uses_root(self, tmp_path):
        """サブフォルダなし → 直下の画像を1商品として扱う"""
        (tmp_path / "001.jpg").touch()
        (tmp_path / "002.jpg").touch()

        products = scan_folder(tmp_path)
        assert len(products) == 1

    def test_management_number_extracted(self, tmp_path):
        self._create_product_folder(tmp_path, "9876543_CASIO", 9)
        products = scan_folder(tmp_path)
        assert products[0].management_number == "9876543"
