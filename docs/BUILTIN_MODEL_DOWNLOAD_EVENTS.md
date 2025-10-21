# 内置模型下载进度事件集成指南

## 概述

内置模型下载功能使用**统一桥接器机制**将下载进度从 Python 后端实时推送到前端 TypeScript。这种机制通过 Rust 桥接层，利用 Tauri 的 IPC 事件系统，实现了零配置、安全的实时通信。

## 事件流程

```
Python (models_builtin.py)
  └─> BridgeEventSender (bridge_events.py)
      └─> print to stdout (JSON格式)
          └─> Rust 监听器 (event_buffer.rs)
              └─> Tauri IPC Event
                  └─> TypeScript (useBridgeEvents.ts)
                      └─> React 组件更新 UI
```

## 事件类型

### 1. `model-download-progress`

**触发时机**: 下载过程中，每秒最多触发1次（节流策略）

**Payload 结构**:
```typescript
{
  model_name: string,        // 模型显示名称，如 "Qwen3-VL-4B (3-bit)"
  current: number,           // 已下载字节数
  total: number,             // 总字节数
  percentage: number,        // 下载百分比 (0-100)
  message: string,           // 进度描述信息
  stage: string,             // 阶段: "starting" | "connecting" | "downloading"
  timestamp: number,         // Unix 时间戳
  source: "models_builtin"   // 事件来源
}
```

**示例**:
```json
{
  "model_name": "Qwen3-VL-4B (3-bit)",
  "current": 1342177280,
  "total": 2684354560,
  "percentage": 50.0,
  "message": "正在下载 model.safetensors: 50%",
  "stage": "downloading",
  "timestamp": 1729152345.678,
  "source": "models_builtin"
}
```

### 2. `model-download-completed`

**触发时机**: 模型下载完成时（立即转发策略）

**Payload 结构**:
```typescript
{
  model_name: string,        // 模型显示名称
  local_path: string,        // 本地存储路径
  message: string,           // 完成消息
  timestamp: number,
  source: "models_builtin"
}
```

**示例**:
```json
{
  "model_name": "Qwen3-VL-4B (3-bit)",
  "local_path": "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/builtin_models/models--mlx-community--Qwen3-VL-4B-Instruct-3bit/snapshots/abc123...",
  "message": "模型 Qwen3-VL-4B (3-bit) 下载完成",
  "timestamp": 1729152456.789,
  "source": "models_builtin"
}
```

### 3. `model-download-failed`

**触发时机**: 下载失败时（立即转发策略）

**Payload 结构**:
```typescript
{
  model_name: string,        // 模型显示名称
  error_message: string,     // 错误信息
  details: {                 // 错误详情
    last_error: string
  },
  timestamp: number,
  source: "models_builtin"
}
```

**示例**:
```json
{
  "model_name": "Qwen3-VL-4B (3-bit)",
  "error_message": "所有镜像站下载模型 qwen3-vl-4b 均失败: Connection timeout",
  "details": {
    "last_error": "Connection timeout after 60s"
  },
  "timestamp": 1729152567.890,
  "source": "models_builtin"
}
```

## Rust 端配置

在 `event_buffer.rs` 中已配置事件处理策略：

```rust
// 模型下载进度：节流处理，避免UI更新过于频繁，最多每秒1次
strategies.insert(
    "model-download-progress".to_string(),
    Throttle(Duration::from_secs(1)),
);

// 模型下载完成：立即通知用户
strategies.insert("model-download-completed".to_string(), Immediate);

// 模型下载失败：立即通知用户
strategies.insert("model-download-failed".to_string(), Immediate);
```

## 前端集成示例

### 在 Settings 页面监听下载事件

```typescript
import { useBridgeEvents } from '@/hooks/useBridgeEvents';
import { useState } from 'react';

function BuiltinModelsSection() {
  const [downloadProgress, setDownloadProgress] = useState<{
    [modelId: string]: {
      progress: number;
      message: string;
      stage: string;
    }
  }>({});
  
  // 监听下载事件
  useBridgeEvents({
    'model-download-progress': (payload) => {
      const { model_name, percentage, message, stage } = payload;
      
      // 更新进度状态
      setDownloadProgress(prev => ({
        ...prev,
        [model_name]: {
          progress: percentage,
          message,
          stage
        }
      }));
    },
    
    'model-download-completed': (payload) => {
      const { model_name, message } = payload;
      
      // 清除进度状态
      setDownloadProgress(prev => {
        const updated = { ...prev };
        delete updated[model_name];
        return updated;
      });
      
      // 刷新模型列表
      refreshModelList();
      
      // Toast 会自动显示（如果 showToasts=true）
      console.log('✅ 下载完成:', message);
    },
    
    'model-download-failed': (payload) => {
      const { model_name, error_message } = payload;
      
      // 清除进度状态
      setDownloadProgress(prev => {
        const updated = { ...prev };
        delete updated[model_name];
        return updated;
      });
      
      // Toast 会自动显示错误
      console.error('❌ 下载失败:', error_message);
    }
  }, { 
    showToasts: true,  // 启用自动 Toast 通知
    logEvents: true    // 启用控制台日志
  });
  
  return (
    <div>
      {/* 模型列表和下载按钮 */}
      {models.map(model => (
        <ModelCard
          key={model.model_id}
          model={model}
          downloadProgress={downloadProgress[model.display_name]}
          onDownload={() => handleDownloadModel(model.model_id)}
        />
      ))}
    </div>
  );
}
```

### 带进度条的模型卡片组件

```typescript
interface ModelCardProps {
  model: {
    model_id: string;
    display_name: string;
    size_mb: number;
    downloaded: boolean;
  };
  downloadProgress?: {
    progress: number;
    message: string;
    stage: string;
  };
  onDownload: () => void;
}

function ModelCard({ model, downloadProgress, onDownload }: ModelCardProps) {
  const isDownloading = !!downloadProgress;
  
  return (
    <div className="border rounded-lg p-4">
      <h3>{model.display_name}</h3>
      <p>大小: {model.size_mb} MB</p>
      
      {/* 下载进度条 */}
      {isDownloading && (
        <div className="mt-2">
          <div className="flex justify-between text-sm mb-1">
            <span>{downloadProgress.message}</span>
            <span>{downloadProgress.progress.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all"
              style={{ width: `${downloadProgress.progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            阶段: {downloadProgress.stage}
          </p>
        </div>
      )}
      
      {/* 下载按钮 */}
      {!model.downloaded && !isDownloading && (
        <button onClick={onDownload}>
          下载模型
        </button>
      )}
      
      {/* 已下载状态 */}
      {model.downloaded && !isDownloading && (
        <span className="text-green-600">✓ 已下载</span>
      )}
    </div>
  );
}
```

### 触发下载

```typescript
async function handleDownloadModel(modelId: string) {
  try {
    const response = await fetch(
      `http://127.0.0.1:60315/models/builtin/${modelId}/download`,
      { method: 'POST' }
    );
    
    const data = await response.json();
    
    if (data.success) {
      toast.info('开始下载', {
        description: `模型 ${modelId} 开始下载，请等待...`
      });
      // 进度更新会通过 bridge events 自动推送
    } else {
      toast.error('启动下载失败', {
        description: data.message
      });
    }
  } catch (error) {
    toast.error('请求失败', {
      description: String(error)
    });
  }
}
```

## Toast 通知行为

如果在 `useBridgeEvents` 中启用 `showToasts: true`，会自动显示：

- **进度事件** (model-download-progress): 仅在特殊阶段（starting, connecting）显示简短提示，避免频繁弹出
- **完成事件** (model-download-completed): 显示成功 Toast，持续 4 秒
- **失败事件** (model-download-failed): 显示错误 Toast，持续 6 秒

## 最佳实践

1. **UI 组件自己管理进度条**: `model-download-progress` 不应弹 Toast，而是更新组件内的进度条状态
2. **重要事件才弹 Toast**: 完成和失败事件需要用户明确知道，应该弹 Toast
3. **避免重复监听**: 在顶层组件（如 Settings 页面）监听一次即可，不要在每个子组件都监听
4. **清理状态**: 下载完成或失败后，及时清除进度状态，刷新模型列表

## 调试建议

1. **检查 Rust 日志**: 查看事件是否被正确转发
   ```
   ⚡ 立即转发事件: model-download-completed
   ⏱️  节流处理事件: model-download-progress (1秒间隔)
   ```

2. **检查前端控制台**: 启用 `logEvents: true` 查看事件接收情况
   ```
   [桥接事件] model-download-progress: { model_name: "...", percentage: 50, ... }
   ```

3. **检查 Python 日志**: 确认事件是否被发送到 stdout
   ```
   BRIDGE_EVENT: {"event": "model-download-progress", "payload": {...}}
   ```

## 相关文件

- **Python**: `api/models_builtin.py` - 下载逻辑和事件发送
- **Python**: `api/bridge_events.py` - 桥接事件发送器
- **Rust**: `tauri-app/src-tauri/src/event_buffer.rs` - 事件接收和转发
- **TypeScript**: `tauri-app/src/hooks/useBridgeEvents.ts` - 前端事件监听 Hook
- **前端**: `tauri-app/src/App.tsx` - 全局事件监听示例
