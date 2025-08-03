# 多模态检索系统开发进度跟踪

## 项目目标
用户pin文件后，使用docling解析文档，生成父块/子块，实现向量化存储和检索，支持文本、图像、表格的多模态内容处理。

## 技术方案概述
- **解析工具**: 使用docling库，采用做法C（annotation + placeholder）
- **分块策略**: 利用docling的body/groups结构，优先使用内置分块
- **模型调用**: 集成现有model_config_mgr.py体系，使用vision和embedding模型
- **数据存储**: SQLite存储元数据关系，LanceDB存储向量数据
- **任务系统**: 集成到现有task_processor，支持HIGH优先级处理
- **前端反馈**: 通过bridge_events.py实现实时进度推送

---

## 📝 重要设计修正

**2025-08-03 用户反馈修正**：
- ✅ **路径问题修正**: 使用数据库目录的父目录，不在同级目录创建文件夹
- ✅ **核心设计理念澄清**: 
  - 父块 = 最终提供给LLM答案合成的"原始完整内容"，**不需要向量化**
  - 子块 = 用于向量检索的"代理单元"，**才需要向量化**
  - 检索流程: 查询 → 子块向量检索 → 找到父块 → 返回父块内容给LLM
- ✅ **向量化逻辑修正**: `_vectorize_and_store` 只处理子块，父块只存储在SQLite
- ✅ **函数复用问题修正**: `_get_table_context_text` 重新实现，不复用图片方法

---

### 进度项1: 创建chunking_mgr.py核心管理类
- [x] **1.1 基础类结构创建**
  - [x] 创建ChunkingMgr类，定义初始化方法
  - [x] 集成session、lancedb_mgr、models_mgr依赖
  - [x] 添加必要的日志配置和错误处理基础框架

- [x] **1.2 Docling解析集成**
  - [x] 集成docling DocumentConverter，参考test_docling_01.py配置
  - [x] 实现PdfPipelineOptions配置（图片描述、OCR等）
  - [x] 实现文档解析方法，生成DoclingDocument对象
  - [x] 处理docling解析异常和错误情况

- [x] **1.3 父块生成逻辑**
  - [x] 解析DoclingDocument的body结构
  - [x] 利用groups信息判断内容关系
  - [x] 生成文本类型父块（纯文本段落）
  - [x] 生成图像类型父块（图片+周围上下文）
  - [x] 生成表格类型父块（表格图片+描述）
  - [x] 实现父块元数据提取（页码、位置等）

- [x] **1.4 子块生成逻辑**
  - [x] 文本父块→子块：直接使用或生成摘要
  - [x] 图像父块→子块：调用vision模型生成描述
  - [x] 表格父块→子块：调用vision模型生成描述
  - [x] 实现图文关系子块（图片描述+周围文本）
  - [x] 生成唯一vector_id（使用nanoid或UUID）

### 进度项2: 数据存储逻辑实现
- [x] **2.1 Document表操作**
  - [x] 实现文档记录创建/更新
  - [x] 文件hash计算和变更检测
  - [x] docling JSON结果存储路径管理
  - [x] 处理状态标记（pending/processing/done/error）

- [x] **2.2 ParentChunk表操作**
  - [x] 实现父块批量插入
  - [x] 不同chunk_type的content存储策略
  - [x] metadata_json的结构化存储
  - [x] 与Document的外键关联处理

- [x] **2.3 ChildChunk表操作**
  - [x] 实现子块批量插入
  - [x] retrieval_content的文本处理
  - [x] vector_id的唯一性保证
  - [x] 与ParentChunk的外键关联处理

- [x] **2.4 LanceDB向量存储**
  - [x] 调用models_mgr的get_embedding方法
  - [x] 实现VectorRecord的批量插入
  - [x] 设置正确的冗余元数据（parent_chunk_id, document_id）
  - [x] 处理向量化失败的情况

---

## 第二阶段：任务集成和API端点

### 进度项3: 集成到现有任务系统
- [ ] **3.1 main.py任务处理扩展**
  - [ ] 在task_processor中添加MULTIVECTOR任务类型分支
  - [ ] 实现单文件高优先级处理逻辑
  - [ ] 集成ChunkingMgr到任务处理流程
  - [ ] 添加任务状态更新和错误处理

- [ ] **3.2 API端点创建**
  - [ ] 创建/pin-file端点接收前端请求
  - [ ] 验证文件路径和权限
  - [ ] 创建MULTIVECTOR任务记录
  - [ ] 返回任务ID和初始状态给前端

- [ ] **3.3 任务数据结构**
  - [ ] 定义extra_data中的文件路径传递
  - [ ] 确保HIGH优先级任务的正确处理
  - [ ] 实现任务创建和状态管理的辅助方法

---

## 第三阶段：前端事件反馈

### 进度项4: 实时进度反馈
- [ ] **4.1 进度事件发送**
  - [ ] 在ChunkingMgr中集成BridgeEventSender
  - [ ] 发送解析开始/完成事件
  - [ ] 发送分块进度事件（当前/总数）
  - [ ] 发送向量化进度事件

- [ ] **4.2 任务完成通知**
  - [ ] 发送任务成功完成事件
  - [ ] 发送任务失败事件（包含错误信息）
  - [ ] 确保事件数据格式符合前端预期

- [ ] **4.3 前端集成验证**
  - [ ] 验证Rust桥接器正常转发事件
  - [ ] 确认前端useBridgeEvents正常接收
  - [ ] 测试事件缓冲和节流机制工作正常

---

## 关键技术细节备忘

### Docling配置要点
- 使用`ImageRefMode.REFERENCED`模式，图片单独保存
- 配置`PictureDescriptionApiOptions`调用本地vision模型
- 解析annotation获取图片描述，剔除后进行纯文本分块

### 数据关系设计
```
Document (1) -> (N) ParentChunk (1) -> (N) ChildChunk (1) -> (1) VectorRecord
```

### 模型调用
- **Vision模型**: 用于图片/表格描述生成
- **Embedding模型**: 用于子块文本向量化
- 都通过models_mgr.py的统一接口调用

### 错误处理策略
- 整体失败处理，前端显示失败状态
- 保存错误信息到task.error_message
- 通过bridge_events发送错误通知

---

## 测试验证计划

### 每个进度项完成后的验证点
1. **进度项1完成**: 能成功解析PDF文件，生成父块/子块数据结构
2. **进度项2完成**: 数据能正确存储到SQLite和LanceDB
3. **进度项3完成**: 前端pin操作能触发后端处理
4. **进度项4完成**: 前端能实时看到处理进度和结果

### 集成测试文件
使用`/Users/dio/Downloads/AI代理的上下文工程：构建Manus的经验教训.pdf`作为测试文件

---

## 当前状态
- [x] 需求分析和技术方案确定
- [x] 进度计划制定
- [ ] 开始开发进度项1

**下一步**: 开始创建chunking_mgr.py文件
