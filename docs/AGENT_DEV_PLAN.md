# Agent 功能开发与集成计划

> **项目目标**：基于我### 阶段 2：工具化与 API 建设

- [x] **3. `tools` 模块代码组织**
  - [x] **核心任务**: 创建 `api/tools/` 目录结构，并迁移或创建初始工具代码。
  - [x] 将"共读PDF"工具集代码迁移到 `tools/co_reading.py`。
  - [x] 创建一个简单的通用工具（如 `calculator.py`）放入 `tools/` 用于测试。
  - [x] **工具通道机制**: 实现了Python后端与TypeScript前端的工具调用通道，解决了跨平台工具执行问题。

- [x] **4. `ToolProvider` 服务与 API 端点**
  - [x] **核心任务**: 实现工具的动态加载服务及前端获取工具清单的 API。
  - [x] 创建 `tool_provider.py` 并实现 `ToolProvider` 类及其 `get_tools_for_session` 方法。
  - [x] 创建 `unified_tools_api.py` 整合了工具直接调用、工具通道响应和工具列表获取的API端点。
  - [x] 在 `main.py` 中注册新的 API 路由。
  - [x] **扩展实现**: 不仅支持基于场景的预置工具，还实现了工具通道机制，支持前端工具执行。ydantic AI 作为后端 Agent 框架，与 Vercel AI SDK 驱动的前端 UI 深度集成。实现一个支持动态工具集、特定场景模式和完整生命周期管理的智能对话系统。

---

## 实施步骤与进度跟踪

### ✅ 阶段 0：方案设计与规划 (已完成)

- [x] 确认了前端 Vercel AI SDK UI + 后端 Pydantic AI Core 的混合架构。
- [x] 设计了会话与工具集/场景绑定的产品交互模式。
- [x] 规划了工具的分类、代码组织、数据库存储和运行时供给策略。
- [x] 梳理并确认了下述七个核心实施步骤。

---

### 阶段 1：核心后端 - 流协议与数据库

- [x] **1. 完整实现 Vercel AI SDK UI 流协议转换**
  - [x] **核心任务**: 在 `models_api.py` 的 `/chat/agent-stream` 路由中，实现 Pydantic AI 输出到 Vercel AI SDK v5 流协议的完整转换。

- [x] **2. 数据库架构设计与实现**
  - [x] **核心任务**: 在 `api/db_mgr.py` 中定义新的数据表模型，并在 `init_db()` 中实现创建和初始数据填充。
  - [x] 定义 `Tool` 表的 SQLModel。
  - [x] 定义 `Scenario` 表的 SQLModel。
  - [x] 定义 `SessionSelectedTool` 关联表的 SQLModel。
  - [x] 扩展 `ChatSession` 表，增加 `scenario_id` 字段。
  - [x] 在 `init_db()` 中添加新表的创建逻辑。
  - [x] 在 `init_db()` 中添加 `Tool` 和 `Scenario` 的初始数据填充脚本。

---

### 阶段 2：工具化与 API 建设

- [x] **3. `tools` 模块代码组织**
  - [x] **核心任务**: 创建 `api/tools/` 目录结构，并迁移或创建初始工具代码。
  - [x] 将“共读PDF”工具集代码迁移到 `tools/co_reading.py`，并完成测试。
  - [x] 创建一个简单的通用工具（如 `calculator.py`）放入 `tools/` 用于测试。

- [x] **4. `ToolProvider` 服务与 API 端点**
  - [x] **核心任务**: 实现工具的动态加载服务及前端获取工具清单的 API。
  - [x] 创建 `unified_tools_api.py` 并定义 `GET /tools/list` 端点，在 `main.py` 中注册新的 API 路由。
  - [x] 创建 `tool_provider.py` 并实现 `ToolProvider` 类及其 `get_tools_for_session` 方法。
  - [x] **简化目标**: 初期 `/tools/list` 端点可先返回基于场景的预置工具和所有通用工具。

---

### 阶段 3：模型集成与后端测试

- [x] **5. 集成模型上下文窗口限制**
  - [x] **核心任务**: 在调用大模型前，从数据库获取并传入模型的上下文和输出Token限制。
  - [x] 在 `models_mgr.py` 或相关模块中，实现查询逻辑：`CapabilityAssignment` -> `ModelConfiguration`。
  - [x] 获取 `max_context_length` 和 `max_output_tokens` 字段。
  - [x] 上下文工程(一期)：从数据库读出历史聊天记录，根据以上限制截取后拼接到提示词中。
  - [x] 在实例化 Pydantic AI 的 `LLM` 对象时传入获取到的限制参数。

- [ ] **6. 后端集成测试 (非UI)**
  - [ ] **核心任务**: 使用 `pytest` 等工具，在无UI环境下验证后端数据流和核心逻辑。
  - [x] **API 测试**: 编写测试用例请求 `/tools/list` 端点，验证返回的 JSON 结构。
  - [x] **服务测试**: 单元测试 `ToolProvider`，验证其能否为不同会话正确组装工具对象列表。
  - [x] **关键流程测试**: 编写集成测试，模拟调用 `/chat/agent-stream`，验证包含工具调用的完整流式响应是否正确。

---

### 阶段 4：前端改造与端到端测试

- [ ] **7. 前端改造与端到端测试**
  - [x] **核心任务**: 使用 `AI Elements` 或 `useChat` hook 改造前端界面，并完成与后端的完整对接测试。
  - [x] **组件替换**: 使用 Vercel AI SDK 的 `<Chat />` 组件或 `useChat` hook 重构聊天界面。
  - [x] **API 对接**: 将 `useChat` 的 `api` 参数或自定义的 `fetch` 调用指向后端的 `/chat/agent-stream` 端点。
  - [ ] **工具UI**: 根据 `/tools/list` 端点返回的数据，渲染可区分“预置”和“可选”的工具选择界面。
  - [ ] **端到端测试**: 验证从前端勾选工具 -> 后端Agent使用 -> 前端流式展示结果的完整链路。
