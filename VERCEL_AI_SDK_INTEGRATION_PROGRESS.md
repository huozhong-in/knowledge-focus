# Vercel AI SDK v5 聊天界面集成 - 进度跟踪文档

> **项目目标**：基于产品设计文档(PRD.md)，实现聊天界面与Vercel AI SDK v5的深度集成，建立完整的对话状态管理和会话持久化系统。

## 🏗️ 整体技术架构

```text
前端TypeScript + AI SDK v5 ← Tauri IPC → Rust Bridge ← HTTP → Python FastAPI
    ↓                                                                ↓
自定义Transport(Tauri HTTP)                                    SSE兼容流式响应
    ↓                                                                ↓  
UIMessage状态管理                                               UIMessage生成
    ↓                                                                ↓
会话持久化存储                                               消息数据库存储
    ↓                                                                ↓
智能上下文管理                                               动态token截断
```

## 🎯 核心设计原则

### 数据流和状态管理
- **UIMessage格式**：前端状态管理和持久化的唯一数据源
- **会话隔离**：每个会话独立的pin文件列表和聊天记录
- **动态上下文**：根据token限制智能截断历史消息
- **智能降级**：在线模型 → 本地模型的无缝降级策略

### 用户体验原则
- **流式加载**：聊天记录分页加载，最近30条优先显示
- **状态感知**：用户能清楚感知当前使用的模型类型（在线/本地）
- **无缝切换**：会话切换时完整恢复pin文件列表和聊天上下文
- **渐进增强**：先实现基础功能，为RAG集成预留扩展空间

---

## 🎯 第一阶段：技术验证与环境适配（P0 - 必须完成）

**目标**：验证Vercel AI SDK v5在Tauri环境中的可行性，解决核心技术风险

### 1.1 环境适配验证（风险1解决）

- [x] **1.1.1 AI SDK v5安装和基础配置**
  - [x] 在tauri-app中安装`ai@beta`、`@ai-sdk/react@beta`包
  - [x] 创建基础的useChat配置demo，验证TypeScript类型
  - [x] 测试AI SDK v5的基础功能（UIMessage、Transport等）
  - [x] 在AppWorkspace中添加开发模式测试入口，可通过按钮切换到AI SDK测试模式

- [x] **1.1.2 自定义Transport实现**
  - [x] 创建`src/lib/tauri-http-transport.ts`：基于标准fetch API的Transport
  - [x] 实现SSE流式响应的解析和处理逻辑
  - [x] 处理错误、重试等网络异常情况
  - [x] 实现ChatTransport接口要求的sendMessages/reconnectToStream方法
  - [x] 更新演示组件以使用自定义Transport，通过TauriHttpTransport进行测试

- [x] **1.1.3 基础连通性测试**
  - [x] ✅ **重大突破** - 端到端集成成功！
  - [x] 创建并测试`/chat/ui-stream`端点，完美支持AI SDK v5格式
  - [x] 验证LM Studio + gemma-3n-e4b-it模型正确响应
  - [x] 确认SSE流式响应格式完全符合AI SDK v5规范
  - [x] 测试结果：前端Transport → 后端SSE → 模型响应 → 流式文本显示 ✅

### 1.2 后端SSE兼容改造（风险2解决）

- [x] **1.2.1 FastAPI SSE端点创建**
  - [x] 在`models_api.py`中创建`/chat/ui-stream`端点
  - [x] 支持AI SDK v5的UIMessage格式解析
  - [x] 实现SSE (Server-Sent Events) 流式响应
  - [x] 设置正确的CORS头和Cache-Control策略
  - [x] 集成系统配置的模型选择（LM Studio + gemma-3n-e4b-it）

### 1.3 端到端集成测试

- [x] **1.3.1 Backend SSE流式验证**
  - [x] 修复litellm异步迭代器兼容性问题（CustomStreamWrapper错误）
  - [x] 修复JSON变量作用域冲突问题
  - [x] 验证LM Studio模型(gemma-3n-e4b-it)正确响应
  - [x] 确认SSE事件格式符合AI SDK v5规范（message-start、text-delta、message-end）
  
- [ ] **1.3.2 Frontend Transport集成测试**
  - [ ] 在AI SDK Demo组件中测试端到端聊天流
  - [ ] 验证TauriHttpTransport正确解析SSE流
  - [ ] 确认useChat hook状态更新正常
  - [ ] 测试错误处理和重连机制

---

## 🗄️ 第二阶段：数据库设计与API完善（P1 - 重要功能）

**目标**：建立完整的对话状态管理和会话持久化系统

### 2.1 数据库架构设计

- [ ] **2.1.1 会话管理表设计**
  ```sql
  -- 聊天会话表
  CREATE TABLE chat_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,                    -- 会话名称
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      metadata JSON,                         -- 会话元数据：{"topic": "...", "file_count": 3, "message_count": 15}
      is_active BOOLEAN DEFAULT TRUE         -- 软删除标记
  );
  ```

- [ ] **2.1.2 消息存储表设计**
  ```sql
  -- 聊天消息表（UIMessage格式）
  CREATE TABLE chat_messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id INTEGER REFERENCES chat_sessions(id),
      message_id TEXT UNIQUE NOT NULL,      -- UI层的消息ID
      role TEXT NOT NULL,                   -- 'user' | 'assistant' | 'system'
      content TEXT,                         -- 主要文本内容
      parts JSON,                          -- UIMessage.parts数组
      metadata JSON,                       -- 消息元数据（model_id、timestamp、token_usage等）
      sources JSON,                        -- 预留：RAG来源信息
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX(session_id, created_at)        -- 查询优化
  );
  ```

- [ ] **2.1.3 会话文件关联表设计**
  ```sql
  -- 会话Pin文件表（会话级隔离）
  CREATE TABLE session_pinned_files (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id INTEGER REFERENCES chat_sessions(id),
      file_path TEXT NOT NULL,             -- 文件绝对路径
      file_name TEXT NOT NULL,             -- 显示用文件名
      pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      metadata JSON,                       -- 文件元数据：大小、类型、向量化状态等
      UNIQUE(session_id, file_path)        -- 同一会话中文件唯一
  );
  ```

### 2.2 会话管理API开发

- [ ] **2.2.1 会话CRUD端点**
  - [ ] `POST /chat/sessions` - 创建新会话（自动生成智能名称）
  - [ ] `GET /chat/sessions` - 获取会话列表（支持分页和搜索）
  - [ ] `PUT /chat/sessions/{id}` - 更新会话信息（重命名等）
  - [ ] `DELETE /chat/sessions/{id}` - 软删除会话

- [ ] **2.2.2 消息持久化端点**
  - [ ] `GET /chat/sessions/{id}/messages` - 获取会话消息（支持分页、最近30条优先）
  - [ ] `POST /chat/sessions/{id}/messages` - 批量保存消息
  - [ ] 在`/chat/ui-stream`端点中集成自动消息保存逻辑

- [ ] **2.2.3 会话文件管理端点**
  - [ ] `GET /chat/sessions/{id}/pinned-files` - 获取会话Pin文件列表
  - [ ] `POST /chat/sessions/{id}/pin-file` - 为会话Pin文件
  - [ ] `DELETE /chat/sessions/{id}/pinned-files/{file_id}` - 取消Pin文件
  - [ ] 文件状态变更的实时同步机制

### 2.3 智能上下文管理实现

- [ ] **2.3.1 动态上下文截断机制**
  - [ ] 实现基于token限制的智能消息截断算法
  - [ ] 优先级策略：`系统prompt > 最新消息 > pin文件context > 历史消息`
  - [ ] 支持不同模型的不同上下文窗口大小

- [ ] **2.3.2 会话状态恢复机制**
  - [ ] 实现UIMessage数组的高效序列化/反序列化
  - [ ] 会话切换时的状态恢复：pin文件列表 + 聊天记录
  - [ ] 处理大会话的性能优化：增量加载、虚拟滚动

---

## 🎨 第三阶段：前端UI完善与用户体验（P2 - 体验优化）

**目标**：完善聊天界面的交互体验和视觉设计

### 3.1 Chat组件重构与集成

- [ ] **3.1.1 基于AI SDK v5的Chat组件**
  - [ ] 使用新的useChat hook重构现有聊天界面
  - [ ] 实现类型安全的消息渲染逻辑（文本、工具调用、数据部分）
  - [ ] 集成自定义TauriHttpTransport和状态管理

- [ ] **3.1.2 会话管理UI**
  - [ ] 实现会话列表侧边栏（类似ChatGPT体验）
  - [ ] 会话创建、重命名、删除的用户交互
  - [ ] 会话切换时的平滑过渡和状态恢复

- [ ] **3.1.3 Pin文件管理UI集成**
  - [ ] 在聊天界面显示当前会话的Pin文件列表
  - [ ] 文件Pin/UnPin的快捷操作
  - [ ] 文件向量化状态的可视化反馈

### 3.2 用户体验优化

- [ ] **3.2.1 智能状态指示**
  - [ ] 模型状态指示器：在线模型 vs 本地模型
  - [ ] 网络状态监控和降级提示
  - [ ] 消息发送状态：发送中、已送达、失败重试

- [ ] **3.2.2 交互体验增强**
  - [ ] 消息操作：复制、重新生成、编辑、删除
  - [ ] 聊天记录的无限滚动和性能优化
  - [ ] 快捷键支持：发送、换行、切换会话等

---

## 📊 里程碑和验收标准

### 第一阶段完成标准（技术验证）
- ✅ **环境适配成功**：在Tauri环境中AI SDK v5正常工作，无类型错误
- ✅ **网络连通性**：自定义Transport稳定工作，支持SSE流式响应
- ✅ **基础对话**：用户发送消息 → 模型响应 → 实时显示，完整链路通畅
- ✅ **降级机制**：网络中断时能自动降级到本地模型

### 第二阶段完成标准（功能完整）
- ✅ **会话管理**：创建、切换、删除会话功能完整可用
- ✅ **状态恢复**：会话切换时Pin文件列表和聊天记录正确恢复
- ✅ **智能上下文**：动态token截断机制正常工作，对话连贯性良好
- ✅ **数据持久化**：所有聊天数据安全保存，应用重启后完整恢复

### 第三阶段完成标准（用户体验）
- ✅ **界面流畅**：聊天界面响应迅速，交互逻辑清晰直观
- ✅ **状态感知**：用户能清楚了解当前使用的模型和网络状态
- ✅ **错误处理**：各种异常场景都有合理的用户提示和恢复机制

---

## 🔧 技术实现要点

### 关键技术选择
- **前端框架**：React + TypeScript + Vercel AI SDK v5
- **状态管理**：AI SDK内置状态 + 自定义Transport
- **网络层**：Tauri HTTP API + SSE协议
- **后端框架**：FastAPI + sse-starlette
- **数据库**：SQLite（轻量级、本地化）
- **消息格式**：UIMessage（AI SDK v5标准）

### 性能优化策略
- **消息分页**：虚拟滚动 + 增量加载
- **上下文管理**：智能截断 + 优先级排序
- **缓存策略**：会话列表 + 消息历史本地缓存
- **网络优化**：请求去重 + 连接复用

### 扩展性考虑
- **RAG集成预留**：消息表sources字段，支持未来检索来源记录
- **多模态支持**：UIMessage parts结构支持文本、图像、工具调用等
- **插件机制**：Transport层可扩展，支持不同协议和提供商
- **国际化准备**：用户界面文本外部化，支持多语言

---

## 🎯 下一步行动

1. **确认技术方案**：Review本文档，确保所有设计决策符合产品需求
2. **环境准备**：安装必要依赖，配置开发环境
3. **开始第一阶段**：从环境适配验证开始，逐步推进
4. **定期Review**：每个阶段完成后评估进度，调整后续计划

> **注意**：本文档将随着开发进展持续更新，记录实际实现中的发现和调整。所有设计决策都基于当前需求，支持未来的渐进式增强。
