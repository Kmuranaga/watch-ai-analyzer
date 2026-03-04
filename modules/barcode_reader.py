"""
バーコード読取モジュール
バーコード画像から管理番号（数字列）を読み取る
"""

import logging
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from config import BARCODE_ROTATIONS, BARCODE_SCALE_FACTOR

logger = logging.getLogger(__name__)

# pyzbarのインポート（オプショナル）
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    logger.warning("pyzbar が未インストールです。pip install pyzbar でインストールしてください。")


def read_barcode(image_path: Path) -> str | None:
    """
    バーコード画像から管理番号を読み取る。

    Args:
        image_path: バーコード画像のパス

    Returns:
        管理番号（文字列）。読取不可の場合はNone。
    """
    if not image_path or not image_path.exists():
        logger.error(f"バーコード画像が見つかりません: {image_path}")
        return None

    try:
        img = Image.open(image_path)
    except Exception as e:
        logger.error(f"画像の読み込みに失敗: {image_path} - {e}")
        return None

    # 前処理パイプライン: 元画像 → グレースケール → コントラスト強調 → リサイズ
    preprocessed_images = _preprocess_image(img)

    for processed_img in preprocessed_images:
        # 各回転角度を試行
        for rotation in BARCODE_ROTATIONS:
            rotated = processed_img.rotate(rotation, expand=True) if rotation != 0 else processed_img
            result = _try_decode(rotated)
            if result:
                logger.info(f"バーコード読取成功: {result} (回転: {rotation}°)")
                return result

    logger.warning(f"バーコード読取失敗: {image_path}")
    return None


def _preprocess_image(img: Image.Image) -> list[Image.Image]:
    """画像の前処理バリエーションを生成"""
    results = []

    # グレースケール変換
    gray = img.convert("L")
    results.append(gray)

    # コントラスト強調
    enhancer = ImageEnhance.Contrast(gray)
    high_contrast = enhancer.enhance(2.0)
    results.append(high_contrast)

    # シャープネス強調
    sharp = gray.filter(ImageFilter.SHARPEN)
    results.append(sharp)

    # 低解像度の場合はリサイズ
    w, h = gray.size
    if w < 500 or h < 500:
        scaled = gray.resize(
            (w * BARCODE_SCALE_FACTOR, h * BARCODE_SCALE_FACTOR),
            Image.LANCZOS
        )
        results.append(scaled)

    # 二値化（大津の方法の簡易版）
    threshold = 128
    binary = gray.point(lambda x: 255 if x > threshold else 0, "1")
    results.append(binary.convert("L"))

    return results


def _try_decode(img: Image.Image) -> str | None:
    """pyzbarでデコードを試行"""
    if not PYZBAR_AVAILABLE:
        return None

    try:
        decoded = pyzbar_decode(img)
        for obj in decoded:
            data = obj.data.decode("utf-8").strip()
            if data:
                return data
    except Exception as e:
        logger.debug(f"デコードエラー: {e}")

    return None
