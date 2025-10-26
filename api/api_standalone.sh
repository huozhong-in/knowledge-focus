#!/bin/bash

# 拼接数据库路径，从 tauri.conf.json 读出 
identifier=$(cat ../tauri-app/src-tauri/tauri.conf.json | jq -r .identifier)

DB_FOLDER=~/Library/Application\ Support/"$identifier"
# 如果不存在就新建文件夹
if [ ! -d "$DB_FOLDER" ]; then
  mkdir -p "$DB_FOLDER"
fi

DB_PATH="$DB_FOLDER"/knowledge-focus.db
echo $DB_PATH


uv run main.py \
--port 60315 \
--host 127.0.0.1 \
--db-path "$DB_PATH" \
