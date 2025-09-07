# 系统重构进度跟踪

## 异步架构重构 (2025年1月) ✅ 已完成

### 问题背景
在文件标签系统中遇到LanceDB向量数据库查询错误：
- 错误信息：`Unsupported query type: <class 'coroutine'>`
- 根本原因：异步代码传递了协程对象而非实际的向量数据

### 解决方案演进

**第一阶段：异步修复尝试**
- 使用nest_asyncio库处理嵌套事件循环
- 遇到新问题：`this event loop is already running`
- 结论：异步方案在后台任务处理中过于复杂

**第二阶段：同步架构转换 ✅**
完成了完整的异步到同步转换：

1. **main.py**: task_processor函数
   - 移除了复杂的异步事件循环处理
   - 改为简单的while循环 + time.sleep()
   - 移除了async_task_processor函数

2. **models_mgr.py**: get_embedding方法
   - 从AsyncOpenAI客户端改为同步OpenAI客户端
   - 从httpx.AsyncClient改为httpx.Client
   - 保持了其他流式聊天的异步方法不变

3. **tagging_mgr.py**: generate_and_link_tags_for_file
   - 移除await关键字
   - 直接调用同步的embedding方法

4. **file_tagging_mgr.py**: 全面同步化
   - parse_and_tag_file: 移除async/await
   - process_pending_batch: 移除async/await
   - process_single_file_task: 移除async/await
   - 将asyncio.sleep改为time.sleep

### 测试结果
- ✅ 用户测试通过："测试通过了，可以给文件打标签"
- ✅ LanceDB集成正常工作
- ✅ 文件标签系统稳定运行
- ✅ 不再出现协程类型错误

### 技术收获
- 后台任务处理中，同步架构比异步更稳定
- 混合架构可行：核心处理同步，用户交互异步
- LanceDB等数据库更适合同步操作

---

## 文件扫描重构 (2025年8月) 🚧 进行中

### 重构目标
将Rust端从语义判断简化为扩展名判断，Python端专注语义处理，提升性能和可维护性。

### 重构原则
- Rust端：只做文件系统操作 + 扩展名判断
- Python端：语义处理和智能化
- 保留：黑白名单机制、配置变更队列
- 特殊处理：macOS Bundle文件

---

## 第一阶段：数据库层简化

### 1.1 BundleExtension表优化
- [x] 为BundleExtension表添加`is_system_default`字段，标记系统初始化的记录
- [x] 确保初始化的bundle扩展名记录不可删除/修改

### 1.2 删除复杂语义规则
- [x] 创建新的简化方法`_init_basic_file_filter_rules`，只保留基础忽略规则
- [x] 修改`init_db`方法调用，使用简化的规则初始化
- [x] 删除旧的`_init_file_filter_rules`方法（用户自行清理）

### 1.3 简化文件分类和扩展名映射
- [x] 保留FileCategory表的基础分类（文档、图片、音视频、代码等）
- [x] 保留FileExtensionMap表的扩展名映射
- [x] 删除复杂的文件名模式匹配相关代码

### 1.4 数据库初始化方法调整
- [x] 修改`init_db`方法，移除复杂规则的初始化调用
- [x] 确保BundleExtension的初始化包含`is_system_default`标记
- [x] 验证基础数据的完整性

---

## 第二阶段：API端点简化

### 2.1 设计新的配置API
- [x] 创建新的API端点`/api/file-scanning-config`
- [x] 返回简化的配置数据结构：
  ```json
  {
    "extension_mappings": {"pdf": 1, "docx": 1, ...},
    "bundle_extensions": [".app", ".pages", ".numbers", ...],
    "ignore_patterns": [".DS_Store", "node_modules", ...],
    "file_categories": [...]
  }
  ```

### 2.2 修改现有API端点
- [x] 保留`/config/all`端点功能
- [x] 删除复杂语义规则相关的API响应
- [x] 确保Bundle配置的API支持

### 2.3 API实现
- [x] 在`myfolders_api.py`中实现新端点`/file-scanning-config`
- [x] 添加必要的数据库查询逻辑
- [x] 确保返回数据格式的正确性

---

## 第三阶段：Rust端重构

### 3.1 简化文件扫描逻辑
- [ ] 修改`file_scanner.rs`中的扫描逻辑
- [ ] 移除复杂的语义判断代码
- [ ] 只保留扩展名判断逻辑

### 3.2 实现Bundle处理逻辑
- [ ] 在扫描逻辑中添加Bundle识别功能：
  - [ ] 方法1：检查目录扩展名
  - [ ] 方法2：确认`Contents/Info.plist`存在
- [ ] 实现初始扫描时的Bundle处理：
  - [ ] 识别Bundle后停止递归扫描
  - [ ] 将Bundle作为整体文件处理
- [ ] 实现监控时的Bundle事件归并：
  - [ ] 检测事件是否在Bundle内部
  - [ ] 将内部事件转换为Bundle整体变化事件

### 3.3 更新配置获取逻辑
- [x] 创建新的`FileScanningConfig`配置结构体
- [x] 实现`fetch_file_scanning_config`方法适配新API端点
- [ ] 更新现有代码使用新的配置获取方法

### 3.4 保留现有队列机制
- [ ] 确保配置变更队列机制正常工作
- [ ] 简化队列处理逻辑中的复杂规则部分
- [ ] 验证增量扫描和监控更新逻辑

### 3.5 更新相关命令和函数
- [ ] 修改`commands.rs`中相关的Tauri命令
- [ ] 更新`file_monitor.rs`中的监控逻辑
- [ ] 调整`setup_file_monitor.rs`中的初始化逻辑

---

## 第四阶段：集成验证

### 4.1 端到端功能验证
- [ ] 验证文件扫描功能正常
- [ ] 验证Bundle文件处理正确
- [ ] 验证黑白名单功能
- [ ] 验证配置变更响应

### 4.2 性能验证
- [ ] 对比重构前后扫描性能
- [ ] 验证Bundle处理不影响扫描速度
- [ ] 确认内存使用合理

---

## 注意事项

### Bundle处理要点
- Bundle识别：扩展名 + `Contents/Info.plist`确认
- 初始扫描：跳过Bundle内部文件
- 变化监控：内部事件归并为Bundle整体事件
- 作为整体：Bundle本身就是用户搜索的目标

### 配置变更机制
- 初始扫描期间：配置变更排队等待
- 扫描完成后：配置变更立即处理
- 数据清理：黑名单文件夹立即删除记录

### 性能考虑
- 扩展名判断比语义判断快
- 更多文件进入粗筛表是可接受的
- Python端用markitdown过滤处理

---

## 当前状态
� **第二阶段基本完成，第三阶段进行中**

**已完成：**
- ✅ BundleExtension表添加is_system_default字段
- ✅ 创建简化的基础文件过滤规则
- ✅ 实现新的API端点 `/file-scanning-config`
- ✅ 创建Rust端新的配置结构FileScanningConfig
- ✅ 实现获取简化配置的方法

**进行中：**
- 🚧 Rust端文件扫描逻辑简化
- 🚧 Bundle处理逻辑实现

**下一步：**
- 实现Bundle识别和处理逻辑
- 简化文件扫描逻辑，只做扩展名判断
- 更新扫描逻辑使用新的配置

---

## 总体进度状态

### 异步架构重构 ✅ 完成
- ✅ LanceDB协程错误修复
- ✅ 异步到同步架构转换
- ✅ 文件标签系统测试通过
- ✅ 系统稳定性提升

### 代码清理计划
基于异步重构的完成，建议进行以下清理工作：
- 移除未使用的async导入和装饰器
- 清理废弃的nest_asyncio相关代码
- 整理模块间的依赖关系
- 验证所有测试用例的有效性

最后更新：2025年1月20日
