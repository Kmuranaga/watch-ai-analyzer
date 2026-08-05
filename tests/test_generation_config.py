"""Gemini 3移行: _generation_config() ファクトリと poll_batch タイムアウトのテスト

design doc: Gemini 3系ではtemperatureを送らず(既定1.0維持)、thinking_level/
media_resolutionを指定する。AI_MODELをgemini-2.5-proに戻すだけで旧仕様
(temperatureのみ指定)へ完全復帰できることを保証する（切り戻しテスト）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import modules.ai_analyzer as ai
from modules.ai_analyzer import _generation_config, poll_batch


class TestGenerationConfigGemini3:
    """AI_MODEL が gemini-3系の場合の生成設定"""

    def test_temperature_not_set(self, monkeypatch):
        """Gemini 3系はtemperatureを指定しない（公式推奨の既定1.0を維持）"""
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-3.6-flash")
        config = _generation_config()
        assert config.temperature is None

    def test_thinking_level_set(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-3.6-flash")
        monkeypatch.setattr(ai, "AI_THINKING_LEVEL", "low")
        config = _generation_config()
        assert config.thinking_config is not None
        assert str(config.thinking_config.thinking_level).upper().endswith("LOW")

    def test_media_resolution_set(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-3.6-flash")
        monkeypatch.setattr(ai, "AI_MEDIA_RESOLUTION", "high")
        config = _generation_config()
        assert config.media_resolution is not None
        assert str(config.media_resolution).upper().endswith("HIGH")

    def test_max_output_tokens_preserved(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-3.6-flash")
        monkeypatch.setattr(ai, "AI_MAX_TOKENS", 9999)
        config = _generation_config()
        assert config.max_output_tokens == 9999

    def test_thinking_level_reflects_config_value(self, monkeypatch):
        """AI_THINKING_LEVEL の値の変更が生成設定に反映されること"""
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-3.6-flash")
        monkeypatch.setattr(ai, "AI_THINKING_LEVEL", "medium")
        config = _generation_config()
        assert str(config.thinking_config.thinking_level).upper().endswith("MEDIUM")

    def test_gemini_3_variant_model_names_also_match(self, monkeypatch):
        """gemini-3で始まるモデル名は全てGemini3系分岐に入ること"""
        for name in ("gemini-3.6-flash", "gemini-3-pro", "gemini-3.6-pro-preview"):
            monkeypatch.setattr(ai, "AI_MODEL", name)
            config = _generation_config()
            assert config.temperature is None
            assert config.thinking_config is not None


class TestGenerationConfigGemini25Rollback:
    """AI_MODEL を gemini-2.5-pro に戻した場合の切り戻し保証テスト。

    このテストが通り続ける限り、AI_MODEL環境変数をgemini-2.5-proに戻すだけで
    旧仕様(temperatureのみ指定/thinking・media_resolution未送信)へ完全復帰できる。
    """

    def test_temperature_set_to_ai_temperature(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-2.5-pro")
        monkeypatch.setattr(ai, "AI_TEMPERATURE", 0.0)
        config = _generation_config()
        assert config.temperature == 0.0

    def test_thinking_config_is_none(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-2.5-pro")
        config = _generation_config()
        assert config.thinking_config is None

    def test_media_resolution_is_none(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-2.5-pro")
        config = _generation_config()
        assert config.media_resolution is None

    def test_max_output_tokens_preserved(self, monkeypatch):
        monkeypatch.setattr(ai, "AI_MODEL", "gemini-2.5-pro")
        monkeypatch.setattr(ai, "AI_MAX_TOKENS", 8192)
        config = _generation_config()
        assert config.max_output_tokens == 8192


class TestPollBatchTimeout:
    """poll_batch のタイムアウト（Batchジョブは48時間で失効するため無限待機を避ける）"""

    def test_raises_on_timeout(self, monkeypatch):
        """タイムアウトを超えたら例外を投げ、無限にポーリングし続けないこと"""

        class _FakeState:
            name = "JOB_STATE_RUNNING"

        class _FakeJob:
            state = _FakeState()

        class _FakeBatches:
            def get(self, name):
                return _FakeJob()

        class _FakeClient:
            batches = _FakeBatches()

        monkeypatch.setattr(ai, "_get_client", lambda: _FakeClient())

        # 1回目=開始時刻(0.0), 2回目以降=タイムアウトを超過した時刻(1000.0)
        calls = {"n": 0}

        def fake_monotonic():
            calls["n"] += 1
            return 0.0 if calls["n"] == 1 else 1000.0

        monkeypatch.setattr(ai.time, "monotonic", fake_monotonic)
        monkeypatch.setattr(ai.time, "sleep", lambda s: None)

        with pytest.raises(TimeoutError):
            poll_batch("batches/fake", poll_interval=0, timeout_seconds=1)

    def test_does_not_raise_before_timeout_when_succeeded(self, monkeypatch):
        """タイムアウト前に完了すれば正常終了する（回帰防止）"""

        class _FakeState:
            name = "JOB_STATE_SUCCEEDED"

        class _FakeJob:
            state = _FakeState()

        class _FakeBatches:
            def get(self, name):
                return _FakeJob()

        class _FakeClient:
            batches = _FakeBatches()

        monkeypatch.setattr(ai, "_get_client", lambda: _FakeClient())
        monkeypatch.setattr(ai.time, "sleep", lambda s: None)

        # 例外を投げず正常returnすること
        poll_batch("batches/fake", poll_interval=0, timeout_seconds=60)

    def test_default_timeout_is_24_hours(self):
        """デフォルトのタイムアウトは24時間(60*60*24秒)であること"""
        import inspect
        sig = inspect.signature(poll_batch)
        assert sig.parameters["timeout_seconds"].default == 60 * 60 * 24
