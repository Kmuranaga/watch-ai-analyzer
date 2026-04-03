"""
フォルダスキャン・画像仕分けモジュール

対応データ構造: システム仕分け後データ（②）
  - 商品ごとにサブフォルダで分かれている
  - フォルダ名の形式: "1234567_商品名" （先頭の数字部分が管理番号）
  - バーコード画像は含まれない（システム側で読取済み）
  - フォルダ内には商品画像とコメントシール画像のみ

画像の並び順（ファイル名昇順ソート後）:
  1枚目: 正面画像 ★AI解析
  2枚目: 斜め
  3枚目: 側面1
  4枚目: 側面2
  5枚目: 側面3
  6枚目: 側面4
  7枚目: 裏蓋斜め
  8枚目: 裏蓋 ★AI解析
  9枚目: 裏蓋正面
  10枚目: コメントシール1 ★AI解析（存在時のみ）
  11枚目: コメントシール2 ★AI解析（存在時のみ）
"""

import logging
import re
from pathlib import Path
from dataclasses import dataclass, field

from config import SUPPORTED_IMAGE_FORMATS

logger = logging.getLogger(__name__)

# 画像枚数の期待値（バーコードなし）
IMAGES_MIN = 9   # 商品画像9枚（異常報告なし）
IMAGES_MAX = 11  # 商品画像9枚 + コメントシール最大2枚


@dataclass
class ProductImages:
    """商品ごとの画像パスリスト"""
    product_id: str          # フォルダ名全体
    management_number: str   # フォルダ名から抽出した管理番号
    folder_path: Path
    images: list[Path] = field(default_factory=list)

    @property
    def front_image(self) -> Path | None:
        """1枚目: 正面画像"""
        return self.images[0] if len(self.images) > 0 else None

    @property
    def diagonal_image(self) -> Path | None:
        """2枚目: 斜め画像（バンド確認用）"""
        return self.images[1] if len(self.images) > 1 else None

    @property
    def back_cover_image(self) -> Path | None:
        """8枚目: 裏蓋画像"""
        return self.images[7] if len(self.images) > 7 else None

    @property
    def comment_images(self) -> list[Path]:
        """10-11枚目: コメントシール画像（存在する場合のみ）"""
        result = []
        if len(self.images) > 9:
            result.append(self.images[9])
        if len(self.images) > 10:
            result.append(self.images[10])
        return result

    @property
    def has_comments(self) -> bool:
        """コメントシール画像が存在するか"""
        return len(self.images) > 9

    @property
    def image_count(self) -> int:
        return len(self.images)


def extract_management_number(folder_name: str) -> str:
    """
    フォルダ名の先頭から管理番号（数字列）を抽出する。

    対応パターン:
      "1234567_時計"       → "1234567"
      "1234567 SEIKO 時計" → "1234567"
      "1234567"            → "1234567"
      "ABC_時計"           → "" （数字で始まらない場合は空）

    Returns:
        管理番号の文字列。抽出できない場合は空文字。
    """
    match = re.match(r"^(\d+)", folder_name)
    if match:
        return match.group(1)
    return ""


def scan_folder(input_dir: Path) -> list[ProductImages]:
    """
    入力フォルダをスキャンし、商品ごとの画像リストを返す。

    期待するフォルダ構成:
      input/
      ├── 1234567_SEIKO セイコー/
      │   ├── 001.jpg   (正面)
      │   ├── 002.jpg   (斜め)
      │   ├── ...
      │   ├── 009.jpg   (裏蓋正面)
      │   ├── 010.jpg   (コメントシール1 ※あれば)
      │   └── 011.jpg   (コメントシール2 ※あれば)
      ├── 1234568_OMEGA オメガ/
      │   └── ...
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"入力フォルダが見つかりません: {input_dir}")

    products = []

    # サブフォルダを列挙
    subdirs = sorted([d for d in input_dir.iterdir() if d.is_dir()])

    if not subdirs:
        # サブフォルダがない場合: input直下の画像を1商品として扱う
        product = _scan_product_folder(input_dir, input_dir.name)
        if product:
            products.append(product)
    else:
        for subdir in subdirs:
            product = _scan_product_folder(subdir, subdir.name)
            if product:
                products.append(product)

    logger.info(f"スキャン完了: {len(products)} 商品を検出")
    return products


def _scan_product_folder(folder: Path, folder_name: str) -> ProductImages | None:
    """1つの商品フォルダをスキャンして画像リストを返す"""
    images = sorted([
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_FORMATS
    ])

    if not images:
        logger.warning(f"画像が見つかりません: {folder}")
        return None

    # フォルダ名から管理番号を抽出
    management_number = extract_management_number(folder_name)
    if not management_number:
        logger.warning(f"[{folder_name}] フォルダ名から管理番号を抽出できません")

    product = ProductImages(
        product_id=folder_name,
        management_number=management_number,
        folder_path=folder,
        images=images,
    )

    # 画像枚数チェック
    count = product.image_count
    if count < IMAGES_MIN:
        logger.warning(
            f"[{folder_name}] 画像枚数不足: {count}枚 (期待: {IMAGES_MIN}〜{IMAGES_MAX}枚)"
        )
    elif count > IMAGES_MAX:
        logger.warning(
            f"[{folder_name}] 画像枚数超過: {count}枚 (期待: {IMAGES_MIN}〜{IMAGES_MAX}枚)"
        )
    else:
        logger.info(
            f"[{folder_name}] {count}枚の画像を検出 "
            f"(管理番号: {management_number or '不明'})"
        )

    return product
