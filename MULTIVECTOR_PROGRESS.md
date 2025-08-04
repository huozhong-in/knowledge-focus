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

## 向量化激活机制
多模态向量化有两种激活方式：
1. **用户主动pin文件**: 创建HIGH优先级MULTIVECTOR任务，立即处理
2. **文件内容变化**: Rust监控→粗筛表→HIGH优先级TAGGING任务→**自动衔接MULTIVECTOR任务**（仅当文件处于pin状态时）

这确保了：
- 用户关注的文件始终保持最新的向量化状态
- 避免对未被pin文件进行昂贵的向量化操作
- 提供实时的文档变化响应能力

### 第一阶段实现亮点

**ChunkingMgr核心引擎**:
- `process_document()`: 完整的文档处理流程，从解析到存储一站式
- `_init_chunker()`: 智能tokenizer解耦，支持多语言文档处理
- `_generate_chunks()`: Docling HybridChunker集成，智能分块策略
- `_determine_chunk_type()`: 增强类型检测，支持debugging模式
- `_create_image_context_chunks()`: MULTIVECTOR.md核心功能，图文关系增强

**数据纯净性保证**:
- 父块存储`raw_content`：保持原始文档内容的完整性
- 子块存储`retrieval_content`：LLM优化的检索友好内容
- 混合内容检测：自动识别和分离图像描述与原始文本

**多模态内容处理**:
- 支持chunk_type: `text`, `image`, `table`, `image_context`
- Vision模型集成：自动生成图像和表格的文本描述
- 上下文感知：图像块结合周围文本创建关系块

### Docling配置要点ing的body/groups结构，优先使用内置分块
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

**关键技术突破**：
- ✅ **Tokenizer解耦设计**: Docling chunker使用通用tokenizer，与embedding模型完全解耦，通过API调用生成向量
- ✅ **数据纯净性原则**: 修正数据污染问题，父块存储raw_content(原始内容)，子块存储contextualized_content(上下文化内容)
- ✅ **Chunk类型检测**: 解决所有chunk显示为"text"的bug，正确识别image、table、text类型
- ✅ **混合内容分离**: 实现mixed content检测和分离，确保图像描述与原始文本不混合
- ✅ **图文关系增强**: 实现MULTIVECTOR.md核心设计 - 创建image_context类型父块，结合图像描述与周围文本摘要

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

## 🎉 第一阶段完成庆祝 (2025-08-03)

**第一阶段：核心多模态分块引擎** - ✅ **成功完成** 🎊

### 主要成就

1. **完整的多模态解析和分块系统**
   - 成功集成Docling库，实现PDF/DOCX多模态文档解析
   - 实现智能分块策略，支持文本、图像、表格三种内容类型
   - 建立完整的父块-子块架构，满足检索和合成的不同需求

2. **技术架构突破**
   - 解决tokenizer解耦难题，使系统更加灵活稳定
   - 实现数据纯净性原则，确保原始内容与AI生成内容分离
   - 建立robust的错误处理和调试机制

3. **MULTIVECTOR.md设计实现**
   - 成功实现"图片描述 + 周围原始文本摘要"的图文关系增强
   - 建立多层次检索能力，为复杂问答奠定基础
   - 完整的SQLite + LanceDB存储架构

4. **验证成果**
   - 测试文档成功处理：23个父块，26个子块（包含3个图文关系块）
   - 所有chunk类型正确识别（text、image、table、image_context）
   - 向量化和存储流程验证通过

### 技术债务清理
- ✅ 修正chunk类型检测bug
- ✅ 解决数据污染问题
- ✅ 优化混合内容处理逻辑
- ✅ 完善调试和日志系统

**下一步**：进入第二阶段 - 任务系统集成和API端点开发

---

## 第二阶段：任务集成和API端点

### 进度项3: 集成到现有任务系统

- [x] **3.1 main.py任务处理扩展**
  - [x] 在task_processor中添加MULTIVECTOR任务类型分支
  - [x] 实现单文件高优先级处理逻辑
  - [x] 集成ChunkingMgr到任务处理流程
  - [x] 添加任务状态更新和错误处理
  - [x] 实现基于任务记录的文件pin状态检查机制（8小时窗口）

- [x] **3.2 API端点创建**
  - [x] 创建/pin-file端点接收前端请求
  - [x] 验证文件路径和权限
  - [x] 创建MULTIVECTOR任务记录
  - [x] 返回任务ID和初始状态给前端
  - [x] 添加/task/{task_id}端点查询任务状态
  - [ ] 取得从PDF解析后另存的图像文件的API

- [x] **3.3 任务数据结构**
  - [x] 定义extra_data中的文件路径传递
  - [x] 确保HIGH优先级任务的正确处理
  - [x] 实现任务创建和状态管理的辅助方法
  - [x] 添加target_file_path冗余字段支持高效查询
  - [x] 实现is_file_recently_pinned方法检查8小时窗口

- [x] **3.4 TAGGING→MULTIVECTOR自动衔接**
  - [x] 在TAGGING任务完成后检查文件pin状态
  - [x] 自动创建HIGH优先级MULTIVECTOR任务（仅当文件被pin时）
  - [x] 实现pin状态检查机制（临时版本）
  - [x] 确保任务链式处理的稳定性

### 🎉 进度项3 基本完成！

**第二阶段核心功能已实现**：
- ✅ **任务处理扩展**: task_processor现在支持MULTIVECTOR任务类型
- ✅ **Pin文件API**: /pin-file端点可接收前端pin操作
- ✅ **自动衔接机制**: TAGGING任务完成后自动检查pin状态并创建MULTIVECTOR任务
- ✅ **错误处理**: 完整的异常处理和日志记录
- ✅ **文件验证**: 路径存在性、权限、文件类型检查

**临时实现说明**：
- 📝 pin状态检查目前使用文件扩展名判断（重要文档类型）
- 📝 实际应用中需要实现真正的pin状态存储和查询机制

**待优化项目**：
- [ ] 实现真正的pin状态数据库表或缓存机制
- [ ] PDF解析后图像文件获取API
- [ ] 前端pin状态与后端状态同步机制

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
- 使用`ImageRefMode.PLACEHOLDER`模式，图片单独保存
- 配置`PictureDescriptionApiOptions`调用本地vision模型
- 解析annotation获取图片描述，剔除后进行纯文本分块

### 数据关系设计
```
Document (1) -> (N) ParentChunk (1) -> (N) ChildChunk (1) -> (1) VectorRecord
```

### 模型调用
- **Vision模型**: 用于图片/表格描述生成
- **Embedding模型**: 用于子块文本向量化
- **纯文本模型**: 用于对纯文本内容生成摘要
- 都通过models_mgr.py的统一接口调用

### 错误处理策略
- 整体失败处理，前端显示失败状态
- 保存错误信息到task.error_message
- 通过bridge_events发送错误通知

---

## 测试验证计划

### 每个进度项完成后的验证点
1. **✅ 进度项1完成**: 能成功解析PDF文件，生成父块/子块数据结构
2. **✅ 进度项2完成**: 数据能正确存储到SQLite和LanceDB
3. **⏳ 进度项3待开发**: 前端pin操作能触发后端处理
4. **⏳ 进度项4待开发**: 前端能实时看到处理进度和结果

### 第一阶段验证成果

**实际测试结果** (2025-08-03):
- ✅ **文档解析**: 成功解析AI代理PDF文档，提取文本、图像、表格
- ✅ **智能分块**: 生成29个父块，包含纯文本、图像、表格、图像+上下文，4种类型
- ✅ **子块生成**: 创建29个子块，包含3个图文关系增强块
- ✅ **类型识别**: 正确识别chunk_type (text: 20, image: 2, table: 1, image_context: 3)
- ✅ **数据存储**: SQLite存储父块元数据，LanceDB存储子块向量
- ✅ **向量化**: 所有子块成功向量化，embedding维度1024
- ✅ **图文关系**: MULTIVECTOR.md设计成功实现，图像描述与周围文本智能组合

### 集成测试文件
使用`/Users/dio/Downloads/AI代理的上下文工程：构建Manus的经验教训.pdf`作为测试文件

