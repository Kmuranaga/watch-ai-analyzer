"""素材のめっき併記リカバリ（apply_material_plating_recovery）のテスト。

実例 3000639/3000659/3000758: 複合刻印（10K R.G.P. 等）の商品で、裏蓋解析が
めっき側を落として品位のみ（10K）を返す揺れがあるため、品位のみの時だけ
焦点確認でめっき併記を回収する。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main as main_module
from modules.csv_writer import ProductResult


class _FakeProduct:
    product_id = "9999999_TEST"
    back_cover_image = Path("dummy_back.jpg")


class _NoBackProduct:
    product_id = "9999999_TEST"
    back_cover_image = None


def _patch(monkeypatch, plating, calls=None):
    def fake(path, karat):
        if calls is not None:
            calls.append(karat)
        return plating
    monkeypatch.setattr(main_module, "recheck_material_plating", fake)


def test_gf_recovers_to_compound(monkeypatch):
    _patch(monkeypatch, "GF")
    r = ProductResult(material="10K")
    main_module.apply_material_plating_recovery(_FakeProduct(), r)
    assert r.material == "10K金張り"


def test_rgp_recovers_to_compound(monkeypatch):
    _patch(monkeypatch, "RGP")
    r = ProductResult(material="14K")
    main_module.apply_material_plating_recovery(_FakeProduct(), r)
    assert r.material == "14K RGP"


def test_electroplated_keeps_karat_only(monkeypatch):
    """クライアント指定（3000915）: ELECTROPLATED は品位のみを維持"""
    _patch(monkeypatch, "ELECTROPLATED")
    r = ProductResult(material="18K")
    main_module.apply_material_plating_recovery(_FakeProduct(), r)
    assert r.material == "18K"


def test_no_plating_keeps_karat(monkeypatch):
    _patch(monkeypatch, "")
    r = ProductResult(material="14K")
    main_module.apply_material_plating_recovery(_FakeProduct(), r)
    assert r.material == "14K"


def test_compound_material_does_not_fire(monkeypatch):
    calls = []
    _patch(monkeypatch, "GF", calls)
    r = ProductResult(material="14K金張り")
    main_module.apply_material_plating_recovery(_FakeProduct(), r)
    assert r.material == "14K金張り"
    assert calls == []


def test_non_karat_material_does_not_fire(monkeypatch):
    calls = []
    _patch(monkeypatch, "GF", calls)
    for m in ("ステンレス", "GP", ""):
        r = ProductResult(material=m)
        main_module.apply_material_plating_recovery(_FakeProduct(), r)
        assert r.material == m
    assert calls == []


def test_no_back_image_does_not_fire(monkeypatch):
    calls = []
    _patch(monkeypatch, "GF", calls)
    r = ProductResult(material="10K")
    main_module.apply_material_plating_recovery(_NoBackProduct(), r)
    assert r.material == "10K"
    assert calls == []
