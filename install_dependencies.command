#!/bin/zsh
set -euo pipefail

echo "Vivo Lightroom 档案转换器 — 安装运行依赖"
echo

if ! command -v brew >/dev/null 2>&1; then
  echo "未找到 Homebrew。请先按 https://brew.sh/ 的官方说明安装。"
  read -r "?按回车键退出…"
  exit 1
fi

brew install ffmpeg python@3.12 dovi_tool

PYTHON312="$(brew --prefix python@3.12)/bin/python3.12"
VENV="$HOME/Library/Application Support/VivoLightroomArchiveConverter/venv"
mkdir -p "${VENV:h}"
"$PYTHON312" -m venv "$VENV"
"$VENV/bin/python3" -m pip install --upgrade pip
"$VENV/bin/python3" -m pip install "av==18.1.0"

echo
"$VENV/bin/python3" -c 'import av; print("PyAV", av.__version__)'
ffmpeg -version | head -n 1
dovi_tool --version
echo
echo "依赖安装完成。现在可以打开 App。"
read -r "?按回车键退出…"
