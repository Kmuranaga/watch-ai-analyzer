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
  8枚目: 裏蓋正面
  9枚目: 裏蓋 ★AI解析
  10〜14枚目: コメントシール ★AI解析（存在時のみ・最大5枚。＃コメント/状態異常/針数）

ファイル名末尾に連番がある場合（例: 3099530_01.jpg 〜 3099530_12.jpg、3093691_08-.jpg）は
その番号で何枚目かを決める。撮影漏れで 09 が欠けても 10 以降が繰り上がらず、
「9枚目なし」を検出でき、コメントシールも10枚目以降として読める。
連番が付いていない／重複・範囲外があるフォルダは従来どおり並び順で判定する。
"""

import logging
import re
from pathlib import Path
from dataclasses import dataclass, field

from config import SUPPORTED_IMAGE_FORMATS, IDX_BACK_COVER, IDX_COMMENT_START, COMMENT_IMAGE_COUNT

logger = logging.getLogger(__name__)

# 画像枚数の期待値（バーコードなし）
IMAGES_MIN = 9   # 商品画像9枚（異常報告なし）
IMAGES_MAX = IDX_COMMENT_START + COMMENT_IMAGE_COUNT  # 商品画像9枚 + コメントシール最大N枚

# 裏蓋画像（9枚目）が無い商品の処理ステータス表記（single/batch/Web UI 共通）
BACK_COVER_MISSING_MSG = f"裏蓋エラー（{IDX_BACK_COVER + 1}枚目なし）"


@dataclass
class ProductImages:
    """商品ごとの画像パスリスト"""
    product_id: str          # フォルダ名全体
    management_number: str   # フォルダ名から抽出した管理番号
    folder_path: Path
    images: list[Path] = field(default_factory=list)
    # ファイル名の連番による配置（0始まりの位置 → 画像）。None なら images の並び順で判定
    slots: dict[int, Path] | None = None

    def image_at(self, idx: int) -> Path | None:
        """idx 番目（0始まり）の画像。欠番・枚数不足なら None"""
        if self.slots is not None:
            return self.slots.get(idx)
        return self.images[idx] if len(self.images) > idx else None

    @property
    def front_image(self) -> Path | None:
        """1枚目: 正面画像"""
        return self.image_at(0)

    @property
    def diagonal_image(self) -> Path | None:
        """2枚目: 斜め画像（バンド確認用）"""
        return self.image_at(1)

    @property
    def back_cover_image(self) -> Path | None:
        """9枚目: 裏蓋画像"""
        return self.image_at(IDX_BACK_COVER)

    @property
    def comment_images(self) -> list[Path]:
        """10枚目〜: コメントシール画像（存在する場合のみ・最大 COMMENT_IMAGE_COUNT 枚）"""
        return [
            img
            for i in range(IDX_COMMENT_START, IDX_COMMENT_START + COMMENT_IMAGE_COUNT)
            if (img := self.image_at(i)) is not None
        ]

    @property
    def has_comments(self) -> bool:
        """コメントシール画像が存在するか"""
        return bool(self.comment_images)

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


# ファイル名末尾の連番（"3099530_08" → 8, "3093691_08-" → 8, "001" → 1）。
# 4桁以上（DSC_0001 等のカメラ連番）は対象外。
_SEQ_RE = re.compile(r"(?:^|\D)(\d{1,3})\D*$")


def build_numbered_slots(images: list[Path]) -> dict[int, Path] | None:
    """全画像のファイル名に連番があれば {0始まり位置: 画像} を返す。

    1枚でも連番が読めない・番号が重複する・1〜IMAGES_MAX の範囲外なら None
    （並び順で判定する従来動作にフォールバック）。
    """
    slots: dict[int, Path] = {}
    for img in images:
        m = _SEQ_RE.search(img.stem)
        if not m:
            return None
        n = int(m.group(1))
        if not 1 <= n <= IMAGES_MAX or (n - 1) in slots:
            return None
        slots[n - 1] = img
    return slots


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
        slots=build_numbered_slots(images),
    )

    if product.slots is not None:
        missing = [i + 1 for i in range(IMAGES_MIN) if i not in product.slots]
        if missing:
            logger.warning(
                f"[{folder_name}] ファイル名の連番に欠番: "
                + "・".join(f"{n}枚目" for n in missing)
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
