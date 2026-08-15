"""config.APP_VERSION（配布パッケージのバージョン識別）のテスト"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config


class TestAppVersion:
    """VERSION ファイルの有無で APP_VERSION が切り替わることを確認"""

    def test_dev_when_no_version_file(self):
        """開発環境（VERSIONファイルなし）では \"dev\""""
        assert not config.VERSION_FILE.exists()
        assert config.APP_VERSION == "dev"

    def test_reads_version_file_when_present(self):
        """VERSIONファイルがあれば中身をそのまま読む（scripts/make_package.sh が生成する想定）"""
        version_file = config.VERSION_FILE
        version_file.write_text("main @ abc1234 (2026-08-15)\n", encoding="utf-8")
        try:
            importlib.reload(config)
            assert config.APP_VERSION == "main @ abc1234 (2026-08-15)"
        finally:
            version_file.unlink()
            importlib.reload(config)
