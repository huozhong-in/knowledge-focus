#!/bin/sh

# 同步 tauri.conf.json 中的版本号到src/version.ts
sh scripts/sync-version.sh

# 构建未签名的应用包和updater
TAURI_SIGNING_PRIVATE_KEY="${HOME}/.tauri/kf-updater.key" TAURI_SIGNING_PRIVATE_KEY_PASSWORD="rD4QInFlBk4DtX" bun tauri build --bundles app
