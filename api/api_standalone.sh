#!/bin/bash

# 从 config.py 中读取数据库路径
DB_PATH=$(sed -n 's/^TEST_DB_PATH = "\(.*\)"/\1/p' config.py)

python main.py \
--port 60315 \
--host 127.0.0.1 \
--db-path "$DB_PATH" \
--mode dev
