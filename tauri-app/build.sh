#!/bin/sh

TAURI_SIGNING_PRIVATE_KEY="${HOME}/.tauri/kf-updater.key" TAURI_SIGNING_PRIVATE_KEY_PASSWORD="rD4QInFlBk4DtX" bun tauri build --bundles app,dmg
