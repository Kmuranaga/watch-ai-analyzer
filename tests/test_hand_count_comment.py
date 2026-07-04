"""針数コメント対応（確定仕様）のテスト

仕様:
  1. AI(正面)がクロノグラフ → クロノグラフ（コメント無視）
  2. それ以外はコメント撮影の針数のみ採用（2針/3針/デジタル/針がすべて欠損）
  3. コメントが無ければ空欄 + 処理ステータスに「針数コメント無し」（AIフォールバック無し）

付帯仕様:
  - 「針数判定元」列（針数の直後）: コメント / AI（クロノグラフ） / 空欄
  - 「針がすべて欠損」と空欄はタイトルに載せない
  - ラベル表記は data/hand_count_labels.xlsx で変更可能（無ければ既定値）
  - 12枚目（コメントシール3）まで対応
"""

import csv
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
import modules.ai_analyzer as ai
import modules.hand_count_policy as hcp
from modules.csv_writer import ProductResult, COLUMNS
from modules.folder_scanner import ProductImages, IMAGES_MAX, _scan_product_folder
from modules.hand_count_policy import (
    DEFAULT_LABELS, load_labels, normalize_comment_hand_count,
    labels_for_prompt, decide_hand_count,
)


@pytest.fixture(autouse=True)
def _reset_labels_cache():
    """テスト間でラベルキャッシュが汚染されないようリセットする。"""
    hcp._labels_cache = None
    yield
    hcp._labels_cache = None


# === hand_count_policy: load_labels ===

def test_load_labels_defaults_when_file_missing(tmp_path):
    labels = load_labels(tmp_path / "nonexistent.xlsx")
    assert labels == DEFAULT_LABELS
    # 既定値のコピーであること（呼び出し側の変更が既定値を汚染しない）
    labels["two_hands"]["synonyms"].append("x")
    assert "x" not in DEFAULT_LABELS["two_hands"]["synonyms"]


def _write_labels_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "針数ラベル"
    ws.append(["キー", "出力表記", "同義語（カンマ区切り）"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_load_labels_from_xlsx_custom_rename(tmp_path, monkeypatch):
    """顧客がxlsxでラベル表記を変更 → コード変更なしで出力表記が変わる。"""
    path = tmp_path / "labels.xlsx"
    _write_labels_xlsx(path, [
        ["all_hands_missing", "針が全部無い", "針なし,針欠損"],
    ])
    labels = load_labels(path)
    assert labels["all_hands_missing"]["label"] == "針が全部無い"
    # 出力表記自体も同義語に含まれる
    assert "針が全部無い" in labels["all_hands_missing"]["synonyms"]
    # 不足キーは既定値で補完される
    assert labels["two_hands"]["label"] == "2針"
    assert labels["digital"]["label"] == "デジタル"

    # キャッシュに反映して正規化・決定にも効くこと
    monkeypatch.setattr(hcp, "_labels_cache", labels)
    assert normalize_comment_hand_count("針なし") == "針が全部無い"
    hand_count, source, title_hc = decide_hand_count("", "針なし")
    assert hand_count == "針が全部無い"
    assert source == "コメント"
    assert title_hc == ""  # 欠損ラベルはリネーム後もタイトルに載せない


def test_repo_labels_file_matches_defaults():
    """リポジトリ同梱の data/hand_count_labels.xlsx が既定値と同内容であること。"""
    from config import HAND_COUNT_LABELS_FILE
    assert Path(HAND_COUNT_LABELS_FILE).exists()
    assert load_labels(HAND_COUNT_LABELS_FILE) == DEFAULT_LABELS


# === hand_count_policy: normalize_comment_hand_count ===

def test_normalize_comment_exact_match():
    assert normalize_comment_hand_count("2針") == "2針"
    assert normalize_comment_hand_count("三針") == "3針"
    assert normalize_comment_hand_count("デジタル表示") == "デジタル"
    assert normalize_comment_hand_count("針なし") == "針がすべて欠損"


def test_normalize_comment_fullwidth_and_spaces():
    # normalize_text（NFKC・空白除去）を通ること
    assert normalize_comment_hand_count("　２針 ") == "2針"


def test_normalize_comment_substring_match():
    assert normalize_comment_hand_count("針欠損あり") == "針がすべて欠損"
    assert normalize_comment_hand_count("3針です") == "3針"


def test_normalize_comment_no_match():
    assert normalize_comment_hand_count("") == ""
    assert normalize_comment_hand_count("リューズ固着") == ""


def test_labels_for_prompt_contains_all_labels():
    text = labels_for_prompt()
    for key in DEFAULT_LABELS:
        assert DEFAULT_LABELS[key]["label"] in text


# === hand_count_policy: decide_hand_count ===

def test_decide_chrono_wins_over_comment():
    assert decide_hand_count("クロノグラフ", "2針") == (
        "クロノグラフ", "AI（クロノグラフ）", "クロノグラフ")


def test_decide_comment_used_when_not_chrono():
    assert decide_hand_count("3針", "2針") == ("2針", "コメント", "2針")


def test_decide_blank_when_neither():
    # AI針数（非クロノ）はフォールバックに使わない（空欄=要確認）
    assert decide_hand_count("3針", "") == ("", "", "")
    assert decide_hand_count("", "") == ("", "", "")


def test_decide_all_hands_missing_not_in_title():
    hand_count, source, title_hc = decide_hand_count("2針", "針がすべて欠損")
    assert hand_count == "針がすべて欠損"
    assert source == "コメント"
    assert title_hc == ""


def test_decide_digital_comment():
    assert decide_hand_count("", "デジタル") == ("デジタル", "コメント", "デジタル")


# === folder_scanner: 12枚対応 ===

def test_folder_scanner_supports_12_images(tmp_path, caplog):
    assert IMAGES_MAX == 12
    for i in range(12):
        (tmp_path / f"{i+1:03d}.jpg").write_bytes(b"x")
    with caplog.at_level("WARNING"):
        product = _scan_product_folder(tmp_path, "1234567_TEST")
    assert product.image_count == 12
    assert len(product.comment_images) == 3
    assert product.comment_images[2] == tmp_path / "012.jpg"
    assert "画像枚数超過" not in caplog.text


def test_comment_images_two_images_unchanged():
    imgs = [Path(f"/tmp/img_{i:03d}.jpg") for i in range(11)]
    p = ProductImages("1_t", "1", Path("/tmp"), imgs)
    assert len(p.comment_images) == 2


# === ai_analyzer: analyze_comment ===

def test_analyze_comment_picks_hand_count_from_any_image(monkeypatch):
    monkeypatch.setattr(ai, "_load_comment_prompt", lambda: "PROMPT")
    seq = iter([
        {"title_prefix": "", "abnormality_text": "リューズ固着", "abnormality_type": "リューズ",
         "hand_count_comment": ""},
        {"title_prefix": "", "abnormality_text": "", "abnormality_type": "",
         "hand_count_comment": "2針"},
    ])
    monkeypatch.setattr(ai, "_call_api", lambda prompt, path, extra_images=None: next(seq))
    out = ai.analyze_comment([Path("c1.jpg"), Path("c2.jpg")])
    assert out["hand_count_comment"] == "2針"
    # 異常コメントと針数コメントは共存する（針数カードは異常内容に混入しない）
    assert out["abnormality_text"] == "リューズ固着"


def test_analyze_comment_empty_hand_count(monkeypatch):
    monkeypatch.setattr(ai, "_load_comment_prompt", lambda: "PROMPT")
    monkeypatch.setattr(ai, "_call_api", lambda prompt, path, extra_images=None: {
        "title_prefix": "", "abnormality_text": "", "abnormality_type": "",
        "hand_count_comment": ""})
    out = ai.analyze_comment([Path("c1.jpg"), Path("c2.jpg")])
    assert out["hand_count_comment"] == ""


def test_analyze_comment_no_images_has_key():
    out = ai.analyze_comment([])
    assert out["hand_count_comment"] == ""


def test_load_comment_prompt_injects_labels(monkeypatch):
    monkeypatch.setattr(ai, "_load_prompt", lambda name: "対象: {HAND_COUNT_LABELS} のみ")
    prompt = ai._load_comment_prompt()
    assert "{HAND_COUNT_LABELS}" not in prompt
    assert "針がすべて欠損" in prompt


# === ai_analyzer: parse_batch_results_for_product ===

def test_parse_batch_results_comment3_merged():
    results = {
        "P1__comment1": {"title_prefix": "", "abnormality_text": "ガラス割れ",
                         "abnormality_type": "ガラス", "hand_count_comment": ""},
        "P1__comment3": {"title_prefix": "", "abnormality_text": "",
                         "abnormality_type": "", "hand_count_comment": "3針"},
    }
    _front, _back, comment = ai.parse_batch_results_for_product("P1", results)
    assert comment["hand_count_comment"] == "3針"
    assert comment["abnormality_text"] == "ガラス割れ"


def test_parse_batch_results_hand_count_from_any_index():
    for idx in (1, 2, 3):
        results = {f"P1__comment{idx}": {"hand_count_comment": "デジタル"}}
        _f, _b, comment = ai.parse_batch_results_for_product("P1", results)
        assert comment["hand_count_comment"] == "デジタル", f"comment{idx} で拾えない"


def test_parse_batch_results_no_comments():
    _f, _b, comment = ai.parse_batch_results_for_product("P1", {})
    assert comment["hand_count_comment"] == ""


# === batchモード end-to-end（single と共通の decide_hand_count 経由） ===

def _make_product(tmp_path):
    imgs = [tmp_path / f"{i:02d}.jpg" for i in range(8)]
    for p in imgs:
        p.write_bytes(b"x")
    return ProductImages(
        product_id="9999999_TEST",
        management_number="9999999",
        folder_path=tmp_path,
        images=imgs,
    )


def _run_batch(tmp_path, monkeypatch, front, comment):
    """batchモードで main() を駆動し、出力CSVの行を返す。"""
    product = _make_product(tmp_path)
    back = {"back_brand_en": "", "model_number": "6119-8030"}
    monkeypatch.setattr(main_module, "scan_folder", lambda _d: [product])
    monkeypatch.setattr(main_module, "create_batch_requests", lambda _p: [{"dummy": 1}])
    monkeypatch.setattr(main_module, "submit_batch", lambda _r: "batch_test")
    monkeypatch.setattr(main_module, "poll_batch", lambda _b, poll_interval=60: None)
    monkeypatch.setattr(main_module, "retrieve_batch_results", lambda _b: {})
    monkeypatch.setattr(main_module, "parse_batch_results_for_product",
                        lambda _pid, _r: (dict(front), dict(back), dict(comment)))
    monkeypatch.setattr(main_module, "analyze_back_cover",
                        lambda _img: {"back_brand_en": ""})
    monkeypatch.setattr(main_module, "recover_model_number_upscaled", lambda _img: "")
    monkeypatch.setattr(main_module, "classify_series_is_slogan", lambda _s: False)

    out_csv = tmp_path / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--mode", "batch",
        "--input", str(tmp_path), "--output", str(out_csv),
    ])
    main_module.main()

    with open(out_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    return rows[0]


def test_batch_comment_overrides_ai_hand_count(tmp_path, monkeypatch):
    row = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "hand_count": "3針"},
        comment={"title_prefix": "", "abnormality_text": "", "hand_count_comment": "2針"},
    )
    assert row["針数"] == "2針"
    assert row["針数判定元"] == "コメント"
    assert "3針" not in row["タイトル"]
    assert "2針" in row["タイトル"]


def test_batch_no_comment_blank_hand_count(tmp_path, monkeypatch):
    row = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "hand_count": "3針"},
        comment={"title_prefix": "", "abnormality_text": "", "hand_count_comment": ""},
    )
    assert row["針数"] == ""
    assert row["針数判定元"] == ""
    assert "針数コメント無し" in row["処理ステータス"]
    assert "針" not in row["タイトル"]  # 針数はタイトルに載らない


def test_batch_chrono_wins_over_comment(tmp_path, monkeypatch):
    row = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "hand_count": "クロノグラフ"},
        comment={"title_prefix": "", "abnormality_text": "", "hand_count_comment": "2針"},
    )
    assert row["針数"] == "クロノグラフ"
    assert row["針数判定元"] == "AI（クロノグラフ）"
    assert "クロノグラフ" in row["タイトル"]
    assert "針数コメント無し" not in row["処理ステータス"]


def test_batch_all_hands_missing_not_in_title(tmp_path, monkeypatch):
    row = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "hand_count": "3針"},
        comment={"title_prefix": "", "abnormality_text": "",
                 "hand_count_comment": "針がすべて欠損"},
    )
    assert row["針数"] == "針がすべて欠損"
    assert row["針数判定元"] == "コメント"
    assert "針がすべて欠損" not in row["タイトル"]
    assert "針数コメント無し" not in row["処理ステータス"]


# === csv_writer: 針数判定元 列 ===

def test_columns_has_hand_count_source_after_hand_count():
    assert "針数判定元" in COLUMNS
    assert COLUMNS.index("針数判定元") == COLUMNS.index("針数") + 1


def test_to_row_matches_columns_and_places_source():
    r = ProductResult(hand_count="2針", hand_count_source="コメント")
    row = r.to_row()
    assert len(row) == len(COLUMNS)
    assert row[COLUMNS.index("針数")] == "2針"
    assert row[COLUMNS.index("針数判定元")] == "コメント"
