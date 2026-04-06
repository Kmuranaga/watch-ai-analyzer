# Watch AI Analyzer - Claude Code ガイド

## テスト

- テストフレームワーク: pytest
- テストディレクトリ: `tests/`
- テスト実行: `source .venv/bin/activate && python -m pytest tests/ -v`

### ルール

- **コードを変更したら、必ずテストを実行してからタスク完了とすること**
- テスト対象モジュールを変更した場合は、関連テストが全てパスすることを確認する
- 新しいロジックを追加した場合は、対応するテストも追加する

## プロジェクト構成

- `modules/` - コアロジック（AI解析、正規化、カテゴリマッピング等）
- `app.py` - Flask Web UI
- `main.py` - CLI エントリポイント
- `config.py` - 設定
- `data/mapping.xlsx` - ブランド別・汎用カテゴリマッピング
