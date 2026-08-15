#!/usr/bin/env bash
# watch-ai-analyzer 配布パッケージ作成スクリプト
#
# 過去の梱包事故の再発防止用:
#   ①STAR修正の反映漏れ ②PR#28の反映漏れ … 古いチェックアウトから作られた
#   ③.venv（Macのシンボリックリンク含む）混入でWindows解凍エラー
# そのため「最新のorigin/main・未コミット変更なし」の状態からのみパッケージを作成する。
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

[ -z "$(git status --porcelain)" ] || fail "未コミットの変更（または未追跡ファイル）があります。最新のmainから作成してください。"

head_hash=$(git rev-parse HEAD)
origin_main_hash=$(git rev-parse origin/main)
[ "$head_hash" = "$origin_main_hash" ] || fail "HEAD が origin/main と一致しません。最新のmainから作成してください。"

short_hash=$(git rev-parse --short HEAD)
commit_date=$(git show -s --format=%cs HEAD)
version_line="main @ ${short_hash} (${commit_date})"
echo "$version_line" > VERSION

zip_name="watch-ai-analyzer_${short_hash}.zip"
rm -f "$zip_name"

staging_dir=$(mktemp -d)
trap 'rm -rf "$staging_dir"' EXIT

# rsyncでexclude指定しつつ、zip内トップレベルが watch-ai-analyzer/ になるよう
# 実際のディレクトリ名に依存しないステージング先へコピーする。
rsync -a \
    --exclude='.venv/' \
    --exclude='.env' \
    --exclude='.git/' \
    --exclude='.claude/' \
    --exclude='.codex/' \
    --exclude='__pycache__/' \
    --exclude='input/' \
    --exclude='output/' \
    --exclude='tmp/' \
    --exclude='*.pages' \
    --exclude='.pytest_cache/' \
    --exclude='AGENTS.md' \
    ./ "$staging_dir/watch-ai-analyzer/" || fail "パッケージ内容のコピーに失敗しました"

(cd "$staging_dir" && zip -rq "$repo_root/$zip_name" watch-ai-analyzer) || fail "zip作成に失敗しました"

file_count=$(unzip -l "$zip_name" | tail -1 | awk '{print $2}')
zip_size=$(du -h "$zip_name" | cut -f1)

echo "作成完了: $zip_name"
echo "VERSION: $version_line"
echo "ファイル数: $file_count"
echo "サイズ: $zip_size"
