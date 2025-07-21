#!/bin/bash

# 获取 tauri.conf.json 中的版本号
VERSION=$(grep '"version"' src-tauri/tauri.conf.json | head -1 | sed 's/.*"version": "\(.*\)".*/\1/')

# 更新前端版本文件
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
