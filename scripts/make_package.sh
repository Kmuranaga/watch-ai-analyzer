#!/usr/bin/env bash
# watch-ai-analyzer 配布パッケージ作成スクリプト
#
# 過去の梱包事故の再発防止用:
#   ①STAR修正の反映漏れ ②PR#28の反映漏れ … 古いチェックアウトから作られた
#   ③.venv（Macのシンボリックリンク含む）混入でWindows解凍エラー
#
# 方式: git archive で「コミット済みのHEADツリー」から直接zipを作る。
#   - 作業ディレクトリの状態（未追跡のクライアントデータ tmp/ やローカル設定の
#     変更）に一切依存しないため、古いファイルや未追跡物が混入する余地がない
#   - .venv/.env/input/output/tmp 等は元々git管理外なので自動的に除外される
#   - 前提条件は「mainブランチ」かつ「HEAD == origin/main」のみ
#
# リポジトリルートで実行する前提。
set -euo pipefail

fail() {
    echo "エラー: $1" >&2
    exit 1
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || fail "gitリポジトリの中で実行してください"
cd "$repo_root"

echo "origin から最新情報を取得しています..."
git fetch origin || fail "git fetch origin に失敗しました"

current_branch=$(git rev-parse --abbrev-ref HEAD)
[ "$current_branch" = "main" ] || fail "現在のブランチは '${current_branch}' です。最新のmainから作成してください。"

head_hash=$(git rev-parse HEAD)
origin_main_hash=$(git rev-parse origin/main)
[ "$head_hash" = "$origin_main_hash" ] || fail "HEAD が origin/main と一致しません。git pull してから作成してください。"

short_hash=$(git rev-parse --short HEAD)
commit_date=$(git show -s --format=%cs HEAD)
version_line="main @ ${short_hash} (${commit_date})"
echo "$version_line" > VERSION
trap 'rm -f "$repo_root/VERSION"' EXIT

zip_name="watch-ai-analyzer_${short_hash}.zip"
rm -f "$zip_name"

# HEADのコミット内容のみをzip化（作業ディレクトリの状態に非依存）。
# .claude（ローカル設定）と *.pages（旧仕様書）はgit管理下だが配布対象外。
git archive HEAD \
    --prefix=watch-ai-analyzer/ \
    --add-file=VERSION \
    -o "$zip_name" \
    -- . ':(exclude).claude' ':(exclude)*.pages' \
    || fail "zip作成に失敗しました"

file_count=$(unzip -l "$zip_name" | tail -1 | awk '{print $2}')
zip_size=$(du -h "$zip_name" | cut -f1)

echo ""
echo "パッケージを作成しました:"
echo "  ファイル : $zip_name"
echo "  バージョン: $version_line"
echo "  ファイル数: $file_count"
echo "  サイズ   : $zip_size"
