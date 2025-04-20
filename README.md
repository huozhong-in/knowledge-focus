---
marp: true
---

# KnowledgeFocus
Focus on building an open and extensible AI knowledge base system. Suitable for individual use, small teams, and even larger enterprises. Its excellent openness allows for easy integration into existing workflows.


# 开发环境搭建

## 1. api目录下建立python虚拟环境

`cd api`

`conda create -p ./.venv -y python=3.12 --always-copy`

`conda activate ./.venv`

## 2. 安装依赖

`cd api`

`pip install fastapi uvicorn`

## 3. 给tauri app安装依赖并进行开发

`cd tauri-app`

`bun install`

`bun tauri dev`

## 4. 打包应用

`bun tauri build --bundles app`