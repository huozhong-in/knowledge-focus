# Splash 模型下载集成测试指南

## 测试前准备

### 1. 清理环境（模拟首次安装）

```bash
# 删除数据库
rm ~/Library/Application\ Support/knowledge-focus.huozhong.in/knowledge-focus.db

# 删除已下载的模型
rm -rf ~/Library/Application\ Support/knowledge-focus.huozhong.in/builtin_models/

# 确认清理成功
ls ~/Library/Application\ Support/knowledge-focus.huozhong.in/
```

### 2. 启动开发环境

```bash
cd /Users/dio/workspace/knowledge-focus/tauri-app
./dev.sh
```

## 测试场景

### 场景 1: 首次启动（正常流程） ✅

**预期行为**:
1. 显示 "Checking permissions..."
2. 权限通过后显示 "Permission verified"
3. API 启动日志滚动显示（Python 环境同步、依赖下载等）
4. API 就绪后显示 "Checking builtin model..."
5. 检测到模型未下载，显示 "Downloading builtin model..."
6. 显示下载进度条（0% → 100%）
7. 进度条下方显示镜像选择器（默认 HuggingFace）
8. 下载完成后显示 "Model ready, starting backend scan..."
9. 后端扫描启动后自动进入主界面

**验证点**:
- [ ] 进度条平滑更新（每秒更新一次）
- [ ] 进度百分比正确显示
- [ ] 下载消息显示文件大小和速度信息
- [ ] 无法跳过模型下载阶段
- [ ] 整个流程无错误

### 场景 2: 模型已存在（快速启动） ✅

**准备**: 保持模型文件不删除，只重启 App

**预期行为**:
1. 权限检查 → API 启动
2. 检查模型时立即返回 "Model ready"
3. 直接进入后端扫描
4. 不显示下载进度条
5. 快速进入主界面

**验证点**:
- [ ] 无下载阶段
- [ ] 启动速度快（3-5秒内进入主界面）
- [ ] 无多余的 UI 闪烁

### 场景 3: 下载失败 + 镜像切换 ❌

**模拟方法**: 
```bash
# 方法1: 断网测试（开飞行模式）
# 方法2: 修改 models_builtin.py 强制失败

# 在 download_model_async() 中临时添加:
async def download_model_async(...):
    # 模拟失败
    emit_bridge_event("model-download-failed", {"error": "Network timeout"})
    return
```

**预期行为**:
1. 下载进度到某个百分比后停止
2. 显示红色错误面板：
   - "Failed to download builtin model"
   - 错误消息（如 "Network timeout"）
   - 镜像选择下拉框
   - "Retry Download" 按钮
3. 切换镜像到 "HF-Mirror (China)"
4. 点击 "Retry Download" 重新开始

**验证点**:
- [ ] 错误信息清晰
- [ ] 可以切换镜像
- [ ] 重试按钮可用
- [ ] 重试后重新开始下载流程

### 场景 4: 下载中切换镜像 🔄

**操作**:
1. 开始下载（使用 HuggingFace）
2. 下载到 20% 时，手动切换镜像到 HF-Mirror
3. 观察行为

**当前实现限制**:
- 切换镜像会触发新的初始化请求
- 可能导致重复下载
- **建议**: 仅在下载失败时切换镜像

**改进方案**（可选）:
```tsx
// 在下载中禁用镜像选择
<select 
  disabled={modelStage === 'downloading'}
  value={selectedMirror}
  ...
>
```

## Bridge Events 验证

### 检查事件是否正确触发

在浏览器控制台或 Tauri DevTools 中添加监听：

```tsx
// 临时添加到 splash.tsx 的事件监听中
modelProgressUnlisten = await listen<{progress: number, message?: string}>('model-download-progress', (event) => {
  console.log('📊 Progress:', event.payload);
  setDownloadProgress(event.payload.progress);
  if (event.payload.message) {
    setDownloadMessage(event.payload.message);
  }
});

modelCompletedUnlisten = await listen('model-download-completed', () => {
  console.log('✅ Download completed');
  setModelStage('ready');
});

modelFailedUnlisten = await listen<{error: string}>('model-download-failed', (event) => {
  console.error('❌ Download failed:', event.payload.error);
  setModelStage('error');
});
```

### 验证节流（1秒限制）

```bash
# 查看 API 日志
tail -f ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/*.log | grep "model-download"

# 应该看到进度事件间隔约 1 秒
```

## API 接口验证

### 手动测试初始化接口

```bash
# 检查模型状态
curl http://127.0.0.1:60315/models/builtin/download-status

# 预期响应（未下载）:
# {"success": true, "downloaded": false, "model_path": null}

# 预期响应（已下载）:
# {"success": true, "downloaded": true, "model_path": "/path/to/model"}

# 触发初始化（HuggingFace）
curl -X POST http://127.0.0.1:60315/models/builtin/initialize \
  -H "Content-Type: application/json" \
  -d '{"mirror": "huggingface"}'

# 预期响应（模型已存在）:
# {"status": "ready", "model_path": "...", "message": "Model already downloaded"}

# 预期响应（开始下载）:
# {"status": "downloading", "progress": 0, "message": "Download started using huggingface"}

# 触发初始化（HF-Mirror）
curl -X POST http://127.0.0.1:60315/models/builtin/initialize \
  -H "Content-Type: application/json" \
  -d '{"mirror": "hf-mirror"}'
```

## 常见问题排查

### 问题 1: 进度条不更新

**可能原因**:
- Bridge events 未正确发送
- 前端事件监听未注册

**排查**:
```bash
# 检查 API 日志中是否有 bridge event 发送记录
grep "emit_bridge_event" ~/Library/Application\ Support/knowledge-focus.huozhong.in/logs/*.log

# 检查前端控制台是否有事件接收日志
```

### 问题 2: 下载完成后卡住不进入主界面

**可能原因**:
- `model-download-completed` 事件未触发
- `modelStage` 未正确更新为 'ready'
- `startBackendScan()` 未被调用

**排查**:
```tsx
// 在 useEffect 中添加日志
useEffect(() => {
  console.log('🔍 Model stage changed:', modelStage);
  if (modelStage === 'ready' && hasFullDiskAccess && isApiReady) {
    console.log('✅ Conditions met, starting backend scan');
    startBackendScan();
  }
}, [modelStage, hasFullDiskAccess, isApiReady]);
```

### 问题 3: 重试按钮无效

**可能原因**:
- `window.location.reload()` 被阻止

**改进方案**:
```tsx
<Button
  onClick={async () => {
    setModelStage('checking');
    setDownloadProgress(0);
    setDownloadMessage('');
    
    // 直接调用初始化函数而不是重新加载页面
    try {
      const response = await fetch('http://127.0.0.1:60315/models/builtin/initialize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mirror: selectedMirror })
      });
      const result = await response.json();
      if (result.status === 'downloading') {
        setModelStage('downloading');
      }
    } catch (error) {
      toast.error('Failed to restart download');
    }
  }}
  className="w-full bg-red-600 hover:bg-red-700 text-white"
>
  Retry Download
</Button>
```

## 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 首次下载时间 | < 10 分钟 | 取决于网络速度（2.6GB 模型） |
| 进度更新频率 | 1 次/秒 | Bridge event 节流 |
| 模型检查时间 | < 1 秒 | 已下载情况 |
| 启动到主界面 | < 5 秒 | 模型已存在时 |

## 下一步

- [ ] 运行场景 1 测试（首次启动）
- [ ] 运行场景 2 测试（模型已存在）
- [ ] 运行场景 3 测试（下载失败）
- [ ] 验证 Bridge Events 正确触发
- [ ] 检查日志是否有异常
- [ ] 确认用户体验流畅

测试通过后，可以继续：
1. 实现智能卸载逻辑
2. 清理旧代码
3. 完整的端到端测试
