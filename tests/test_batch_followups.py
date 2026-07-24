"""Batchモードでのブランド整合・条件付きフォローアップの回帰テスト。

対象: ブランドの文字盤最優先整合 / 型番リカバリ / シリーズ・スローガン除外。
仕様変更（2026-07-24 クライアント合意）により、裏蓋ブランドによる正面の上書きと
その安定化ガード（二択照合・再サンプル）は廃止。文字盤が読めていれば常に文字盤を
採用し、文字盤が空の場合のみ mapping.xlsx 登録ブランドの裏蓋刻印で補完する。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
from modules.folder_scanner import ProductImages


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


def _run_batch(tmp_path, monkeypatch, front, back,
               recovered_model="", slogan=False):
    """batchモードで main() を駆動し、(出力行, フォローアップ呼び出し回数) を返す。"""
    product = _make_product(tmp_path)
    comment = {"title_prefix": "", "abnormality_text": ""}
    monkeypatch.setattr(main_module, "scan_folder", lambda _d: [product])
    monkeypatch.setattr(main_module, "create_batch_requests", lambda _p: [{"dummy": 1}])
    monkeypatch.setattr(main_module, "submit_batch", lambda _r: "batch_test")
    monkeypatch.setattr(main_module, "poll_batch", lambda _b, poll_interval=60: None)
    monkeypatch.setattr(main_module, "retrieve_batch_results", lambda _b: {})
    monkeypatch.setattr(main_module, "parse_batch_results_for_product",
                        lambda _pid, _r: (dict(front), dict(back), dict(comment)))

    calls = {"recover": 0, "slogan": 0}

    def fake_recover(_img):
        calls["recover"] += 1
        return recovered_model
    monkeypatch.setattr(main_module, "recover_model_number_upscaled", fake_recover)

    def fake_slogan(_s):
        calls["slogan"] += 1
        return slogan
    monkeypatch.setattr(main_module, "classify_series_is_slogan", fake_slogan)

    out_csv = tmp_path / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--mode", "batch",
        "--input", str(tmp_path), "--output", str(out_csv),
    ])
    main_module.main()

    with open(out_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    return rows[0], calls


def test_dial_first_front_kept_in_batch(tmp_path, monkeypatch):
    # 文字盤最優先: 正面TAG HEUER vs 裏蓋ELGIN（既知ブランド刻印）でも正面を採用。
    # 旧仕様の裏蓋是正（ELGIN採用）は仕様変更により廃止。追い読みAPIは存在しない。
    row, _calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "TAG HEUER", "hand_count": "3針"},
        back={"back_brand_en": "ELGIN", "model_number": "6119-8030"},
    )
    assert row["ブランド英字"] == "TAG HEUER"


def test_dial_first_case_maker_back_in_batch(tmp_path, monkeypatch):
    # □STAR型（実データ2959969）: 正面CITIZEN vs 裏蓋STAR → 正面を採用。
    row, _calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "CITIZEN", "hand_count": "3針"},
        back={"back_brand_en": "STAR", "model_number": "SENS51801A-Y"},
    )
    assert row["ブランド英字"] == "CITIZEN"


def test_back_fill_known_brand_when_front_empty_in_batch(tmp_path, monkeypatch):
    # 正面判読不可 + 裏蓋ELGIN（mapping.xlsx 登録ブランド）→ 裏蓋で補完。
    row, _calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "", "hand_count": "3針"},
        back={"back_brand_en": "ELGIN", "model_number": ""},
    )
    assert row["ブランド英字"] == "ELGIN"


def test_back_unknown_text_not_adopted_when_front_empty_in_batch(tmp_path, monkeypatch):
    # 正面判読不可 + 裏蓋ELMITEX（ベルトメーカー刻印・mapping未登録）→ 空欄のまま。
    row, _calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "", "hand_count": "3針"},
        back={"back_brand_en": "ELMITEX", "model_number": ""},
    )
    assert row["ブランド英字"] == ""


def test_model_recovery_fires_when_empty_in_batch(tmp_path, monkeypatch):
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "hand_count": "2針"},
        back={"back_brand_en": "", "model_number": ""},
        recovered_model="283110",
    )
    assert row["型番"] == "283110"
    assert calls["recover"] == 1


def test_model_recovery_skipped_when_present_in_batch(tmp_path, monkeypatch):
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "hand_count": "2針"},
        back={"back_brand_en": "", "model_number": "6119-8030"},
        recovered_model="999999",
    )
    assert row["型番"] == "6119-8030"
    assert calls["recover"] == 0  # 読めている商品には追いコストなし


def test_slogan_filter_applies_in_batch(tmp_path, monkeypatch):
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "ELGIN", "series_en": "MOST VALUABLE PLAYER", "hand_count": "3針"},
        back={"back_brand_en": "", "model_number": ""},
        slogan=True,
    )
    assert row["シリーズ英字"] == ""
    assert calls["slogan"] == 1


def test_slogan_filter_not_called_for_short_series_in_batch(tmp_path, monkeypatch):
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SEIKO", "series_en": "LORD MATIC", "hand_count": "3針"},
        back={"back_brand_en": "", "model_number": ""},
        slogan=True,
    )
    assert row["シリーズ英字"] == "LORD MATIC"
    assert calls["slogan"] == 0  # 構造ゲートで候補外 → APIを呼ばない
