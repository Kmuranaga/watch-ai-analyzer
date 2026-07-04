"""針数コメントのラベル設定と針数決定ポリシー

確定仕様:
  1. AI(正面)がクロノグラフ → クロノグラフ（コメント無視）
  2. それ以外はコメント撮影の針数のみ採用（2針/3針/デジタル/針がすべて欠損）
  3. コメントが無ければ空欄（AIフォールバックはしない。空欄=要確認）

ラベル表記は data/hand_count_labels.xlsx で変更可能（無ければ既定値）。
"""

import logging
from pathlib import Path

import openpyxl

from config import HAND_COUNT_LABELS_FILE
from modules.normalizer import normalize_text, normalize_hand_count

logger = logging.getLogger(__name__)

# 既定ラベル（設定ファイルが無い場合に使用）
DEFAULT_LABELS = {
    "two_hands": {"label": "2針", "synonyms": ["2針", "二針", "2本針", "2本"]},
    "three_hands": {"label": "3針", "synonyms": ["3針", "三針", "3本針", "3本"]},
    "digital": {"label": "デジタル", "synonyms": ["デジタル", "デジタル表示"]},
    "all_hands_missing": {"label": "針がすべて欠損",
                          "synonyms": ["針がすべて欠損", "針欠損", "針なし", "針無し", "全針欠損"]},
}

_labels_cache: dict | None = None


def load_labels(path: Path | None = None) -> dict:
    """設定ファイルからラベル定義を読み込む。無ければ既定値を返す。

    xlsx形式（1行目ヘッダー）: キー | 出力表記 | 同義語（カンマ区切り）
    """
    file = path or HAND_COUNT_LABELS_FILE
    if not Path(file).exists():
        logger.info(f"針数ラベル設定ファイルなし。既定値を使用: {file}")
        return {k: {"label": v["label"], "synonyms": list(v["synonyms"])}
                for k, v in DEFAULT_LABELS.items()}
    labels = {}
    wb = openpyxl.load_workbook(file, read_only=True)
    ws = wb.active
    header = True
    for row in ws.iter_rows(values_only=True):
        if header:
            header = False
            continue
        if not row or not row[0]:
            continue
        key = str(row[0]).strip()
        label = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        syn_raw = str(row[2]).strip() if len(row) > 2 and row[2] else ""
        synonyms = [s.strip() for s in syn_raw.split(",") if s.strip()]
        if key and label:
            if label not in synonyms:
                synonyms.insert(0, label)
            labels[key] = {"label": label, "synonyms": synonyms}
    wb.close()
    # 不足キーは既定値で補完（設定ミスで機能が壊れないように）
    for k, v in DEFAULT_LABELS.items():
        labels.setdefault(k, {"label": v["label"], "synonyms": list(v["synonyms"])})
    logger.info(f"針数ラベル設定読込完了: {len(labels)}種")
    return labels


def get_labels(reload: bool = False) -> dict:
    """ラベル定義を返す（プロセス内キャッシュ）。"""
    global _labels_cache
    if _labels_cache is None or reload:
        _labels_cache = load_labels()
    return _labels_cache


def normalize_comment_hand_count(text: str) -> str:
    """コメント撮影から読み取った針数表記を正規のラベルに変換する。該当なしは空文字。"""
    if not text:
        return ""
    cleaned = normalize_text(text)
    labels = get_labels()
    # まず完全一致、次に部分一致（誤爆しにくい順に）
    for key in ("all_hands_missing", "digital", "three_hands", "two_hands"):
        entry = labels.get(key, {})
        for syn in entry.get("synonyms", []):
            if cleaned == syn:
                return entry["label"]
    for key in ("all_hands_missing", "digital", "three_hands", "two_hands"):
        entry = labels.get(key, {})
        for syn in entry.get("synonyms", []):
            if syn and syn in cleaned:
                return entry["label"]
    return ""


def labels_for_prompt() -> str:
    """コメント解析プロンプトへ注入する、認識対象ラベルの説明文字列。"""
    labels = get_labels()
    parts = []
    for key in ("two_hands", "three_hands", "digital", "all_hands_missing"):
        entry = labels.get(key, {})
        syns = "、".join(entry.get("synonyms", []))
        parts.append(f"「{entry.get('label', '')}」（同義表記: {syns}）")
    return "／".join(parts)


def decide_hand_count(front_hand_count: str, comment_hand_count: str) -> tuple[str, str, str]:
    """針数の最終決定（確定仕様）。

    Returns:
        (hand_count, source, title_hand_count)
        hand_count: 針数列に出力する値（決められなければ空文字）
        source: 「針数判定元」列の値（"AI（クロノグラフ）" / "コメント" / ""）
        title_hand_count: タイトルに載せる値（「針がすべて欠損」と空欄は載せない）
    """
    if normalize_hand_count(front_hand_count or "") == "クロノグラフ":
        return "クロノグラフ", "AI（クロノグラフ）", "クロノグラフ"
    label = normalize_comment_hand_count(comment_hand_count or "")
    if label:
        missing_label = get_labels()["all_hands_missing"]["label"]
        title_value = "" if label == missing_label else label
        return label, "コメント", title_value
    return "", "", ""
