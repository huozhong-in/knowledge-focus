# Splash 启动页优化重构进度

## 📋 项目概述

优化 Splash 启动页，为首次启动用户提供清晰的三阶段启动流程指引，提升用户体验和信心。

## 🎯 核心目标

1. **透明化启动流程**：让用户清楚了解当前进度和剩余步骤
2. **增强用户信心**：通过实时日志和时间估算减少等待焦虑
3. **优雅的错误处理**：提供清晰的解决方案而非复杂的自动重试
4. **横向布局优化**：充分利用 1350px 宽度展示三步流程

## 🚀 三个关键阶段

### Phase 1: Python 环境初始化
- **操作**: `uv sync` 创建虚拟环境并安装依赖
- **首次耗时**: 30-60秒（取决于网络和缓存）
- **失败处理**: 检测虚拟环境是否存在，存在则切换离线模式

### Phase 2: FastAPI 服务启动  
- **操作**: `uv run --offline` 启动 main.py
- **首次耗时**: 10-20秒（创建 __pycache__）
- **失败处理**: 显示错误日志和 GitHub Issues 链接

### Phase 3: 全能小模型下载
- **操作**: 下载 Qwen3-VL 4B (2.61GB)
- **首次耗时**: 3-10分钟（取决于网速）
- **失败处理**: 提供手动下载脚本

## ✅ 已确认的设计决策

### 时间估算策略
- ✅ **模糊范围 + 实时日志**: 显示 "预计 3-5 分钟" + 滚动日志
- ✅ 多层信息披露：当前步骤、文件名、速度、剩余时间
- ✅ 首次启动重点：给足用户信心等待

### 布局设计
- ✅ **横向布局**: 利用 1350px 宽度，三步并排展示
- ✅ 时间轴风格：带连接线的步骤指示器
- ✅ 响应式设计：保证最小宽度 768px 下也能正常显示

### 专家模式
- ✅ **默认折叠**: 只显示一行，保持界面整洁
- ✅ 点击展开：显示详细日志 + 复制按钮 + GitHub Issues 链接
- ✅ 终端风格：黑底绿字模拟终端输出

### 错误恢复
- ✅ **简单原则**: 告诉用户怎么做，然后重启 App
- ✅ 不做复杂重试：避免增加逻辑复杂度
- ✅ 提供手动方案：终端脚本 + 重启指引

### 进度详情
- ✅ **实时更新**: 当前文件名、下载速度、已下载/总大小
- ✅ Python 端增强：修改 `ProgressReporter` 传递更多信息
- ✅ 节流机制：每秒最多更新一次，避免过于频繁

### 视觉动画
- ✅ **零成本动画**: 仅使用 Lucide-react 图标 + CSS
- ✅ 状态指示：旋转、脉冲、变色、弹跳
- ✅ 成功动画：CheckCircle + scale spring 动画
- ✅ 错误状态：AlertTriangle + shake 动画

## 📝 实施任务清单

### Phase 1: 前端重构 (splash.tsx)

#### 1.1 类型定义和状态管理
- [x] 定义 `PhaseStatus` 类型: `'pending' | 'running' | 'success' | 'error'`
- [x] 定义 `StartupPhase` 接口（id, title, status, progress, message, error）
- [x] 使用 `useState` 管理三个阶段的状态
- [x] 添加日志数组状态和专家模式开关

#### 1.2 横向布局实现
- [x] 实现时间轴式布局（三个步骤 + 连接线）
- [x] 每个步骤包含：图标圈、标题、消息、进度条
- [ ] 响应式处理：小屏幕切换为纵向布局
- [x] 添加步骤间的动画过渡

#### 1.3 事件监听增强
- [x] 解析 `api-log` 判断当前阶段（uv sync / FastAPI / model）
- [x] 监听 `model-download-progress` 更新进度
- [x] 监听 `model-download-completed` 标记成功
- [x] 监听 `model-download-failed` 显示错误
- [x] 实现日志数组累积和去重

#### 1.4 专家模式实现
- [x] 默认折叠，显示 "查看详细日志" 按钮
- [x] 展开后显示 ScrollArea 终端风格日志
- [x] 实现 "复制日志" 功能
- [x] 实现 "报告问题" 跳转到 GitHub Issues
- [ ] 日志自动滚动到底部

#### 1.5 时间估算显示
- [x] 显示模糊时间范围 "预计 3-5 分钟"
- [x] 根据阶段显示不同提示文案
- [x] Phase 1: "正在准备 Python 环境..."
- [x] Phase 2: "正在启动 API 服务..."
- [x] Phase 3: "正在下载模型 (2.61GB)..."

#### 1.6 错误处理 UI
- [x] Phase 1 错误：显示网络问题 + 离线模式说明
- [x] Phase 2 错误：显示日志 + 报告问题链接
- [x] Phase 3 错误：显示手动下载脚本选项
- [x] 统一错误面板样式（Alert 组件）

### Phase 2: 后端增强 (Rust + Python)

#### 2.1 Rust 端 (api_startup.rs)
- [ ] 检测虚拟环境是否存在（.venv/bin/python）
- [ ] uv sync 失败时智能切换离线模式
- [ ] 发送阶段标识事件（phase-changed）
- [ ] 优化事件消息格式，便于前端解析

#### 2.2 Python 端 (models_builtin.py)
- [ ] 增强 `ProgressReporter` 传递当前文件名
- [ ] 增加下载速度计算（基于时间差）
- [ ] 通过 `bridge_events` 发送更详细的进度信息
- [ ] 添加 `stage` 字段：'preparing' | 'downloading' | 'verifying'

#### 2.3 手动下载脚本生成
- [ ] 在 Rust 端实现 `generate_download_script` command
- [ ] 脚本使用打包的 `uv run` 命令
- [ ] 生成到临时目录并返回路径
- [ ] 实现 `run_script_in_terminal` command 打开终端执行

### Phase 3: 视觉优化

#### 3.1 步骤指示器动画
- [ ] pending: 灰色圆圈 + 数字
- [ ] running: 蓝色脉冲 + Loader2 旋转图标
- [ ] success: 绿色 + CheckCircle + scale spring 动画
- [ ] error: 红色 + AlertTriangle + shake 动画

#### 3.2 进度条样式
- [ ] 主进度条：2px 高度，蓝色填充
- [ ] 下方显示：已下载/总大小、速度、剩余时间
- [ ] indeterminate 模式：长时间无进度时切换到脉冲动画

#### 3.3 连接线动画
- [ ] 默认灰色虚线
- [ ] 步骤完成后变为实线并填充颜色
- [ ] 使用 CSS transition 实现渐变效果

#### 3.4 整体过渡
- [ ] Logo 淡入动画
- [ ] 步骤依次出现（stagger 动画）
- [ ] 完成后淡出到主界面

### Phase 4: 测试和优化

#### 4.1 场景测试
- [ ] 首次启动（无缓存、无模型）
- [ ] 二次启动（有缓存、有模型）
- [ ] 网络断开场景
- [ ] uv sync 失败场景
- [ ] 模型下载失败场景
- [ ] 模型下载中断后继续

#### 4.2 性能优化
- [ ] 事件节流：避免过于频繁的状态更新
- [ ] 日志限制：最多保留 200 条日志
- [ ] 防抖处理：避免重复请求
- [ ] 内存泄漏检查：确保事件监听器正确清理

#### 4.3 边界情况
- [ ] 磁盘空间不足
- [ ] 权限问题（无法写入目录）
- [ ] Python 版本不兼容
- [ ] 端口占用（FastAPI 启动失败）

## 🎨 UI 组件清单

### 新增组件
- [ ] `PhaseIndicator` - 单个阶段指示器
- [ ] `PhaseConnector` - 阶段间连接线
- [ ] `ExpertModePanel` - 专家模式日志面板
- [ ] `ErrorRecoveryPanel` - 错误恢复面板
- [ ] `ManualDownloadDialog` - 手动下载脚本对话框

### 使用的 shadcn/ui 组件
- Progress
- Alert / AlertTitle / AlertDescription
- Button
- Badge
- Card / CardHeader / CardTitle / CardContent
- ScrollArea
- Tabs / TabsList / TabsTrigger / TabsContent
- Dialog / DialogContent / DialogHeader / DialogTitle

### 使用的 Lucide 图标
- Loader2 (旋转加载)
- CheckCircle (成功)
- AlertTriangle (错误)
- ChevronDown (展开/收起)
- Copy (复制)
- ExternalLink (外部链接)
- Terminal (终端)
- Package (Python 包)
- Server (API 服务)
- Download (模型下载)

## 📊 关键指标

### 性能目标
- 首次启动总耗时: < 5 分钟（网络正常）
- Phase 1 (uv sync): 30-60秒
- Phase 2 (FastAPI): 10-20秒
- Phase 3 (模型下载): 3-10分钟

### 用户体验目标
- 进度更新频率: 每秒 1 次
- 日志可见性: 默认显示最近 5 条
- 错误识别率: 100%（不遗漏任何错误）
- 恢复指引清晰度: 用户无需额外搜索

## 🐛 已知问题和风险

### 潜在问题
1. **huggingface_hub 进度稀疏**: 大文件下载时长时间无更新
   - 缓解方案: 显示 indeterminate progress + "正在下载..."
   
2. **网络波动导致下载失败**: 需要重新开始
   - 缓解方案: snapshot_download 自带断点续传
   
3. **首次启动时间过长**: 用户可能失去耐心
   - 缓解方案: 充分披露信息 + 时间估算 + 动画

### 降级方案
- 如果模型下载失败，提供手动下载脚本
- 如果 uv sync 失败但环境存在，切换离线模式
- 如果 FastAPI 启动失败，显示日志供用户报告

## 📅 时间规划

### Sprint 1: 前端基础 (2小时)
- 重构 splash.tsx 状态管理
- 实现横向布局和步骤指示器
- 实现基础事件监听

### Sprint 2: 交互增强 (1.5小时)
- 实现专家模式面板
- 实现错误处理 UI
- 添加动画效果

### Sprint 3: 后端集成 (1.5小时)
- Rust 端智能降级逻辑
- Python 端进度信息增强
- 手动下载脚本生成

### Sprint 4: 测试和优化 (1小时)
- 各种场景测试
- 性能优化
- Bug 修复

**总计**: 约 6 小时

## 🎯 成功标准

- [ ] 首次启动用户能清楚看到三个阶段
- [ ] 每个阶段都有实时进度反馈
- [ ] 错误时提供清晰的解决方案
- [ ] 专家模式下能看到完整日志
- [ ] 手动下载脚本能正常工作
- [ ] 无控制台警告和错误
- [ ] 内存无泄漏

## 📝 更新日志

### 2025-01-27

#### Sprint 1 完成 ✅

- ✅ 创建优化重构进度文档
- ✅ 确认所有设计决策
- ✅ 完成 Phase 1 前端基础重构
  - 类型定义和状态管理完成
  - 横向时间轴布局实现
  - 三阶段指示器组件完成
  - 事件监听系统重构
  - 专家模式日志面板实现
  - 错误恢复面板基础实现
  - 动画效果（framer-motion）集成

#### Bug 修复 🐛

- ✅ **修复阶段判断逻辑**: 正确识别三个关键状态转换点
  - Phase 1 完成: "Python virtual environment sync completed"
  - Phase 2 开始: "Starting Python API service" / "Initializing FastAPI"
  - Phase 2 完成: "Uvicorn running" / "Application startup complete"
  - 问题描述: Phase 1 (uv sync) 完成后仍显示 loading，应该立即进入 Phase 2
  - 解决方案: 增强日志解析逻辑，使用 else-if 链准确捕获每个阶段的开始和完成

#### 待完成事项

- [ ] 响应式布局优化（小屏幕支持）
- [ ] 日志自动滚动到底部
- [ ] 手动下载脚本生成和执行
- [ ] Rust 端智能降级逻辑
- [ ] Python 端进度信息增强
- [ ] 完整测试和性能优化

---

**最后更新**: 2025-01-27  
**负责人**: GitHub Copilot + Developer  
**优先级**: P0 (最高)
