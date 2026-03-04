"""
データ正規化モジュール
AIから取得したテキストを統一フォーマットに変換する
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def normalize_all(data: dict) -> dict:
    """全フィールドに正規化処理を適用する"""
    result = data.copy()

    # ブランド名正規化
    if result.get("brand_en"):
        result["brand_en"] = normalize_brand(result["brand_en"])

    # シリーズ名正規化
    if result.get("series_en"):
        result["series_en"] = normalize_text(result["series_en"]).upper()

    # 素材名正規化
    if result.get("material"):
        result["material"] = normalize_material(result["material"])

    # ムーブメント正規化
    if result.get("movement_type"):
        result["movement_type"] = normalize_movement(result["movement_type"])

    # 防水表記正規化
    if result.get("water_resistance"):
        result["water_resistance"] = normalize_water_resistance(result["water_resistance"])

    # 型番正規化
    if result.get("model_number"):
        result["model_number"] = normalize_text(result["model_number"])

    return result


def normalize_text(text: str) -> str:
    """基本的なテキスト正規化（空白除去・全角→半角）"""
    if not text:
        return ""

    # 前後の空白を除去
    text = text.strip()

    # 全角英数字→半角変換
    text = unicodedata.normalize("NFKC", text)

    # 連続空白を1つに
    text = re.sub(r"\s+", " ", text)

    return text


def normalize_brand(brand: str) -> str:
    """ブランド名を大文字に統一"""
    brand = normalize_text(brand)
    return brand.upper()


# === 素材名変換テーブル ===
MATERIAL_MAP = {
    # ステンレス
    "stainless steel": "ステンレス",
    "stainless": "ステンレス",
    "st.steel": "ステンレス",
    "st. steel": "ステンレス",
    "ss": "ステンレス",
    "sus": "ステンレス",
    "ステンレススチール": "ステンレス",
    "ステンレス": "ステンレス",
    # チタン
    "titanium": "チタン",
    "ti": "チタン",
    "チタン": "チタン",
    "チタニウム": "チタン",
    # 金
    "gold": "金",
    "gold plated": "金メッキ",
    "gp": "金メッキ",
    "gold filled": "金張り",
    "gf": "金張り",
    "k18": "18金",
    "18k": "18金",
    "750": "18金",
    "k14": "14金",
    "14k": "14金",
    "585": "14金",
    # 銀
    "silver": "銀",
    "ag": "銀",
    "925": "シルバー925",
    "sterling silver": "シルバー925",
    # セラミック
    "ceramic": "セラミック",
    "セラミック": "セラミック",
    # 樹脂
    "resin": "樹脂",
    "plastic": "樹脂",
    "プラスチック": "樹脂",
    "樹脂": "樹脂",
    # ベースメタル
    "base metal": "ベースメタル",
    "alloy": "合金",
    "brass": "真鍮",
    # コンビ
    "combination": "コンビ",
    "combi": "コンビ",
    "two-tone": "コンビ",
}


def normalize_material(material: str) -> str:
    """素材名を統一形式に変換"""
    if not material:
        return ""

    normalized = normalize_text(material).lower()

    # 完全一致で検索
    if normalized in MATERIAL_MAP:
        return MATERIAL_MAP[normalized]

    # 部分一致で検索
    for key, value in MATERIAL_MAP.items():
        if key in normalized:
            return value

    # 日本語の場合はそのまま返す
    if any(ord(c) > 0x3000 for c in material):
        return material.strip()

    # マッチしない場合はそのまま
    logger.debug(f"素材名の変換なし: {material}")
    return material.strip()


# === ムーブメント変換テーブル ===
MOVEMENT_MAP = {
    "quartz": "Quartz",
    "qz": "Quartz",
    "q": "Quartz",
    "クォーツ": "Quartz",
    "クオーツ": "Quartz",
    "automatic": "Automatic",
    "auto": "Automatic",
    "自動巻き": "Automatic",
    "自動巻": "Automatic",
    "オートマチック": "Automatic",
    "mechanical": "Automatic",
    "solar": "Solar",
    "ソーラー": "Solar",
    "eco-drive": "Solar",
    "エコドライブ": "Solar",
    "hand-wound": "Hand-wound",
    "hand wound": "Hand-wound",
    "manual": "Hand-wound",
    "手巻き": "Hand-wound",
    "手巻": "Hand-wound",
    "kinetic": "Kinetic",
    "キネティック": "Kinetic",
    "spring drive": "Spring Drive",
    "スプリングドライブ": "Spring Drive",
}


def normalize_movement(movement: str) -> str:
    """ムーブメント種別を統一形式に変換"""
    if not movement:
        return ""

    normalized = normalize_text(movement).lower()

    if normalized in MOVEMENT_MAP:
        return MOVEMENT_MAP[normalized]

    # 部分一致
    for key, value in MOVEMENT_MAP.items():
        if key in normalized:
            return value

    logger.debug(f"ムーブメントの変換なし: {movement}")
    return movement.strip()


# === 防水表記変換 ===
WATER_RESISTANCE_PATTERNS = [
    (r"(\d+)\s*bar", lambda m: f"{m.group(1)}BAR"),
    (r"(\d+)\s*atm", lambda m: f"{m.group(1)}BAR"),
    (r"(\d+)\s*m\b", lambda m: _meters_to_bar(int(m.group(1)))),
    (r"water\s*resist(?:ant)?", lambda m: "日常生活防水"),
    (r"wr\b", lambda m: "日常生活防水"),
    (r"waterproof", lambda m: "防水"),
    (r"日常生活防水", lambda m: "日常生活防水"),
]


def _meters_to_bar(meters: int) -> str:
    """メートル表記をBAR表記に変換"""
    bar = meters // 10
    if bar > 0:
        return f"{bar}BAR"
    return "日常生活防水"


def normalize_water_resistance(water: str) -> str:
    """防水表記を統一形式に変換"""
    if not water:
        return ""

    normalized = normalize_text(water).lower()

    for pattern, formatter in WATER_RESISTANCE_PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            return formatter(match)

    # マッチしない場合はそのまま
    logger.debug(f"防水表記の変換なし: {water}")
    return water.strip()
