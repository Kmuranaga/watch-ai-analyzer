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

    # 正面ブランドと裏蓋刻印ブランドの整合
    # （文字盤=製品ブランド優先、裏蓋=補完/整合。判定詳細は reconcile_brand を参照）
    _reconcile_brand_fields(result)

    # ブランド名正規化
    if result.get("brand_en"):
        result["brand_en"] = normalize_brand(result["brand_en"])

    # シリーズ名正規化（大文字化＋SEIKO略称の展開。展開はブランド整合後の brand_en を使う）
    if result.get("series_en"):
        result["series_en"] = normalize_series(result["series_en"], result.get("brand_en", ""))

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
}


def normalize_series(series: str, brand: str = "") -> str:
    """シリーズ名を正規化（大文字化＋SEIKO略称の展開）。

    SEIKO の標準的なシリーズ略称（LM/KS/GS）のみ正式名へ展開する。
    他ブランドで同綴りが別義になる誤展開を避けるため、ブランド=SEIKO に限定する。
    """
    s = normalize_text(series).upper()
    if normalize_brand(brand) == "SEIKO":
        return SEIKO_SERIES_ALIAS.get(s, s)
    return s


# === ムーブメント製造元名（製品ブランドではない）===
# 裏蓋にはこれらの製造元名が刻印されることがあるが、製品ブランドとは限らない。
# （正規化後の大文字表記で照合する）
MOVEMENT_MAKERS = {
    "CITIZEN", "MIYOTA", "SEIKO", "SII", "TMI", "HATTORI",
    "ORIENT", "EPSON", "RONDA", "ETA", "ISA", "JAPAN",
    "STP",  # Swiss Technology Production（ETA系の汎用ムーブメント製造元）
}


def reconcile_brand(front_brand: str, back_brand: str, front_conf=None):
    """
    正面（文字盤）ブランドと裏蓋刻印ブランドを整合し、採用ブランドと採用元を返す。

    判定順（裏蓋刻印ブランドを整合の基準にする）:
      1. fb,bb がともにあり fb≠bb で bb が製造元（MOVEMENT_MAKERS）
         → fb（裏蓋は製造元名であって製品ブランドではない。例: RONSON/CITIZEN製造、SEIKO/STP）
      2. fb,bb がともにあり fb≠bb で bb が製造元でない実ブランド
         → bb（裏蓋の実ブランド刻印を採用。正面は高確信でも誤読しうる。例: ELGINがTAG HEUERと誤読）
      3. fb がある → fb（裏蓋が空 or fb==bb）
      4. fb が空で bb がある → bb（表が判読不可→裏蓋で補完）
      5. どちらも空 → ""

    Args:
        front_brand: 正面ブランド（生文字列可）
        back_brand: 裏蓋刻印ブランド（生文字列可）
        front_conf: 正面ブランドの confidence。現ロジックでは判定に使用しないが、
                    後方互換のため引数は受け付ける（製造元ガードで誤採用を防ぐ方式に変更）。

    Returns:
        (brand, source): brand は正規化済みブランド、
                         source は "front" / "back" / ""
    """
    fb = normalize_brand(front_brand) if front_brand else ""
    bb = normalize_brand(back_brand) if back_brand else ""

    if fb and bb and fb != bb:
        # 1. 裏蓋が製造元名 → 文字盤を採用（RONSON/CITIZEN, SEIKO/STP 等）
        if bb in MOVEMENT_MAKERS:
            return fb, "front"
        # 2. 裏蓋が製造元でない実ブランド → 裏蓋を採用
        #    （正面は高確信でも誤読しうるため、製造元でない刻印ブランドを優先）
        return bb, "back"

    # 3. 文字盤優先（裏蓋が空、または fb==bb のケース）
    if fb:
        return fb, "front"

    # 4. 表が判読不可 → 裏蓋で補完
    if bb:
        return bb, "back"

    # 5. どちらも空
    return "", ""


def stabilize_back_brand_override(front_brand: str, back_brand: str,
                                  resample_fn, k: int = 3) -> bool:
    """裏蓋ブランドで正面を上書きしてよいか（裏蓋が安定しているか）を判定する。

    背景: reconcile_brand は「正面≠裏蓋 かつ 裏蓋が非製造元ブランド」のとき裏蓋を採用する
    （例: ELGINがTAG HEUERと誤読される正面を裏蓋ELGINで是正）。しかしこのルールは、
    安定して正しい正面を、裏蓋の一回ノイズ読み（例: 2924323で稀に出る ISSEY MIYAKE）で
    誤って上書きしうる。confidence は信頼できない（空欄でも0.8〜0.95）ため、裏蓋を
    再サンプルして安定性で判定する。

    上書きが起きうるケース（正面・裏蓋ともにあり、異なり、裏蓋が非製造元）のときだけ
    resample_fn を k 回呼んで裏蓋ブランドを取り直し、元の1回と合わせて同一ブランドが
    過半数なら True（安定＝上書き採用）、そうでなければ False（ノイズ＝正面を維持）。
    上書きが起きないケースでは resample_fn を呼ばず True を返す（追加コストなし）。

    Args:
        front_brand: 正面ブランド（生文字列可）
        back_brand: 裏蓋ブランド（生文字列可）
        resample_fn: 引数なしで裏蓋ブランド文字列を返す関数（追加サンプル取得用）
        k: 追加サンプル数

    Returns:
        True なら裏蓋採用を信頼してよい、False なら裏蓋はノイズとして正面を維持すべき。
    """
    fb = normalize_brand(front_brand) if front_brand else ""
    bb = normalize_brand(back_brand) if back_brand else ""

    # 上書きが起きうるケースでなければ再サンプルせず信頼（コストなし）
    if not (fb and bb and fb != bb and bb not in MOVEMENT_MAKERS):
        return True

    samples = [bb] + [normalize_brand(resample_fn() or "") for _ in range(k)]
    same = sum(1 for s in samples if s == bb)
    return same * 2 > len(samples)  # 厳密な過半数


def _reconcile_brand_fields(result: dict) -> None:
    """
    normalize_all 内でブランド/シリーズの整合を行い、result を直接更新する。

    - reconcile_brand で最終ブランドと採用元を決定し brand_en に設定。
    - シリーズ・かなは採用元に合わせて front/back を採用（採用元が空なら他方で補完）。
    - 裏蓋用の一時キー（back_*）は出力に残さないよう pop する。
    """
    front_brand = result.get("brand_en", "")
    back_brand = result.get("back_brand_en", "")
    front_conf = (result.get("confidence") or {}).get("brand")

    final_brand, source = reconcile_brand(front_brand, back_brand, front_conf)
    result["brand_en"] = final_brand

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
                "back_series_en", "back_series_kana", "back_confidence"):
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
