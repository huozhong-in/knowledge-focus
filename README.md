# KnowledgeFocus
Focus on building an open and extensible AI knowledge base system. Suitable for individual use, small teams, and even larger enterprises. Its excellent openness allows for easy integration into existing workflows.


# 开发环境搭建

## 1. api文件夹下建立python虚拟环境

`cd api`

`conda create -p ./.venv -y python=3.12 --always-copy`

`conda activate ./.venv`

## 2. 安装依赖

`cd api`

不要使用uv安装Python包，因为是软链接不能打包进release包，使用pip。

`pip install fastapi uvicorn`

## 3. 给tauri app安装依赖并进行开发

`cd tauri-app`

`bun install`

`bun tauri dev`

### 重新生成icon

`bun tauri icon`

默认读取app-icon.png文件，生成所有平台所需图标文件，放在了icons文件夹下。

## 4. 打包应用

`bun tauri build --bundles app`