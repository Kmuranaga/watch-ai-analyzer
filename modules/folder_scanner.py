"""
フォルダスキャン・画像仕分けモジュール
入力フォルダ内の画像を商品単位にグルーピングする
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field

from config import SUPPORTED_IMAGE_FORMATS, IMAGES_PER_PRODUCT_MIN, IMAGES_PER_PRODUCT_MAX

logger = logging.getLogger(__name__)


@dataclass
class ProductImages:
    """商品ごとの画像パスリスト"""
    product_id: str  # フォルダ名 or 連番
    folder_path: Path
    images: list[Path] = field(default_factory=list)

    @property
    def barcode_image(self) -> Path | None:
        """1枚目: バーコード画像"""
        return self.images[0] if len(self.images) > 0 else None

    @property
    def front_image(self) -> Path | None:
        """2枚目: 正面画像"""
        return self.images[1] if len(self.images) > 1 else None

    @property
    def back_cover_image(self) -> Path | None:
        """9枚目: 裏蓋画像"""
        return self.images[8] if len(self.images) > 8 else None

    @property
    def comment_images(self) -> list[Path]:
        """11-12枚目: コメントシール画像（存在する場合のみ）"""
        result = []
        if len(self.images) > 10:
            result.append(self.images[10])
        if len(self.images) > 11:
            result.append(self.images[11])
        return result

    @property
    def has_comments(self) -> bool:
        """コメントシール画像が存在するか"""
        return len(self.images) > 10

    @property
    def image_count(self) -> int:
        return len(self.images)


def scan_folder(input_dir: Path) -> list[ProductImages]:
    """
    入力フォルダをスキャンし、商品ごとの画像リストを返す。

    フォルダ構成パターン:
    パターンA: input/ 直下にサブフォルダ（1商品=1サブフォルダ）
        input/
        ├── item001/
        │   ├── 001.jpg
        │   ├── 002.jpg
        │   └── ...
        ├── item002/
        │   └── ...

    パターンB: input/ 直下に画像ファイルが並ぶ（1商品分のみ）
        input/
        ├── 001.jpg
        ├── 002.jpg
        └── ...
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"入力フォルダが見つかりません: {input_dir}")

    products = []

    # パターンA: サブフォルダがある場合
    subdirs = sorted([d for d in input_dir.iterdir() if d.is_dir()])
    if subdirs:
        for subdir in subdirs:
            product = _scan_product_folder(subdir, subdir.name)
            if product:
                products.append(product)
    else:
        # パターンB: 直下に画像がある場合
        product = _scan_product_folder(input_dir, input_dir.name)
        if product:
            products.append(product)

    logger.info(f"スキャン完了: {len(products)} 商品を検出")
    return products


def _scan_product_folder(folder: Path, product_id: str) -> ProductImages | None:
    """1つの商品フォルダをスキャンして画像リストを返す"""
    images = sorted([
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_FORMATS
    ])

    if not images:
        logger.warning(f"画像が見つかりません: {folder}")
        return None

    product = ProductImages(
        product_id=product_id,
        folder_path=folder,
        images=images,
    )

    # 画像枚数チェック
    count = product.image_count
    if count < IMAGES_PER_PRODUCT_MIN:
        logger.warning(
            f"[{product_id}] 画像枚数不足: {count}枚 "
            f"(期待: {IMAGES_PER_PRODUCT_MIN}〜{IMAGES_PER_PRODUCT_MAX}枚)"
        )
    elif count > IMAGES_PER_PRODUCT_MAX:
        logger.warning(
            f"[{product_id}] 画像枚数超過: {count}枚 "
            f"(期待: {IMAGES_PER_PRODUCT_MIN}〜{IMAGES_PER_PRODUCT_MAX}枚)"
        )
    else:
        logger.info(f"[{product_id}] {count}枚の画像を検出")

    return product
