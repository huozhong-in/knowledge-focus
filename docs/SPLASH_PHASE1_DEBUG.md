# Splash Phase 1 调试报告

## 🐛 问题描述（第一轮测试）

**现象**：
- 启动过程停在"API服务器启动成功"界面
- 展开日志能看到 FastAPI 已启动
- 终端测试 API 是成功的（说明 API 确实就绪了）
- **但是没有切换到模型下载界面**
- base_dir 中没有模型文件（模型确实没下载）

**用户怀疑**：前端没有拿到"API是否成功"的判定

---

## 🔍 根本原因分析

### Bug #1: 权限检查死锁 ⚠️⚠️⚠️

**文件**: `tauri-app/src/splash.tsx:267-310`

**问题代码**:
```tsx
// API就绪后检查和下载模型
useEffect(() => {
  if (!hasFullDiskAccess || !isApiReady) {  // ❌ 死锁条件
    if (!hasFullDiskAccess) {
      setLoading(false);
    }
    return;
  }
  
  const initializeBuiltinModel = async () => {
    // ... 模型下载逻辑
  };
  
  initializeBuiltinModel();
}, [isApiReady, hasFullDiskAccess, selectedMirror]);
```

**问题分析**:

1. **Phase 1 设计意图**：权限检查应该在模型下载**之后**
   ```
   API就绪 → 模型检查/下载 → 权限检查 → 后端扫描
   ```

2. **实际代码逻辑**：权限检查成为了模型下载的**前置条件**
   ```
   API就绪 → (等待权限) → 模型下载 ❌
   ```

3. **死锁发生**：
   - 初始化时：`hasFullDiskAccess = false`（我们移除了启动时的权限检查）
   - API 就绪后：触发 `useEffect`
   - 条件判断：`!hasFullDiskAccess` 为 `true`
   - 结果：直接 `return`，模型下载代码永远不执行
   - 权限检查：因为模型没下载完，永远不会触发

**修复方案**:
```tsx
// API就绪后检查和下载模型（无需等待权限）✅
useEffect(() => {
  if (!isApiReady) {  // 只检查 API 是否就绪
    return;
  }
  
  const initializeBuiltinModel = async () => {
    // ... 模型下载逻辑
  };
  
  initializeBuiltinModel();
}, [isApiReady, selectedMirror]); // 移除 hasFullDiskAccess 依赖
```

---

## ✅ 已应用的修复

### 1. 移除权限前置条件

**变更**:
- 从依赖数组中移除 `hasFullDiskAccess`
- 从条件判断中移除 `!hasFullDiskAccess`
- 只保留 `!isApiReady` 检查

**效果**:
- API 就绪后立即开始模型检查/下载
- 无需等待权限检查
- 符合 Phase 1 设计：权限延后

### 2. 添加详细调试日志

**位置 1**: 模型初始化 useEffect
```tsx
console.log(`[Splash] API就绪状态变化: isApiReady=${isApiReady}`);
console.log('[Splash] API已就绪，开始初始化内置模型');
console.log(`[Splash] 调用模型初始化API，镜像: ${selectedMirror}`);
console.log('[Splash] 模型初始化API响应:', result);
```

**位置 2**: 模型就绪 useEffect
```tsx
console.log(`[Splash] 模型状态变化: modelStage=${modelStage}, isApiReady=${isApiReady}`);
console.log('[Splash] 模型已就绪，开始权限检查和后端扫描');
```

**用途**:
- 追踪 `isApiReady` 状态变化
- 确认模型初始化 API 是否被调用
- 查看 API 响应内容
- 追踪模型状态机转换

---

## 🧪 第二轮测试指南

### 测试步骤

1. **清理环境**（可选，如果想测试首次下载）:
   ```bash
   # 删除模型文件
   rm -rf ~/Library/Application\ Support/knowledge-focus.huozhong.in/mlx-vlm
   ```

2. **启动应用**:
   ```bash
   cd tauri-app
   ./dev.sh
   ```

3. **观察控制台日志**（重点关注）:
   ```
   [Splash] API就绪状态变化: isApiReady=true
   [Splash] API已就绪，开始初始化内置模型
   [Splash] 调用模型初始化API，镜像: huggingface
   [Splash] 模型初始化API响应: {status: "downloading", ...}
   [Splash] 开始下载模型...
   ```

4. **观察 Splash 界面**:
   - ✅ 应该看到 "Checking builtin model..." 消息
   - ✅ 应该看到 "Downloading builtin model..." 消息
   - ✅ 应该看到进度条（0% → 100%）
   - ✅ 应该看到当前镜像提示文字

5. **验证模型下载**:
   ```bash
   ls -la ~/Library/Application\ Support/knowledge-focus.huozhong.in/mlx-vlm/
   ```
   应该能看到模型文件（几个GB）

### 预期日志流程

```
# Phase 1: App 启动
App.tsx: Performing backup health check...
[Splash] API就绪状态变化: isApiReady=false
[Splash] API未就绪，等待中...

# Phase 2: API 就绪
App.tsx: API is ready. (健康检查成功)
或
App.tsx: Received 'api-ready' event from backend. (事件触发)

# Phase 3: 模型检查/下载
[Splash] API就绪状态变化: isApiReady=true
[Splash] API已就绪，开始初始化内置模型
[Splash] 调用模型初始化API，镜像: huggingface
[Splash] 模型初始化API响应: {status: "downloading", message: "..."}
[Splash] 开始下载模型...

# Phase 4: 下载进度（bridge events）
model-download-progress: {progress: 5, message: "Downloading..."}
model-download-progress: {progress: 15, message: "..."}
...

# Phase 5: 下载完成
model-download-completed
[Splash] 模型状态变化: modelStage=ready, isApiReady=true
[Splash] 模型已就绪，开始权限检查和后端扫描

# Phase 6: 权限检查
Checking disk access permission...

# Phase 7: 进入主界面
```

---

## 🔧 如果还有问题

### 问题 A: 日志中没有 `[Splash] API已就绪`

**原因**: `isApiReady` 可能没有正确更新

**排查步骤**:
1. 检查是否有 `App.tsx: API is ready.` 或 `api-ready event` 日志
2. 检查 `useAppStore` 的 `setApiReady` 是否被调用
3. 检查 Splash 组件是否正确订阅了 store

**临时解决方案**:
```tsx
// 在 Splash 组件中添加
useEffect(() => {
  console.log('[Splash] 组件挂载，isApiReady:', isApiReady);
}, []);
```

### 问题 B: API 响应了但 status 不是 'downloading'

**可能的响应**:
- `{status: "ready"}`: 模型已存在，不需要下载
- `{status: "error", message: "..."}`: 初始化失败

**排查步骤**:
1. 查看 `[Splash] 模型初始化API响应:` 的完整内容
2. 检查 `base_dir` 目录权限
3. 手动测试 API:
   ```bash
   curl -X POST http://127.0.0.1:60315/models/builtin/initialize \
     -H "Content-Type: application/json" \
     -d '{"mirror": "huggingface"}'
   ```

### 问题 C: 调用了 API 但没有响应日志

**原因**: fetch 可能失败或超时

**排查步骤**:
1. 检查是否有 `[Splash] 初始化内置模型失败:` 错误日志
2. 检查网络连接
3. 确认 API 端口 60315 是否正确

---

## 📊 修复对比

| 维度 | Bug 版本 | 修复版本 |
|------|---------|---------|
| 权限检查条件 | `!hasFullDiskAccess \|\| !isApiReady` | `!isApiReady` |
| 依赖数组 | `[isApiReady, hasFullDiskAccess, ...]` | `[isApiReady, ...]` |
| 流程顺序 | ❌ 权限 → 模型 | ✅ 模型 → 权限 |
| 启动死锁 | ⚠️ 会死锁 | ✅ 无死锁 |
| 调试日志 | ❌ 无 | ✅ 详细日志 |

---

## 💡 经验教训

1. **条件依赖要仔细审查**：重构流程时要检查所有相关的条件判断
2. **useEffect 依赖要精确**：不相关的依赖会导致意外行为
3. **调试日志很重要**：关键状态变化都应该有日志输出
4. **测试要覆盖首次启动**：权限和模型下载只在首次启动时触发

---

## 🎯 下一步

修复完成后，如果第二轮测试通过：
1. 可以继续 Phase 2（超时检测等）
2. 或者移除调试日志，清理代码
3. 或者进行其他任务（智能卸载、测试等）
