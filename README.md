# 腕時計AI自動解析システム テスト版 (v0.1)

Watch AI Auto-Analysis System

## 概要

腕時計の撮影画像をAI（Claude Vision API）で自動解析し、ブランド・型番・素材などを構造化データとして抽出するCLIツールです。

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# バーコード読取用ライブラリ（OS別）
# macOS:
brew install zbar
# Ubuntu/Debian:
sudo apt-get install libzbar0
# Windows: pyzbar に同梱

# Anthropic APIキーの設定
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

## 使い方

```bash
# 基本実行（input/ → output/result_YYYYMMDD_HHMMSS.csv）
python main.py

# フォルダ指定
python main.py --input ./images/lot001 --output ./results/lot001.csv

# 個別処理モード（1商品ずつ即座にレスポンス）
python main.py --mode single --input ./images/item001/

# バッチモード（Batch API利用・50%割引）
python main.py --mode batch --input ./images/lot001/

# Excel出力
python main.py --format excel --output ./results/lot001.xlsx

# ドライラン（AIを呼ばずに構造確認のみ）
python main.py --dry-run

# 詳細ログ
python main.py -v
```

## 画像フォルダの構成

### パターンA: 複数商品（1商品=1サブフォルダ）
```
input/
├── item001/
│   ├── 001.jpg    # バーコード
│   ├── 002.jpg    # 正面 ★AI解析
│   ├── 003.jpg    # 斜め
│   ├── 004.jpg    # 側面1
│   ├── 005.jpg    # 側面2
│   ├── 006.jpg    # 側面3
│   ├── 007.jpg    # 側面4
│   ├── 008.jpg    # 裏蓋斜め
│   ├── 009.jpg    # 裏蓋 ★AI解析
│   ├── 010.jpg    # 裏蓋正面
│   ├── 011.jpg    # コメントシール1 ★AI解析（存在時のみ）
│   └── 012.jpg    # コメントシール2 ★AI解析（存在時のみ）
├── item002/
│   └── ...
```

### パターンB: 1商品のみ（直下に画像）
```
input/
├── 001.jpg
├── 002.jpg
└── ...
```

## 出力CSV列

| # | 列名 | 内容 |
|---|------|------|
| 1 | 管理番号 | バーコードから読み取った管理番号 |
| 2 | カテゴリ番号 | mapping.xlsx照合結果 |
| 3 | タイトル | 65文字タイトル |
| 4 | ブランド英字 | AI解析結果 |
| 5 | ブランドカナ | AI解析結果 |
| 6 | シリーズ英字 | AI解析結果 |
| 7 | シリーズカナ | AI解析結果 |
| 8 | 型番 | 裏蓋OCR結果 |
| 9 | 素材 | 正規化済み素材名 |
| 10 | 防水 | 正規化済み防水表記 |
| 11 | ムーブメント | AI推定結果 |
| 12 | 文字盤色 | AI解析結果 |
| 13 | 針数 | AI解析結果 |
| 14 | 異常内容 | コメントシールのテキスト |
| 15 | 処理ステータス | 正常 / エラー内容 |

## カテゴリマッピング（4段階フォールバック）

1. **ブランド+シリーズ完全一致** → そのカテゴリ番号
2. **ブランドのみ一致** → 「（その他）」カテゴリ
3. **汎用カテゴリ** → 性別+ムーブメント+針数で検索
4. **不明** → 空白（手動入力）

## ディレクトリ構成

```
watch-ai-analyzer/
├── main.py                    # エントリーポイント（CLI）
├── config.py                  # 設定ファイル
├── requirements.txt           # 依存パッケージ
├── README.md                  # このファイル
├── modules/
│   ├── folder_scanner.py      # フォルダスキャン・画像仕分け
│   ├── barcode_reader.py      # バーコード読取
│   ├── ai_analyzer.py         # Claude Vision API連携
│   ├── normalizer.py          # データ正規化
│   ├── category_mapper.py     # カテゴリマッピング
│   ├── title_generator.py     # タイトル生成
│   └── csv_writer.py          # CSV/Excel出力
├── prompts/
│   ├── front_analysis.txt     # 正面画像解析プロンプト
│   ├── back_analysis.txt      # 裏蓋画像解析プロンプト
│   └── comment_analysis.txt   # コメントシール解析プロンプト
├── data/
│   └── mapping.xlsx           # カテゴリマッピングテーブル
├── input/                     # 入力画像フォルダ
└── output/                    # 出力CSV
```
