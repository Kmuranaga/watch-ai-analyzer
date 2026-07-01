"""画像前処理モジュール

針数判定の過剰検出（2針→3針）対策として、文字盤を中心クロップ＋拡大した画像を
生成する。拡大により細い針・傷・反射の知覚が安定し、誤って秒針を足す誤判定を抑える。
"""

import io
from pathlib import Path

from PIL import Image


def crop_dial_center(image_path: Path, frac: float = 0.55, size: int = 1024) -> Image.Image:
    """正面画像の中心を正方形にクロップし、size×size へ拡大した画像を返す。

    Args:
        image_path: 正面画像パス
        frac: クロップする一辺の長さ（短辺に対する割合）。小さいほど拡大率が高い。
        size: 出力画像の一辺（px）

    Returns:
        クロップ＋拡大した PIL Image（RGB）
    """
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    s = int(min(w, h) * frac)
    cx, cy = w // 2, h // 2
    box = (cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2)
    return im.crop(box).resize((size, size), Image.LANCZOS)


def crop_dial_to_bytes(image_path: Path, frac: float = 0.55, size: int = 1024) -> bytes:
    """crop_dial_center の結果を JPEG バイト列で返す（API 送信用）。"""
    img = crop_dial_center(image_path, frac, size)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def upscale_to_bytes(image_path: Path, scale: int = 2) -> bytes:
    """画像全体を切り取らず scale 倍に拡大した JPEG バイト列を返す。

    裏蓋の型番刻印はケース外周にあることが多く、中心クロップだと切れてしまう。
    そのため型番リカバリでは「切らずに拡大」して薄い刻印の判読性を上げる。
    """
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    im = im.resize((w * scale, h * scale), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()
