"""裏蓋AI解析対象＝9枚目（2026-10 クライアント合意で8枚目→9枚目に変更）の回帰テスト。

- 裏蓋画像は9枚目（IDX_BACK_COVER=8）を使う。1枚目（正面）は従来どおり。
- 9枚目が無い商品は処理を止めず、正面・コメントの結果は出力し、
  処理ステータスに「裏蓋エラー（9枚目なし）」を出す（single/batch 共通）。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
from config import IDX_BACK_COVER
from modules.folder_scanner import ProductImages, BACK_COVER_MISSING_MSG


def _make_product(tmp_path, n):
    imgs = [tmp_path / f"{i + 1:03d}.jpg" for i in range(n)]
    for p in imgs:
        p.write_bytes(b"x")
    return ProductImages(
        product_id="7777777_TEST",
        management_number="7777777",
        folder_path=tmp_path,
        images=imgs,
    )


FRONT = {"brand_en": "SEIKO", "hand_count": "3針"}
BACK = {"back_brand_en": "", "model_number": "7N43-9080"}
COMMENT = {"title_prefix": "", "abnormality_text": "ベルト切れ", "hand_count_comment": "3針"}


def _patch_common(monkeypatch, product):
    monkeypatch.setattr(main_module, "scan_folder", lambda _d: [product])
    monkeypatch.setattr(main_module, "recover_model_number_upscaled", lambda _img: "")
    monkeypatch.setattr(main_module, "classify_series_is_slogan", lambda _s: False)


def _run(tmp_path, monkeypatch, mode):
    out_csv = tmp_path / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--mode", mode,
        "--input", str(tmp_path), "--output", str(out_csv),
    ])
    main_module.main()
    with open(out_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    return rows[0]


def _run_single(tmp_path, monkeypatch, n_images):
    product = _make_product(tmp_path, n_images)
    _patch_common(monkeypatch, product)
    seen = {}

    def fake_back(img):
        seen["back"] = img
        return dict(BACK)
    monkeypatch.setattr(main_module, "analyze_front", lambda _f, _d: dict(FRONT))
    monkeypatch.setattr(main_module, "analyze_back_cover", fake_back)
    monkeypatch.setattr(main_module, "analyze_comment", lambda _imgs: dict(COMMENT))
    return _run(tmp_path, monkeypatch, "single"), seen


def _run_batch(tmp_path, monkeypatch, n_images):
    product = _make_product(tmp_path, n_images)
    _patch_common(monkeypatch, product)
    has_back = product.back_cover_image is not None
    monkeypatch.setattr(main_module, "create_batch_requests", lambda _p: [{"dummy": 1}])
    monkeypatch.setattr(main_module, "submit_batch", lambda _r: "batch_test")
    monkeypatch.setattr(main_module, "poll_batch", lambda _b, poll_interval=60: None)
    monkeypatch.setattr(main_module, "retrieve_batch_results", lambda _b: {})
    monkeypatch.setattr(
        main_module, "parse_batch_results_for_product",
        lambda _pid, _r: (dict(FRONT), dict(BACK) if has_back else {}, dict(COMMENT)),
    )
    return _run(tmp_path, monkeypatch, "batch")


# === 画像インデックス ===

def test_back_cover_index_is_9th():
    assert IDX_BACK_COVER == 8


def test_back_cover_image_is_9th(tmp_path):
    p = _make_product(tmp_path, 9)
    assert p.back_cover_image == tmp_path / "009.jpg"
    assert p.front_image == tmp_path / "001.jpg"


def test_back_cover_image_none_with_8_images(tmp_path):
    p = _make_product(tmp_path, 8)
    assert p.back_cover_image is None


def test_missing_msg_text():
    assert BACK_COVER_MISSING_MSG == "裏蓋エラー（9枚目なし）"


# === single モード ===

def test_single_uses_9th_image(tmp_path, monkeypatch):
    row, seen = _run_single(tmp_path, monkeypatch, 9)
    assert seen["back"] == tmp_path / "009.jpg"
    assert row["型番"] == "7N43-9080"
    assert BACK_COVER_MISSING_MSG not in row["処理ステータス"]


def test_single_missing_9th_outputs_front(tmp_path, monkeypatch):
    # 8枚のみ＝コメントシール（10枚目〜）も存在しないため、出力されるのは正面の結果
    row, seen = _run_single(tmp_path, monkeypatch, 8)
    assert "back" not in seen  # 裏蓋解析は呼ばれない
    assert row["ブランド英字"] == "SEIKO"
    assert row["型番"] == ""
    assert BACK_COVER_MISSING_MSG in row["処理ステータス"]


# === batch モード ===

def test_batch_with_9th_no_missing_error(tmp_path, monkeypatch):
    row = _run_batch(tmp_path, monkeypatch, 9)
    assert row["型番"] == "7N43-9080"
    assert BACK_COVER_MISSING_MSG not in row["処理ステータス"]


def test_batch_missing_9th_flags_status(tmp_path, monkeypatch):
    """旧実装では batch で裏蓋画像なしがステータスに出なかった（無言で型番空欄）"""
    row = _run_batch(tmp_path, monkeypatch, 8)
    assert row["ブランド英字"] == "SEIKO"
    assert row["型番"] == ""
    assert BACK_COVER_MISSING_MSG in row["処理ステータス"]
    assert "裏蓋AI解析: 結果なし" not in row["処理ステータス"]


# === ファイル名の連番による配置（撮影漏れで 09 が欠けたケース） ===

from modules.folder_scanner import scan_folder, build_numbered_slots


def _make_folder(tmp_path, names, folder="3099530_時計"):
    d = tmp_path / "input" / folder
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(b"x")
    return tmp_path / "input"


def _numbered(mn, nums, suffix=""):
    return [f"{mn}_{n:02d}{suffix}.jpg" for n in nums]


def test_missing_09_with_comments_detected(tmp_path):
    """実データ 3099530: 01〜08, 10〜12（09 欠番）→ 裏蓋なし・コメントは10枚目以降のまま"""
    root = _make_folder(tmp_path, _numbered("3099530", [*range(1, 9), 10, 11, 12]))
    [p] = scan_folder(root)
    assert p.back_cover_image is None
    assert [c.name for c in p.comment_images] == [
        "3099530_10.jpg", "3099530_11.jpg", "3099530_12.jpg",
    ]
    assert p.has_comments
    assert p.front_image.name == "3099530_01.jpg"


def test_numbered_with_trailing_hyphen(tmp_path):
    """実データ 3093691: 8枚目が「_08-.jpg」でも番号どおりに配置"""
    names = _numbered("3093691", range(1, 12))
    names[7] = "3093691_08-.jpg"
    root = _make_folder(tmp_path, names, folder="3093691_時計")
    [p] = scan_folder(root)
    assert p.image_at(7).name == "3093691_08-.jpg"
    assert p.back_cover_image.name == "3093691_09.jpg"
    assert [c.name for c in p.comment_images] == ["3093691_10.jpg", "3093691_11.jpg"]


def test_complete_numbered_same_as_order(tmp_path):
    root = _make_folder(tmp_path, _numbered("3099407", range(1, 13)))
    [p] = scan_folder(root)
    assert p.back_cover_image.name == "3099407_09.jpg"
    assert len(p.comment_images) == 3


def test_three_digit_names_numbered(tmp_path):
    root = _make_folder(tmp_path, [f"{n:03d}.jpg" for n in [*range(1, 9), 10]])
    [p] = scan_folder(root)
    assert p.back_cover_image is None
    assert [c.name for c in p.comment_images] == ["010.jpg"]


def test_unnumbered_falls_back_to_order(tmp_path):
    """カメラ連番（4桁）等は従来どおり並び順で判定"""
    root = _make_folder(tmp_path, [f"DSC_{n:04d}.jpg" for n in range(101, 111)])
    [p] = scan_folder(root)
    assert p.slots is None
    assert p.back_cover_image.name == "DSC_0109.jpg"
    assert [c.name for c in p.comment_images] == ["DSC_0110.jpg"]


def test_build_slots_rejects_duplicates_and_out_of_range():
    assert build_numbered_slots([Path("a_01.jpg"), Path("b_01.jpg")]) is None
    assert build_numbered_slots([Path("a_01.jpg"), Path("a_15.jpg")]) is None
    assert build_numbered_slots([Path("a_00.jpg")]) is None
    assert build_numbered_slots([Path("front.jpg")]) is None


def test_single_missing_09_with_comments_end_to_end(tmp_path, monkeypatch):
    """09 欠番＋コメントあり: 裏蓋エラーを出し、コメント（針数含む）は出力される"""
    root = _make_folder(tmp_path, _numbered("3099530", [*range(1, 9), 10, 11, 12]))
    seen = {}

    def fake_back(img):
        seen["back"] = img
        return dict(BACK)

    def fake_comment(imgs):
        seen["comment"] = [i.name for i in imgs]
        return dict(COMMENT)
    monkeypatch.setattr(main_module, "recover_model_number_upscaled", lambda _img: "")
    monkeypatch.setattr(main_module, "classify_series_is_slogan", lambda _s: False)
    monkeypatch.setattr(main_module, "analyze_front", lambda _f, _d: dict(FRONT))
    monkeypatch.setattr(main_module, "analyze_back_cover", fake_back)
    monkeypatch.setattr(main_module, "analyze_comment", fake_comment)

    out_csv = tmp_path / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "main.py", "--mode", "single", "--input", str(root), "--output", str(out_csv),
    ])
    main_module.main()
    with open(out_csv, encoding="utf-8-sig") as f:
        [row] = list(csv.DictReader(f))

    assert "back" not in seen  # コメントシールを裏蓋として解析しない
    assert seen["comment"] == ["3099530_10.jpg", "3099530_11.jpg", "3099530_12.jpg"]
    assert row["異常内容"] == "ベルト切れ"
    assert row["針数"] == "3針"
    assert BACK_COVER_MISSING_MSG in row["処理ステータス"]
