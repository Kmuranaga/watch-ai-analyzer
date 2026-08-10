"""
データ正規化モジュール
AIから取得したテキストを統一フォーマットに変換する
"""

import logging
import re
import unicodedata
from collections import Counter

from config import DISCARD_NON_PRINTED_BRAND

logger = logging.getLogger(__name__)


def normalize_all(data: dict) -> dict:
    """全フィールドに正規化処理を適用する"""
    result = data.copy()

    # 正面ブランドと裏蓋刻印ブランドの整合
    # （文字盤=製品ブランド優先、裏蓋=補完/整合。判定詳細は reconcile_brand を参照）
    _reconcile_brand_fields(result)

    # ブランド名正規化
    if result.get("brand_en"):
        result["brand_en"] = normalize_brand(result["brand_en"])

    # シリーズ名正規化（大文字化＋SEIKO略称の展開＋機能語除去。展開はブランド整合後の brand_en を使う）
    if result.get("series_en"):
        brand_for_series = result.get("brand_en", "")
        pre_series = normalize_text(result["series_en"]).upper()
        alias_expanded = (
            normalize_brand(brand_for_series) == "SEIKO"
            and pre_series in SEIKO_SERIES_ALIAS
        )
        result["series_en"] = normalize_series(result["series_en"], brand_for_series)
        # 略称展開が発火した場合のみ、対応するカナでAIの誤カナ（例: LK→"エルケー"）を上書きする
        if alias_expanded:
            kana = SEIKO_SERIES_ALIAS_KANA.get(result["series_en"])
            if kana:
                result["series_kana"] = kana

        # 機能語除去（CHRONOGRAPH等）で落ちたトークンがあれば、シリーズカナからも
        # 対応する語を取り除く。片方だけ残るとタイトルで針数・ムーブメント等と
        # 同じ語が二重に出る（実例 2999571: series_en="CHRONOGRAPH" / series_kana=
        # "クロノグラフ" と針数「クロノグラフ」）。例外ペア（SWATCH CHRONO等）は
        # 除去語が発生しないため不発火のまま。
        removed_words = [
            w for w in pre_series.split()
            if w in SERIES_FUNCTION_WORDS and w not in result["series_en"].split()
        ]
        if removed_words:
            if not result["series_en"]:
                result["series_kana"] = ""
            else:
                kana = result.get("series_kana", "")
                for word in removed_words:
                    for token in SERIES_FUNCTION_WORD_KANA.get(word, ()):
                        kana = kana.replace(token, "")
                result["series_kana"] = normalize_text(kana)

    # 素材名正規化
    if result.get("material"):
        result["material"] = normalize_material(result["material"])

    # ムーブメント正規化
    if result.get("movement_type"):
        result["movement_type"] = normalize_movement(result["movement_type"])

    # 防水表記正規化
    if result.get("water_resistance"):
        result["water_resistance"] = normalize_water_resistance(result["water_resistance"])

    # 型番正規化（モジュール番号・機能語の除去含む）
    if result.get("model_number"):
        result["model_number"] = normalize_model_number(
            result["model_number"], result.get("brand_en", "")
        )

    # 本体色正規化（軽い正規化のみ。色名はそのまま通す）
    if result.get("body_color"):
        result["body_color"] = normalize_text(result["body_color"])

    # 文字盤色正規化（軽い正規化のみ）
    if result.get("dial_color"):
        result["dial_color"] = normalize_text(result["dial_color"])

    # 針数正規化（表記ゆれ吸収）
    if result.get("hand_count"):
        result["hand_count"] = normalize_hand_count(result["hand_count"])

    # ケース形状正規化
    if result.get("case_shape"):
        result["case_shape"] = normalize_case_shape(result["case_shape"])

    # 性別正規化
    if result.get("gender"):
        result["gender"] = normalize_gender(result["gender"])

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


# === SEIKO ヴィンテージのシリーズ略称 → 正式名 ===
# 文字盤には略称（LM 等）のみ刻印されることがあり、AI もそのまま略称で出力する。
# （AI 側は series_kana で「ロードマチック」等を出せているが series_en は略称のまま）
# これらは SEIKO 固有の標準的な略称なので、誤展開を防ぐためブランド=SEIKO のときのみ適用する。
SEIKO_SERIES_ALIAS = {
    "LM": "LORD MATIC",
    "KS": "KING SEIKO",
    "GS": "GRAND SEIKO",
    "LK": "LUKIA",  # LUKIA の文字盤刻印は "lk" ロゴのみのため略称のまま出力されがち
}


# === 略称展開後の正式シリーズ名に対応するカナ ===
# 展開が発火した場合のみ、AIの誤カナ（例: LK→"エルケー"）をこちらで上書きする。
SEIKO_SERIES_ALIAS_KANA = {
    "LORD MATIC": "ロードマチック",
    "KING SEIKO": "キングセイコー",
    "GRAND SEIKO": "グランドセイコー",
    "LUKIA": "ルキア",
}


def normalize_series(series: str, brand: str = "") -> str:
    """シリーズ名を正規化（大文字化＋SEIKO略称の展開＋機能語の除去）。

    - SEIKO の標準的なシリーズ略称（LM/KS/GS）のみ正式名へ展開する。
      他ブランドで同綴りが別義になる誤展開を避けるため、ブランド=SEIKO に限定する。
    - 仕様・機能語トークン（CHRONOGRAPH, QUARTZ 等）を除去する（仕様書4.4）。
      対象は「空白区切りの単独トークン」のみ。型番側（normalize_model_number）と
      異なりハイフンでは分割しない（CHRONO-MATIC / ANA-DIGI 等、ハイフン結合が
      名称の一部である実在シリーズを壊すため）。部分一致もしない
      （BREITLING CHRONOMAT を守る）。
    """
    s = normalize_text(series).upper()
    if normalize_brand(brand) == "SEIKO":
        s = SEIKO_SERIES_ALIAS.get(s, s)
    return _strip_series_function_words(s, brand)


def _strip_series_function_words(series: str, brand: str = "") -> str:
    """正規化済み（大文字）シリーズから機能語トークンを除去する。"""
    if not series:
        return ""
    if (normalize_brand(brand), series) in SERIES_FUNCTION_WORD_EXCEPTIONS:
        return series
    tokens = series.split()
    kept = [t for t in tokens if t not in SERIES_FUNCTION_WORDS]
    if len(kept) == len(tokens):
        return series
    result = " ".join(kept)
    logger.info(f"シリーズから機能語を除去: {series!r} → {result!r}")
    return result


# === ケース製造元・裏蓋材質の刻印 ===
# ヴィンテージ国産時計の裏蓋には □囲みの STAR 等ケース製造元の刻印が打刻される。
# 製品ブランドではないので、ブランドの補完にもシリーズの補完にも使わない。
# （ブランド補完は既知ブランド・ホワイトリストでも守られるが、シリーズ側の
# 混入防止はこのリストが担うため whitelist 導入後も必要）
CASE_MAKERS = {
    "STAR",             # □STAR: ケースメーカー刻印（CITIZEN/SEIKO 等のケースに打刻）
    "EVERBRIGHT",       # EVERBRIGHT BACK: 裏蓋材質表記（AIは通常こちらに切り出す）
    "EVERBRIGHT BACK",  # 同上の刻印生値バリアント
    # 注意: 部分一致にすると実在シリーズ（SEVEN STAR, THREE STAR 等）を誤って
    # 消すため、必ず完全一致（リテラル追加）で拡張すること
}


# === 裏蓋補完に使ってよい既知ブランド（mapping.xlsx 由来）===
# 起動時に set_known_brands(mapper.known_brand_names()) で登録する。
# 未登録（空）のままなら裏蓋からのブランド補完は一切行わない（安全側）。
_KNOWN_BRANDS: set[str] = set()


def set_known_brands(brands) -> None:
    """裏蓋刻印からのブランド補完で採用してよい既知ブランド名を登録する。

    mapping.xlsx のブランド名・別名（CategoryMapper.known_brand_names()）を
    起動時に渡す想定。正規化（大文字化）して保持する。
    """
    global _KNOWN_BRANDS
    _KNOWN_BRANDS = {normalize_brand(b) for b in brands if b and str(b).strip()}


def reconcile_brand(front_brand: str, back_brand: str, front_conf=None):
    """
    正面（文字盤）ブランドと裏蓋刻印ブランドを整合し、採用ブランドと採用元を返す。

    文字盤最優先仕様（2026-07-24 クライアント合意の仕様変更）:
      1. fb がある → 常に fb（裏蓋刻印による上書きは行わない）
      2. fb が空で bb がある → bb が既知ブランド（set_known_brands 登録分）かつ
         ケースメーカー刻印（CASE_MAKERS）でない場合のみ bb で補完
         （裏蓋にはケースメーカー・ベルトメーカー・シリーズ名等、製品ブランドで
         ない文字が刻印されることがあり、未知の文字列は採用しない。例: □STAR,
         ELMITEX, Flagship）
      3. どちらも採用できない → ""（人手確認へ）

    旧仕様にあった「裏蓋の実ブランド刻印による正面誤読の是正」（例: ELGIN）は
    この仕様変更で廃止された。文字盤の誤読はそのまま出力され、目視確認で修正する。

    Args:
        front_brand: 正面ブランド（生文字列可）
        back_brand: 裏蓋刻印ブランド（生文字列可）
        front_conf: 後方互換のため受け付けるが判定には使用しない。

    Returns:
        (brand, source): brand は正規化済みブランド、
                         source は "front" / "back" / ""
    """
    fb = normalize_brand(front_brand) if front_brand else ""
    bb = normalize_brand(back_brand) if back_brand else ""

    # 1. 文字盤最優先: 文字盤で読めていれば裏蓋では上書きしない
    if fb:
        return fb, "front"

    # 2. 表が判読不可 → 既知ブランドの裏蓋刻印のみ補完に使う
    if bb and bb in _KNOWN_BRANDS and bb not in CASE_MAKERS:
        return bb, "back"

    # 3. 採用できるブランドなし
    return "", ""


def _reconcile_brand_fields(result: dict) -> None:
    """
    normalize_all 内でブランド/シリーズの整合を行い、result を直接更新する。

    - reconcile_brand で最終ブランドと採用元を決定し brand_en に設定。
    - シリーズ・かなは採用元に合わせて front/back を採用（採用元が空なら他方で補完）。
    - 裏蓋用の一時キー（back_*）は出力に残さないよう pop する。
    """
    # brand_evidence による破棄（既定 OFF。プロンプト単独で推定が止まらない場合の保険）
    # 文字盤に文字が無いのに brand_en が埋まっている＝自己申告根拠が printed_text 以外、
    # というケースを破棄する。brand_evidence キーが無い・空文字なら従来どおり採用する。
    if DISCARD_NON_PRINTED_BRAND:
        front_brand_en = result.get("brand_en", "")
        brand_evidence = result.get("brand_evidence", "")
        if front_brand_en and brand_evidence and brand_evidence != "printed_text":
            logger.info(f"正面ブランドを破棄（brand_evidence={brand_evidence!r}）: {front_brand_en}")
            result["brand_en"] = ""
            result["brand_kana"] = ""

    # ケースメーカー・材質刻印（□STAR, EVERBRIGHT 等）は製品ブランドでもシリーズでもないため、
    # ブランド整合・補完に入る前に裏蓋読み取り値から除外する
    # （例: 2959931 の「EVERBRIGHT BACK」が back_series 経由でタイトルに混入するのを防ぐ）
    if normalize_brand(result.get("back_brand_en", "") or "") in CASE_MAKERS:
        result["back_brand_en"] = ""
        result["back_brand_kana"] = ""
    if normalize_brand(result.get("back_series_en", "") or "") in CASE_MAKERS:
        result["back_series_en"] = ""
        result["back_series_kana"] = ""

    front_brand = result.get("brand_en", "")
    back_brand = result.get("back_brand_en", "")
    front_conf = (result.get("confidence") or {}).get("brand")

    final_brand, source = reconcile_brand(front_brand, back_brand, front_conf)
    result["brand_en"] = final_brand
    result["brand_source"] = source  # 診断用（採用元 front/back/""）。CSV出力には影響しない

    front_series = result.get("series_en", "")
    back_series = result.get("back_series_en", "")
    front_brand_kana = result.get("brand_kana", "")
    back_brand_kana = result.get("back_brand_kana", "")
    front_series_kana = result.get("series_kana", "")
    back_series_kana = result.get("back_series_kana", "")

    if source == "back":
        result["series_en"] = back_series or front_series
        result["brand_kana"] = back_brand_kana or front_brand_kana
        result["series_kana"] = back_series_kana or front_series_kana
    elif source == "front":
        result["series_en"] = front_series or back_series
        result["brand_kana"] = front_brand_kana or back_brand_kana
        result["series_kana"] = front_series_kana or back_series_kana
    # source == "" の場合は既存値（基本空）を維持

    # 裏蓋用の一時キーは出力に残さない
    for key in ("back_brand_en", "back_brand_kana",
                "back_series_en", "back_series_kana", "back_confidence",
                "brand_evidence"):
        result.pop(key, None)


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
# 画像にQz/quartz表記あり→クォーツ、Automatic表記あり→自動巻きのみ出力
# Hand-wound（手巻き）は画像からは判別不可のため出力しない
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
    "kinetic": "Kinetic",
    "キネティック": "Kinetic",
    "spring drive": "Spring Drive",
    "スプリングドライブ": "Spring Drive",
}

# Hand-wound系はヒットしても空文字を返す（出力しない）
MOVEMENT_IGNORE = {
    "hand-wound", "hand wound", "manual", "手巻き", "手巻",
}


def normalize_movement(movement: str) -> str:
    """ムーブメント種別を統一形式に変換。手巻き系は空文字を返す。"""
    if not movement:
        return ""

    normalized = normalize_text(movement).lower()

    # 手巻き系は出力しない
    if normalized in MOVEMENT_IGNORE:
        logger.debug(f"ムーブメント除外（手巻き）: {movement}")
        return ""

    for key in MOVEMENT_IGNORE:
        if key in normalized:
            logger.debug(f"ムーブメント除外（手巻き部分一致）: {movement}")
            return ""

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


# === ケース形状変換テーブル ===
CASE_SHAPE_MAP = {
    "ラウンド": "ラウンド",
    "丸": "ラウンド",
    "丸型": "ラウンド",
    "round": "ラウンド",
    "スクエア": "スクエア",
    "四角": "スクエア",
    "四角型": "スクエア",
    "square": "スクエア",
    "レクタンギュラー": "レクタンギュラー",
    "長方形": "レクタンギュラー",
    "縦長": "レクタンギュラー",
    "rectangular": "レクタンギュラー",
    "rectangle": "レクタンギュラー",
}


# === 性別変換テーブル ===
GENDER_MAP = {
    "mens": "メンズ",
    "men": "メンズ",
    "men's": "メンズ",
    "male": "メンズ",
    "メンズ": "メンズ",
    "男性": "メンズ",
    "男": "メンズ",
    "ladies": "レディース",
    "lady": "レディース",
    "ladies'": "レディース",
    "women": "レディース",
    "women's": "レディース",
    "female": "レディース",
    "レディース": "レディース",
    "女性": "レディース",
    "女": "レディース",
    "unisex": "ユニセックス",
    "uni-sex": "ユニセックス",
    "ユニセックス": "ユニセックス",
    "男女兼用": "ユニセックス",
    "unknown": "不明",
    "不明": "不明",
}


def normalize_gender(gender: str) -> str:
    """性別を統一形式（メンズ/レディース/ユニセックス/不明）に変換"""
    if not gender:
        return ""

    normalized = normalize_text(gender).lower()

    if normalized in GENDER_MAP:
        return GENDER_MAP[normalized]

    # 部分一致
    for key, value in GENDER_MAP.items():
        if key in normalized:
            return value

    logger.debug(f"性別の変換なし: {gender}")
    return gender.strip()


def normalize_case_shape(shape: str) -> str:
    """ケース形状を統一形式（ラウンド/スクエア/レクタンギュラー）に変換"""
    if not shape:
        return ""

    normalized = normalize_text(shape).lower()

    if normalized in CASE_SHAPE_MAP:
        return CASE_SHAPE_MAP[normalized]

    for key, value in CASE_SHAPE_MAP.items():
        if key in normalized:
            return value

    logger.debug(f"ケース形状の変換なし: {shape}")
    return shape.strip()


# === 針数の漢数字→算用数字テーブル ===
_KANJI_NUM_MAP = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6"}


def normalize_hand_count(hand_count: str) -> str:
    """
    針数の表記ゆれを吸収する。
    "2針"/"二針"/"2 針"/"2本" → "2針"、"digital"/"デジタル表示" → "デジタル"、
    クロノグラフ系 → "クロノグラフ" に統一する。
    マッチしない場合は基本正規化した文字列をそのまま返す。
    """
    if not hand_count:
        return ""

    normalized = normalize_text(hand_count)

    # クロノグラフ判定（針数表記より優先）
    if "クロノ" in normalized or "chrono" in normalized.lower():
        return "クロノグラフ"

    # デジタル判定
    if "デジタル" in normalized or "digital" in normalized.lower():
        return "デジタル"

    # 漢数字を算用数字へ変換してから判定
    converted = normalized
    for kanji, num in _KANJI_NUM_MAP.items():
        converted = converted.replace(kanji, num)

    # "N針"/"N本"（間に空白があっても許容）→ "N針"
    match = re.search(r"(\d+)\s*(?:針|本)", converted)
    if match:
        return f"{match.group(1)}針"

    logger.debug(f"針数の変換なし: {hand_count}")
    return normalized


# === 型番から除去する機能語・仕様語（顧客分析で判明した3類型のうち(c)） ===
# 大文字単独トークンとして出現したものを除去する
MODEL_NUMBER_FUNCTION_WORDS = {
    "AUTOMATIC", "AUTO", "QUARTZ", "CHRONOGRAPH", "CHRONO",
    "TOOL", "DIAMOND", "DIAMONDS", "ANALOG", "DIGITAL",
    "WATER", "RESIST", "RESISTANT", "STAINLESS", "STEEL",
    "JAPAN", "MOVT", "MOVEMENT", "DIAL", "CASE", "BACK",
    "MENS", "LADIES",
}

# === シリーズ名から除去する機能語・仕様語（上記4.2(c)と同系統） ===
# 文字盤のサブダイヤル周辺・ベゼル・裏蓋には CHRONOGRAPH / QUARTZ / WATER RESISTANT 等の
# 仕様表記が印字されており、AIがこれをシリーズ名として読み取ることがある
# （実例 2999571: 文字盤 "Town & Country Surf Designs / Chronograph / 10 bar" →
#   series_en="CHRONOGRAPH"。タイトルで針数「クロノグラフ」と重複した）。
# これらはタイトルの別項目（針数・ムーブメント・防水・素材・性別）に既に出るため
# シリーズ欄からは落とす。
#
# MODEL_NUMBER_FUNCTION_WORDS のサブセット。除外した語
# （TOOL/DIAMOND/DIAMONDS/DIAL/CASE/BACK）は、実在シリーズ名に一般英単語として
# 紛れ込むリスクの方が高く、かつ重複出力の実害報告が無いため対象外。
SERIES_FUNCTION_WORDS = MODEL_NUMBER_FUNCTION_WORDS - {
    "TOOL", "DIAMOND", "DIAMONDS", "DIAL", "CASE", "BACK",
}

# 上記の機能語だけで構成されるが、mapping.xlsx に実在シリーズとして登録されている
# （ブランド, シリーズ）の組。除去せずそのまま残す。
# mapping.xlsx にシリーズを追加する際、その名称が SERIES_FUNCTION_WORDS の語だけで
# 構成される場合はここにも追加すること（2026-08時点の該当は下記1件のみ）
SERIES_FUNCTION_WORD_EXCEPTIONS = {
    ("SWATCH", "CHRONO"),  # mapping.xlsx 登録シリーズ・カテゴリ2084024477
}

# 機能語を除去した際、シリーズカナからも併せて取り除く対応表。
# 長い表記を先に置くこと（"クロノグラフ" より先に "クロノ" を消すと「グラフ」が残る）
SERIES_FUNCTION_WORD_KANA = {
    "CHRONOGRAPH": ("クロノグラフ", "クロノ"),
    "CHRONO": ("クロノグラフ", "クロノ"),
    "QUARTZ": ("クォーツ", "クオーツ"),
    "AUTOMATIC": ("オートマチック", "自動巻き", "自動巻"),
    "DIGITAL": ("デジタル",),
    "ANALOG": ("アナログ",),
    "STAINLESS": ("ステンレス",),
    "STEEL": ("スチール",),
}

# 先頭のモジュール番号パターン（例 CASIO G-SHOCK の "5081-GA-100CF" の "5081-"）
_MODULE_PREFIX_RE = re.compile(r"^\d{3,4}-")


def normalize_model_number(model_number: str, brand_en: str = "") -> str:
    """
    AIが読み取った型番を正規化する。顧客分析で判明した3類型を吸収する。

    (a) モジュール番号混在（例 "5081-GA-100CF"）
        → 先頭の "^\\d{3,4}-" を除去し "GA-100CF" を採用
    (b) モジュール番号のみ（ハイフンなしの短い数字・≤4桁。例 "5196", "1647"）
        → 型番不明として空文字を返す（マスタ照合・出力から除外）
        ※ ハイフン区切りの数字や5桁以上の数字は、和製ヴィンテージ等の
           正当な数字型番（例 SEIKO "6119-8030", "29014"）として保持する
    (c) 機能語混在（AUTOMATIC, QUARTZ 等の仕様・機能語）
        → 型番欄から除去

    基本正規化（大文字化・前後空白除去・全角半角統一・ハイフン前後空白除去）も行う。

    Args:
        model_number: AI解析の型番文字列
        brand_en: ブランド英字名（現状は未使用。将来のあいまい補正用に受け取る）

    Returns:
        正規化後の型番（不明な場合は空文字）
    """
    if not model_number:
        return ""

    # 基本正規化: 全角半角統一・前後空白除去・大文字化
    text = normalize_text(model_number).upper()

    # ハイフン前後の空白を除去（"GA - 100" → "GA-100"）
    text = re.sub(r"\s*-\s*", "-", text)

    if not text:
        return ""

    # (c) 機能語の除去（空白・ハイフン区切りのセグメント単位）
    #     例 "GA-100 QUARTZ" → "GA-100"、"AUTOMATIC-UNI5901" → "UNI5901"
    #     （機能語はハイフンで型番本体と結合しているケースがあるため、
    #       空白トークンをさらにハイフンで分割して判定する）
    cleaned_tokens = []
    for token in text.split():
        parts = [p for p in token.split("-")
                 if p and p not in MODEL_NUMBER_FUNCTION_WORDS]
        if parts:
            cleaned_tokens.append("-".join(parts))
    text = " ".join(cleaned_tokens).strip()

    if not text:
        return ""

    # (d) 隣接ノイズ英字トークンの除去（gemini-3.6-flash 特有の読み取り性質）
    #     裏蓋型番の前後に隣接する短い刻印（メーカーコード等）を型番の一部として
    #     一緒に返すことがある（実例 2924290: GT "469658A-6B" に対し
    #     "IT 469658A-6B PR" と出力。thinking low/medium いずれでも同一値＝
    #     偶発的な誤読ではなく決定論的な読み取り性質）。
    #     仕様書4.2の機能語除去（AUTOMATIC 等）と同系統の後処理として、
    #     数字を含むトークンが1つ以上ある場合に限り、先頭・末尾の
    #     「3文字以下の純英字トークン」を除去する。中間のトークン・数字を含む
    #     トークンは対象外。全トークンが純英字の場合（＝数字を含むトークンが無い）
    #     は型番本体の判別ができないため何もしない。
    #     ※ (a) モジュール番号除去より前に行う必要がある。後段だと例えば
    #        "6119-8030 IT" が「先頭が \d{3,4}- で全体に英字を含む」と誤認され、
    #        正当な型番の "6119-" が誤ってモジュール番号として剥がされてしまう。
    tokens = text.split(" ")
    if len(tokens) > 1 and any(re.search(r"\d", t) for t in tokens):
        while len(tokens) > 1 and re.fullmatch(r"[A-Z]{1,3}", tokens[0]):
            tokens.pop(0)
        while len(tokens) > 1 and re.fullmatch(r"[A-Z]{1,3}", tokens[-1]):
            tokens.pop()
        text = " ".join(tokens)

    # (a) 先頭モジュール番号の除去（例 "5081-GA-100CF" → "GA-100CF"）
    #     ただし数字とハイフンだけの文字列（モジュール番号のみ）は除去しない
    if _MODULE_PREFIX_RE.match(text) and re.search(r"[A-Z]", text):
        text = _MODULE_PREFIX_RE.sub("", text, count=1)

    # (b) 英字を含まない型番の扱い
    #     - ハイフンのない短い数字のみ（≤4桁）→ モジュール/キャリバー番号とみなし空に
    #       （例 CASIO "5196", "1647"）
    #     - ハイフン区切りの数字、または5桁以上の数字は、和製ヴィンテージ等の
    #       正当な数字型番（例 SEIKO "6119-8030", "29014", CITIZEN "4-520190"）
    #       として保持する
    if not re.search(r"[A-Z]", text):
        if re.fullmatch(r"\d{1,4}", text):
            logger.debug(f"型番はモジュール番号のみと判断し除外: {model_number}")
            return ""
        # ハイフン区切り・5桁以上の数字型番は保持

    return text


# === 針数専用パス（過剰検出抑制）用ロジック ===
# 針の本数のランク（少ない方を採用＝過剰検出を抑える）
_HAND_RANK = {"2針": 2, "3針": 3, "クロノグラフ": 4}


def fewest_hand_count(values: list) -> str:
    """複数の針数判定から「最も少ない本数」を採用する（過剰検出抑制）。

    既知ランク(2針 < 3針 < クロノグラフ)の中で最小を返す。既知ランクが
    1つも無い場合は最初の非空値、無ければ空文字を返す。
    """
    known = [v for v in values if v in _HAND_RANK]
    if known:
        return min(known, key=lambda v: _HAND_RANK[v])
    for v in values:
        if v:
            return v
    return ""


def majority_nonempty(values: list) -> str:
    """非空値のうち最頻値を返す（同数なら先に多く現れた値）。全て空なら空文字。

    裏蓋型番のジッター（読めるのに時々空になる）を、複数読みの多数決で回収するのに使う。
    """
    c = Counter(v for v in values if v)
    return c.most_common(1)[0][0] if c else ""


def is_multiword_english_phrase_candidate(series: str) -> bool:
    """シリーズがスローガン混入の「候補」か（純英字が3語以上か）を構造だけで判定する。

    実在シリーズは大半が1〜2語で、スローガン（例: MOST VALUABLE PLAYER）は3語以上の純英字。
    ハイフンや数字を含む語（G-SHOCK, EL-330 等の型番的シリーズ）は候補にしない＝保護する。
    ここで False なら意味判定（API）を呼ばずに保持する（コスト削減＋安全側）。
    """
    if not series:
        return False
    words = series.split()
    if len(words) < 3:
        return False
    return all(re.fullmatch(r"[A-Za-z]+", w) for w in words)


def should_run_hand_count_pass(front_hand_count: str) -> bool:
    """正面解析の針数がデジタル以外（=アナログ）なら専用針数パスを走らせる。

    confidence は判別に使えない（過剰検出が全件 conf=1.0 だった実測）ため、
    アナログは一律で専用パスを通す。デジタル（針なし）のみスキップ。空（不明）は実行する。
    """
    hc = normalize_hand_count(front_hand_count) if front_hand_count else ""
    return hc != "デジタル"


def apply_hand_count_override(merged_data: dict, hand_count_data: dict) -> dict:
    """専用針数パスの結果で merged_data の hand_count を上書きした新しい dict を返す。

    - デジタル（針なし）は上書きしない。
    - hand_count_data が空／針数なしのときは既存値を維持（安全側）。
    - 入力 dict は破壊しない。
    """
    result = dict(merged_data)
    if normalize_hand_count(result.get("hand_count", "")) == "デジタル":
        return result
    new_hc = (hand_count_data or {}).get("hand_count", "")
    # 専用パスが返すのは針数(2針/3針/クロノ)のみを正とする。クロップに部分的なLCD等が
    # 写って「デジタル」や不明値が返っても、アナログの hand_count を誤って上書きしない。
    if new_hc in _HAND_RANK:
        result["hand_count"] = new_hc
    return result


# TODO: マスタにブランド＋型番が存在しない場合の「ごく近い既知型番」へのあいまい補正
#       （difflib等・高類似度かつブランド一致必須）は誤上書きリスクが高いため未実装。
#       現状は「正規化＋完全一致」までに留める。
