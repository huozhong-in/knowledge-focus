sh ./sync-version.sh
# bunx tauri signer generate -w ~/.tauri/myapp.key
TAURI_SIGNING_PRIVATE_KEY=${HOME}/.tauri/myapp.key bun tauri build --bundles app
