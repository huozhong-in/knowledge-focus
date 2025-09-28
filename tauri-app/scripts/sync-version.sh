#!/bin/sh

# 同步版本号脚本 - 从 tauri.conf.json 同步版本号到前端

# 获取 tauri.conf.json 中的版本号
VERSION=$(grep '"version"' src-tauri/tauri.conf.json | head -1 | sed 's/.*"version": "\(.*\)".*/\1/')

# 生成简洁的 version.ts 文件
cat > src/version.ts << EOF
// 应用版本配置 - 自动生成，请勿手动编辑
export const APP_VERSION = "$VERSION";

// 版本信息对象
export const VERSION_INFO = {
  version: APP_VERSION,
  environment: import.meta.env.MODE,
} as const;
EOF

echo "版本号已同步: $VERSION"