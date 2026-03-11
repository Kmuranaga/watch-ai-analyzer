# 腕時計AI自動解析システム テスト版 (v0.1)

Watch AI Auto-Analysis System

## 概要

腕時計の撮影画像をAI（Gemini Vision API）で自動解析し、ブランド・型番・素材などを構造化データとして抽出するツールです。

システム仕分け後のデータ（商品ごとにフォルダ分け済み、フォルダ名に管理番号を含む）をそのまま投入できます。

**2つの使い方があります：**

| 方式 | エントリーポイント | 操作 |
|------|-------------------|------|
| **ブラウザUI版**（推奨） | `python app.py` | ブラウザでボタン操作。結果の確認・編集もUI上で完結 |
| CLI版 | `python main.py` | コマンドプロンプトで実行。従来通りの使い方 |

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# Gemini APIキーの設定（Windows）
setx GEMINI_API_KEY "your-api-key"

# Gemini APIキーの設定（Mac / Linux）
export GEMINI_API_KEY=your-api-key
```

> **ブラウザUI版の場合**、APIキーは画面上から設定できます（`.env`ファイルに自動保存）。環境変数の手動設定は不要です。

## 使い方：ブラウザUI版（推奨）

```bash
# 起動
python app.py
```

ブラウザで `http://localhost:8080` を開き、画面上で操作します。

1. APIキーを設定（初回のみ。画面上部の入力欄に貼り付けて「設定」）
2. 入力フォルダを指定（デフォルト: `./input`）
3. 「解析開始」ボタンを押す
4. 結果テーブルで確認・セル編集
5. 「CSVダウンロード」or「Excelダウンロード」

詳しくは `manual_web_ui.docx` を参照してください。

## 使い方：CLI版

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
├── app.py                     # エントリーポイント（ブラウザUI版）
├── main.py                    # エントリーポイント（CLI版）
├── config.py                  # 設定ファイル
├── requirements.txt           # 依存パッケージ
├── README.md                  # このファイル
├── .env                       # APIキー保存（自動生成・git管理外）
├── templates/
│   └── index.html             # ブラウザUI画面
├── modules/
│   ├── folder_scanner.py      # フォルダスキャン・管理番号抽出
│   ├── ai_analyzer.py         # Gemini Vision API連携
│   ├── normalizer.py          # データ正規化
│   ├── category_mapper.py     # カテゴリマッピング
│   ├── title_generator.py     # タイトル生成
│   └── csv_writer.py          # CSV/Excel出力
├── prompts/
│   ├── front_analysis.txt     # 正面画像解析プロンプト
│   ├── back_analysis.txt      # 裏蓋画像解析プロンプト
│   └── comment_analysis.txt   # コメントシール解析プロンプト
├── data/
│   ├── mapping.xlsx           # カテゴリマッピングテーブル
│   └── category_names.xlsx    # カテゴリ番号→名称テーブル
├── input/                     # 入力画像フォルダ
└── output/                    # 出力CSV/Excel
```