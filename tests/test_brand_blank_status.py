"""ブランド判読不可時に人手確認の目印を立てる append_brand_review_status のテスト。

文字盤に文字が無く裏蓋補完も成立しなかったケースは brand_en=="" のまま
汎用カテゴリ等に流れてしまい、通常のエラー（カテゴリ未確定 等）が出ないことがある。
処理ステータスに明示的な警告を残すためのヘルパーの単体テストと、
パイプライン（main.py batch モード）への統合テスト。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
from main import append_brand_review_status
from modules.csv_writer import ProductResult
from modules.folder_scanner import ProductImages


class TestAppendBrandReviewStatus:
    """append_brand_review_status 単体テスト"""

    def test_blank_brand_adds_error(self):
        result = ProductResult()
        result.brand_en = ""
        errors = []
        append_brand_review_status(result, errors)
        assert "ブランド判読不可" in errors

    def test_nonblank_brand_does_not_add_error(self):
        result = ProductResult()
        result.brand_en = "SEIKO"
        errors = []
        append_brand_review_status(result, errors)
        assert "ブランド判読不可" not in errors


class TestBrandBlankStatusPipeline:
    """batch モードで process_batch のステータスに反映されることの統合テスト
    （tests/test_batch_body_color.py の手法を流用）
    """

    def _make_product(self, tmp_path):
        imgs = [tmp_path / f"{i:02d}.jpg" for i in range(8)]
        for p in imgs:
            p.write_bytes(b"x")
        return ProductImages(
            product_id="8888888_TEST",
            management_number="8888888",
            folder_path=tmp_path,
            images=imgs,
        )

    def _run_batch(self, tmp_path, monkeypatch, front):
        product = self._make_product(tmp_path)
        back = {"model_number": "", "material": ""}
        comment = {"title_prefix": "", "abnormality_text": ""}

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
        return rows[0]

    def test_blank_brand_batch_status_flags_review(self, tmp_path, monkeypatch):
        """front brand_en=""（汎用カテゴリに落ちる条件）でも処理ステータスに
        「ブランド判読不可」が含まれること"""
        front = {
            "brand_en": "",
            "gender": "レディース",
            "movement_type": "Quartz",
            "body_color": "シルバー",
            "dial_color": "ブラック",
            "hand_count": "",
            "case_shape": "ラウンド",
        }
        row = self._run_batch(tmp_path, monkeypatch, front)
        assert "ブランド判読不可" in row["処理ステータス"]

    def test_known_brand_batch_status_no_review_flag(self, tmp_path, monkeypatch):
        """front brand_en="SEIKO" では「ブランド判読不可」は含まれないこと"""
        front = {
            "brand_en": "SEIKO",
            "gender": "レディース",
            "movement_type": "Quartz",
            "body_color": "シルバー",
            "dial_color": "ブラック",
            "hand_count": "",
            "case_shape": "ラウンド",
        }
        row = self._run_batch(tmp_path, monkeypatch, front)
        assert "ブランド判読不可" not in row["処理ステータス"]
