"""
設定ファイル（APIキー・パス等）
Watch AI Auto-Analysis System - Configuration
"""

import os
from pathlib import Path

# === プロジェクトルート ===
PROJECT_ROOT = Path(__file__).parent

# === .envファイル読み込み ===
_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            if "=" in _line:
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip().strip("'\"")
                if _key and _key not in os.environ:
                    os.environ[_key] = _val

# === APIキー ===
# 環境変数 or .envファイルから取得。未設定の場合は空文字
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# === AIモデル設定 ===
AI_MODEL = "gemini-2.5-pro"
# gemini-2.5-pro は思考(thinking)トークンも max_output_tokens を消費する。
# 2048 では思考が枠を食い尽くし、出力が空(text=None)や途中切断したJSONになって
# 解析が間欠的に失敗する（裏蓋型番の抽出漏れの主因）。出力JSON自体は数百トークンと
# 小さいため、思考分の余裕を確保するために十分大きな値にする。
AI_MAX_TOKENS = 8192
AI_TEMPERATURE = 0.0  # 解析精度重視のため低温設定

# === パス設定 ===
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
MAPPING_FILE = PROJECT_ROOT / "data" / "mapping.xlsx"
CATEGORY_NAME_FILE = PROJECT_ROOT / "data" / "category_names.xlsx"
HAND_COUNT_LABELS_FILE = PROJECT_ROOT / "data" / "hand_count_labels.xlsx"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

# === 画像設定 ===
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}

# === 画像インデックス（0始まり、バーコードなし） ===
# システム仕分け後データ: バーコード画像は含まれない
IDX_FRONT = 0         # 1枚目: 正面画像
IDX_BACK_COVER = 7    # 8枚目: 裏蓋画像
IDX_COMMENT1 = 9      # 10枚目: コメントシール1
IDX_COMMENT2 = 10     # 11枚目: コメントシール2
IDX_COMMENT3 = 11    # 12枚目: コメントシール3（針数コメント等）

# === リトライ設定 ===
API_MAX_RETRIES = 2
API_RETRY_BASE_DELAY = 2  # 秒（指数バックオフの基底）
API_RETRY_MAX_DELAY = 60  # リトライ待機の上限（秒）

# === CSV出力設定 ===
CSV_ENCODING = "utf-8-sig"  # BOM付きUTF-8（Excel互換）

# === Batch API設定 ===
BATCH_API_ENABLED = True  # Batch APIを利用するか（50%割引）

# === 並列処理設定 ===
MAX_CONCURRENT_PRODUCTS = 3  # 同時処理する商品数の上限
MAX_CONCURRENT_API_CALLS = 3  # 1商品内の同時API呼び出し数（正面・裏蓋・コメント）
