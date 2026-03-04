# 腕時計AI自動解析システム テスト版 (v0.1)

Watch AI Auto-Analysis System

## 概要

腕時計の撮影画像をAI（Claude Vision API）で自動解析し、ブランド・型番・素材などを構造化データとして抽出するCLIツールです。

システム仕分け後のデータ（商品ごとにフォルダ分け済み、フォルダ名に管理番号を含む）をそのまま投入できます。

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# Anthropic APIキーの設定（Windows）
setx ANTHROPIC_API_KEY "sk-ant-api03-..."

# Anthropic APIキーの設定（Mac / Linux）
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

## 使い方

```bash
# 基本実行（input/ → output/result_YYYYMMDD_HHMMSS.csv）
python main.py

# フォルダ指定
python main.py --input D:\Photos\lot001 --output D:\Results\lot001.csv

# バッチモード（Batch API利用・50%割引）
python main.py --mode batch --input D:\Photos\lot001

# Excel出力
python main.py --format excel

# ドライラン（AIを呼ばずに構造確認のみ）
python main.py --dry-run

# 詳細ログ
python main.py -v
```

## 入力データの形式

システム仕分け後のデータをそのまま使用します。フォルダ名の先頭の数字部分を管理番号として自動取得するため、バーコード読取処理は不要です。

### フォルダ構成

```
input\
├── 1234567_SEIKO セイコー\
│   ├── 001.jpg    # 正面 ★AI解析
│   ├── 002.jpg    # 斜め
│   ├── 003.jpg    # 側面1
│   ├── 004.jpg    # 側面2
│   ├── 005.jpg    # 側面3
│   ├── 006.jpg    # 側面4
│   ├── 007.jpg    # 裏蓋斜め
│   ├── 008.jpg    # 裏蓋 ★AI解析
│   ├── 009.jpg    # 裏蓋正面
│   ├── 010.jpg    # コメントシール1 ★AI解析（存在時のみ）
│   └── 011.jpg    # コメントシール2 ★AI解析（存在時のみ）
├── 9876543_OMEGA オメガ\
│   └── ...
```

### フォルダ名のルール

- 先頭が数字で始まること（例: `1234567_時計`）
- 先頭の連続する数字部分が管理番号として使われます
- アンダースコア以降の商品名部分は自由です

### 画像枚数

- 9枚: 商品画像のみ（異常報告なし）
- 10枚: 商品画像 + コメントシール1枚
- 11枚: 商品画像 + コメントシール2枚

## 出力CSV列

| # | 列名 | 内容 |
|---|------|------|
| 1 | 管理番号 | フォルダ名から抽出した管理番号 |
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
│   ├── folder_scanner.py      # フォルダスキャン・管理番号抽出
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