"""Batchモードでも条件付きフォローアップ3機能が適用されることの回帰テスト。

対象: 裏蓋ブランド安定化 / 型番リカバリ / シリーズ・スローガン除外。
これらは従来 single モード限定だった（結果を見てからの条件付き追い読みが
batch の一括送信ではできないため）。ハイブリッド方式（batch 結果の後処理で
通常APIの追い読み）により batch でも有効になったことを検証する。
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
               resample_brand="", recovered_model="", slogan=False, choice="back"):
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

    calls = {"resample": 0, "recover": 0, "slogan": 0, "choice": 0}

    def fake_choice(_img, _fb, _bb):
        calls["choice"] += 1
        return choice
    monkeypatch.setattr(main_module, "verify_back_brand_choice", fake_choice)

    def fake_back(_img):
        calls["resample"] += 1
        return {"back_brand_en": resample_brand}
    monkeypatch.setattr(main_module, "analyze_back_cover", fake_back)

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


def test_unstable_back_brand_rejected_in_batch(tmp_path, monkeypatch):
    # 正面SWATCH(安定・正) vs 裏蓋ISSEY MIYAKE(ノイズ)。再サンプルが全て空 → 裏蓋不採用
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "SWATCH", "hand_count": "3針"},
        back={"back_brand_en": "ISSEY MIYAKE", "model_number": "YT57-0AJ0"},
        resample_brand="",
    )
    assert row["ブランド英字"] == "SWATCH"
    assert calls["resample"] == 3  # k=3 の再サンプルが走った


def test_stable_back_brand_adopted_in_batch(tmp_path, monkeypatch):
    # ELGIN型: 正面誤読(TAG HEUER) vs 裏蓋ELGINが安定 → 裏蓋採用（非回帰）
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "TAG HEUER", "hand_count": "3針"},
        back={"back_brand_en": "ELGIN", "model_number": ""},
        resample_brand="ELGIN",
        recovered_model="",
    )
    assert row["ブランド英字"] == "ELGIN"


def test_hallucinated_back_brand_rejected_in_batch(tmp_path, monkeypatch):
    # BINLUN型: 正面BINLUN(正・conf1.0) vs 裏蓋KENTEX(一貫した幻覚読み)。
    # 再サンプル多数決は「一貫した」幻覚を通してしまうが、二択照合が
    # 「裏蓋に実際に刻印されているのは正面(BINLUN)」と答える → 裏蓋不採用。
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "BINLUN", "hand_count": "3針"},
        back={"back_brand_en": "KENTEX", "model_number": "BL0067G"},
        choice="front",
    )
    assert row["ブランド英字"] == "BINLUN"
    assert calls["choice"] == 1
    assert calls["resample"] == 0  # 二択照合で不採用が確定 → 再サンプルは走らない


def test_choice_back_still_allows_override(tmp_path, monkeypatch):
    # ELGIN型（非回帰）: 二択照合が「裏蓋刻印は裏蓋ブランド(ELGIN)」と答え、
    # 再サンプルも安定 → 従来どおり裏蓋採用で正面誤読を是正。
    row, calls = _run_batch(
        tmp_path, monkeypatch,
        front={"brand_en": "TAG HEUER", "hand_count": "3針"},
        back={"back_brand_en": "ELGIN", "model_number": ""},
        resample_brand="ELGIN",
        choice="back",
    )
    assert row["ブランド英字"] == "ELGIN"
    assert calls["choice"] == 1
    assert calls["resample"] == 3


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
