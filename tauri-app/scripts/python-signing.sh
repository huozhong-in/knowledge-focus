#!/bin/sh
# 处理sidecar的签名问题

set -e
echo "Starting pre-bundle script..."
# 从环境变量读取签名身份
SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-}"
# 取得脚本当前目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Script directory: $SCRIPT_DIR"
# 使用jq读取当前文件夹下的notary_log.json，解析出所有path节点的值，即文件路径
# {
#   "logFormatVersion": 1,
#   "jobId": "1faced06-724a-443f-bf46-bdc3febd5ddf",
#   "status": "Invalid",
#   "statusSummary": "Archive contains critical validation errors",
#   "statusCode": 4000,
#   "archiveFilename": "KnowledgeFocus_0.4.2_arm64.dmg",
#   "uploadDate": "2025-10-18T09:24:53.208Z",
#   "sha256": "790808a1a830c8d37d4a4084455eb1278292232b697cb11fc08b67dfadb87487",
#   "ticketContents": null,
#   "issues": [
#     {
#       "severity": "error",
#       "code": null,
#       "path": "KnowledgeFocus_0.4.2_arm64.dmg/KnowledgeFocus.app/Contents/Resources/api/venv/bin/magika",
#       "message": "The binary is not signed with a valid Developer ID certificate.",
#       "docUrl": "https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution/resolving_common_notarization_issues#3087721",
#       "architecture": "arm64"
#     },
#     {
#       "severity": "error",
#       "code": null,
#       "path": "KnowledgeFocus_0.4.2_arm64.dmg/KnowledgeFocus.app/Contents/Resources/api/venv/bin/magika",
#       "message": "The signature does not include a secure timestamp.",
#       "docUrl": "https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution/resolving_common_notarization_issues#3087733",
#       "architecture": "arm64"
#     },
#     {
#       "severity": "error",
#       "code": null,
#       "path": "KnowledgeFocus_0.4.2_arm64.dmg/KnowledgeFocus.app/Contents/Resources/api/venv/bin/magika",
#       "message": "The executable does not have the hardened runtime enabled.",
#       "docUrl": "https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution/resolving_common_notarization_issues#3087724",
#       "architecture": "arm64"
#     }
# ...

DMG_NAME=($(jq -r '.archiveFilename' notary_log.json))
# 使用jq读取当前文件夹下的notary_log.json，解析出所有path节点的值，即文件路径，注意去重
PYTHON_LIB_PATHS=($(jq -r '.issues[].path' notary_log.json | sort -u))
# 将PYTHON_LIB_PATHS中的每个路径中"DMG_NAME/KnowledgeFocus.app/Contents/Resources/api/"前缀去掉
# 如KnowledgeFocus_0.4.2_arm64.dmg/KnowledgeFocus.app/Contents/Resources/api/venv/lib/python3.13/site-packages/torch/bin/protoc
# 变为 .venv/lib/python3.13/site-packages/torch/bin/protoc
for i in "${!PYTHON_LIB_PATHS[@]}"; do
    PYTHON_LIB_PATHS[$i]="$(echo "${PYTHON_LIB_PATHS[$i]}" | sed "s|$DMG_NAME/KnowledgeFocus.app/Contents/Resources/api/venv/|../../api/.venv/|")"
done
# 循环处理每个文件
for PYTHON_LIB_PATH in "${PYTHON_LIB_PATHS[@]}"; do
    echo "Processing : $PYTHON_LIB_PATH"
    if [ -f "$PYTHON_LIB_PATH" ]; then
        echo "Clearing extended attributes..."
        sudo xattr -cr "$PYTHON_LIB_PATH"
        echo "Re-signing binary with identity: $SIGNING_IDENTITY"
        codesign --force --deep --sign "$SIGNING_IDENTITY" "$PYTHON_LIB_PATH"
        echo "Python lib processed successfully: $PYTHON_LIB_PATH"
    else
        echo "Python lib not found, skipping: $PYTHON_LIB_PATH"
    fi
done
echo "All python libs processed successfully."