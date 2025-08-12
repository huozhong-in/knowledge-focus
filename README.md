# KnowledgeFocus

Focus on building an open and extensible AI knowledge base system. Suitable for individual use, small teams, and even larger enterprises. Its excellent openness allows for easy integration into existing workflows.

## 功能特点

### 文件监控与智能分类

KnowledgeFocus包含一个强大的文件监控系统，可以自动监控指定的文件夹，实时跟踪文件变化并进行智能分类。主要功能包括：

1. **实时文件监控** - 使用高性能的文件系统事件监听，检测新增、修改和删除的文件
2. **初步文件分类** - 在Rust端进行粗筛（初步分类），根据文件类型、名称等特征进行快速分类
3. **元数据提取** - 自动提取文件的元数据信息，包括创建时间、修改时间、大小、哈希值等
4. **规则匹配** - 应用可配置的规则来对文件进行标记和分类
5. **批量处理** - 高效地批量处理文件元数据，减少网络和系统资源开销
6. **与Python API集成** - 将初步处理结果发送到Python后端，进行进一步的深度分析和处理

### 其他核心功能

## 开发环境搭建

### 1. api文件夹下建立python虚拟环境

`cd api`

使用conda而不是uv，因为uv的虚拟环境是软链接，不能打包进release包。

`conda create -p ./.venv -y python=3.12 --always-copy`

使用`./`前缀是为了跟带有名字的conda全局虚拟环境区分开来，使用的是当前目录中的.venv。

`conda activate ./.venv`

## 2. 安装依赖

`cd api`

不要使用uv安装Python包，因为是软链接不能打包进release包，要使用pip。

`pip install fastapi uvicorn`

### 3. 给tauri app安装依赖并进行开发

`cd tauri-app`

`bun install`

`bun tauri dev`

#### 重新生成icon

`bun tauri icon`

默认读取app-icon.png文件，生成所有平台所需图标文件，放在了icons文件夹下。

### 4. 打包应用

`bun tauri build --bundles app`

### 5. 升级Tauri

更新 Tauri 依赖：
`cd tauri-app && bun update @tauri-apps/api@latest @tauri-apps/cli@latest`

更新 Rust 端的 Tauri 依赖：
`cd src-tauri && cargo update`

验证更新是否成功：
`cd ../../tauri-app && bun tauri info`
