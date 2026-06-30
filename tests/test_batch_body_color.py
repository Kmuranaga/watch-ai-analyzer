"""Batch APIモードで本体色(body_color)が出力に伝播することを保証する回帰テスト。

不具合: main.py の Batch 処理パスは body_color を ProductResult に設定しておらず、
        generate_title にも渡していなかったため、--mode batch では「本体色」列が常に空に
        なり、タイトルからも本体色が抜け落ちていた（single モードでは正常）。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
from modules.folder_scanner import ProductImages


def test_batch_mode_populates_body_color(tmp_path, monkeypatch):
    # --- ダミー商品（裏蓋判定のため画像8枚以上） ---
    imgs = [tmp_path / f"{i:02d}.jpg" for i in range(8)]
    for p in imgs:
        p.write_bytes(b"x")
    product = ProductImages(
        product_id="9999999_TEST",
        management_number="9999999",
        folder_path=tmp_path,
        images=imgs,
    )

    # AI解析結果（正面で body_color と dial_color を別々に返す想定）
    front = {"brand_en": "SEIKO", "body_color": "ホワイト", "dial_color": "ブラック",
             "hand_count": "3針", "case_shape": "ラウンド", "gender": "メンズ"}
    back = {"model_number": "SARX055", "material": "ステンレス"}
    comment = {"title_prefix": "", "abnormality_text": ""}

    # Batchパイプラインを全てモック（実APIは呼ばない）
    monkeypatch.setattr(main_module, "scan_folder", lambda _d: [product])
    monkeypatch.setattr(main_module, "create_batch_requests", lambda _p: [{"dummy": 1}])
    monkeypatch.setattr(main_module, "submit_batch", lambda _r: "batch_test")
    monkeypatch.setattr(main_module, "poll_batch", lambda _b, poll_interval=60: None)
    monkeypatch.setattr(main_module, "retrieve_batch_results", lambda _b: {})
    monkeypatch.setattr(
        main_module, "parse_batch_results_for_product",
        lambda _pid, _results: (front, back, comment),
    )

    out_csv = tmp_path / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--mode", "batch",
        "--input", str(tmp_path), "--output", str(out_csv),
    ])

    main_module.main()

    with open(out_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    row = rows[0]
    # 本体色が空でなく、文字盤色とは別に出力されていること
    assert row["本体色"] == "ホワイト", f"本体色が空/誤り: {row['本体色']!r}"
    assert row["文字盤色"] == "ブラック"
    # タイトルにも本体色が含まれること
    assert "ホワイト" in row["タイトル"], f"タイトルに本体色が無い: {row['タイトル']!r}"
