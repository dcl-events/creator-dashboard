#!/bin/zsh
# 20万ダイヤ以上ライバーダッシュボードの毎朝更新。
# tiktok-automation/run-daily.sh の最後（スプシ書き込み後）から呼ばれる。単独でも実行可。
set -e
cd "$(dirname "$0")"
PY="$HOME/Claude/pococha/.venv/bin/python"
"$PY" -W ignore tools/build.py
"$PY" -W ignore tools/push_sheet.py
git add -A docs
if git diff --cached --quiet; then echo "変更なし（pushしない）"; exit 0; fi
git -c user.name=dcl-events -c user.email=dcl-events@users.noreply.github.com \
  commit -qm "Daily update $(date +%Y-%m-%d)"
git push -q
echo "push OK"
