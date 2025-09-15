#!/bin/sh
# 获取 tauri.conf.json 中的版本号
VERSION=$(grep '"version"' src-tauri/tauri.conf.json | head -1 | sed 's/.*"version": "\(.*\)".*/\1/')
cat > src/version.ts << EOF
// 应用版本配置 - 自动生成，请勿手动编辑
export const APP_VERSION = "$VERSION";
export const BUILD_DATE = "$(date -u +%Y-%m-%d)";
export const BUILD_TIME = "$(date -u +%Y-%m-%dT%H:%M:%SZ)";
// 版本信息对象
export const VERSION_INFO = {
  version: APP_VERSION,
  buildDate: BUILD_DATE,
  buildTime: BUILD_TIME,
  environment: import.meta.env.MODE,
} as const;
EOF
echo "版本号已同步: $VERSION"

# 从环境变量读取签名身份
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-}"
# 取得脚本当前目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Script directory: $SCRIPT_DIR"
SIDECAR_PATHS=("$SCRIPT_DIR/src-tauri/target/release/uv" "$SCRIPT_DIR/src-tauri/target/release/uvx" "$SCRIPT_DIR/src-tauri/target/release/bun")
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