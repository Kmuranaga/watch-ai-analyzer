"""
設定ファイル（APIキー・パス等）
Watch AI Auto-Analysis System - Configuration
"""

import os
from pathlib import Path

# === プロジェクトルート ===
PROJECT_ROOT = Path(__file__).parent

# === APIキー ===
# 環境変数から取得。未設定の場合は空文字
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# === AIモデル設定 ===
AI_MODEL = "claude-opus-4-6"
AI_MAX_TOKENS = 2048
AI_TEMPERATURE = 0.0  # 解析精度重視のため低温設定

# === パス設定 ===
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
MAPPING_FILE = PROJECT_ROOT / "data" / "mapping.xlsx"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# === 画像設定 ===
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
IMAGES_PER_PRODUCT_MIN = 10
IMAGES_PER_PRODUCT_MAX = 12

# === 画像インデックス（0始まり） ===
IDX_BARCODE = 0       # 1枚目: バーコード
IDX_FRONT = 1         # 2枚目: 正面画像
IDX_BACK_COVER = 8    # 9枚目: 裏蓋画像
IDX_COMMENT1 = 10     # 11枚目: コメントシール1
IDX_COMMENT2 = 11     # 12枚目: コメントシール2

# === バーコード設定 ===
BARCODE_ROTATIONS = [0, 90, 180, 270]
BARCODE_SCALE_FACTOR = 2  # 低解像度画像の拡大倍率

# === リトライ設定 ===
API_MAX_RETRIES = 3
API_RETRY_BASE_DELAY = 2  # 秒（指数バックオフの基底）

# === タイトル生成設定 ===
TITLE_MAX_LENGTH = 65

# === CSV出力設定 ===
CSV_ENCODING = "utf-8-sig"  # BOM付きUTF-8（Excel互換）

# === Batch API設定 ===
BATCH_API_ENABLED = True  # Batch APIを利用するか（50%割引）
