#!/usr/bin/env bash
# Build SmartCaja Linux installers (AppImage, deb, rpm) inside Ubuntu 24.04.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export CARGO_TERM_COLOR=always

echo "==> Installing OS packages"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl wget file git pkg-config xz-utils \
  python3.12 python3.12-venv python3.12-dev \
  build-essential libssl-dev \
  libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev \
  libayatana-appindicator3-dev patchelf \
  libfuse2 squashfs-tools rpm rsync >/dev/null

if ! command -v node >/dev/null 2>&1; then
  echo "==> Installing Node.js 20"
  curl -fsSL https://nodejs.org/dist/v20.18.1/node-v20.18.1-linux-x64.tar.xz \
    | tar -xJ -C /usr/local --strip-components=1
fi

if ! command -v rustc >/dev/null 2>&1; then
  echo "==> Installing Rust"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
fi
# shellcheck disable=SC1091
. "$HOME/.cargo/env"

echo "==> Copying source to Linux filesystem"
rm -rf /work
mkdir -p /work
rsync -a \
  --exclude venv --exclude .venv-linux --exclude node_modules \
  --exclude target --exclude dist --exclude .git --exclude '*.patch' \
  --exclude 'desktop/backend/build' --exclude 'desktop/backend/dist' \
  --exclude 'desktop/src-tauri/binaries/backend-*' \
  --exclude 'desktop/src-tauri/target' \
  /src/ /work/
# Windows checkout uses CRLF; bash on Linux rejects `set -o pipefail\r`.
find /work -type f \( -name '*.sh' -o -name '*.mjs' \) -print0 | xargs -0 sed -i 's/\r$//'
cd /work

echo "==> Python venv + PyInstaller sidecar"
python3.12 -m venv /work/.venv-linux
/work/.venv-linux/bin/python -m pip install -q -U pip
/work/.venv-linux/bin/python -m pip install -q -r requirements-desktop.txt pyinstaller
export PYTHON=/work/.venv-linux/bin/python
bash desktop/scripts/build-backend.sh

echo "==> Tauri Linux bundles"
cd /work/desktop
npm install --no-fund --no-audit
if [ ! -f src-tauri/icons/icon.ico ]; then
  npm run icon
fi
npm run build

echo "==> Collecting artifacts"
mkdir -p /out
found=0
while IFS= read -r -d '' f; do
  cp -v "$f" /out/
  found=1
done < <(find src-tauri/target -type f \( -name '*.AppImage' -o -name '*.deb' -o -name '*.rpm' \) -print0)
if [ "$found" -eq 0 ]; then
  echo "ERROR: no Linux bundles produced" >&2
  find src-tauri/target -maxdepth 5 -type d -print
  exit 1
fi
ls -lh /out
echo "==> Linux installers ready in /out"
