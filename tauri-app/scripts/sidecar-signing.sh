#!/bin/sh
# 处理sidecar的签名问题

set -e
echo "Starting pre-bundle script..."
# 从环境变量读取签名身份
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-}"
# 取得脚本当前目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Script directory: $SCRIPT_DIR"
SIDECAR_PATHS=(
    "$SCRIPT_DIR/tauri-app/src-tauri/bin/uv-aarch64-apple-darwin" 
    "$SCRIPT_DIR/tauri-app/src-tauri/bin/uvx-aarch64-apple-darwin" 
    "$SCRIPT_DIR/tauri-app/src-tauri/bin/bun-aarch64-apple-darwin"
    )
# 循环处理每个sidecar
for SIDECAR_PATH in "${SIDECAR_PATHS[@]}"; do
    echo "Processing sidecar at: $SIDECAR_PATH"
    if [ -f "$SIDECAR_PATH" ]; then
        echo "Clearing extended attributes..."
        sudo xattr -cr "$SIDECAR_PATH"
        echo "Re-signing binary with identity: $SIGNING_IDENTITY"
        codesign --force --deep --sign "$SIGNING_IDENTITY" "$SIDECAR_PATH"
        echo "Sidecar processed successfully: $SIDECAR_PATH"
    else
        echo "Sidecar not found, skipping: $SIDECAR_PATH"
    fi
done
echo "All sidecars processed successfully."