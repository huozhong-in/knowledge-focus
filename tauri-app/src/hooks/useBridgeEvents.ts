import { useEffect } from 'react';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { toast } from 'sonner';

/**
 * 桥接事件监听Hook
 * 
 * 此Hook用于监听来自Python后端通过Rust桥接转发的各种事件。
 * 它提供了一个统一的方式来处理后端主动发送的通知。
 */

interface BridgeEventPayload {
  timestamp?: number;
  source?: string;
  [key: string]: any;
}

interface EventHandlers {
  'tags-updated'?: (payload: BridgeEventPayload) => void;
  'task-completed'?: (payload: BridgeEventPayload) => void;
  'file-processed'?: (payload: BridgeEventPayload) => void;
  'parsing-progress'?: (payload: BridgeEventPayload) => void;
  'screening-progress'?: (payload: BridgeEventPayload) => void;
  'model-status-changed'?: (payload: BridgeEventPayload) => void;
  'database-updated'?: (payload: BridgeEventPayload) => void;
  'error-occurred'?: (payload: BridgeEventPayload) => void;
  'system-status'?: (payload: BridgeEventPayload) => void;
  [eventName: string]: ((payload: BridgeEventPayload) => void) | undefined;
}

/**
 * 使用桥接事件监听器
 * 
 * @param handlers 事件处理器映射
 * @param options 选项配置
 */
export function useBridgeEvents(
  handlers: EventHandlers,
  options: {
    showToasts?: boolean; // 是否显示toast通知
    logEvents?: boolean;  // 是否在控制台记录事件
  } = {}
) {
  const { showToasts = false, logEvents = true } = options;

  useEffect(() => {
    const unlistenFunctions: Promise<UnlistenFn>[] = [];

    // 为每个事件类型设置监听器
    Object.entries(handlers).forEach(([eventName, handler]) => {
      if (handler) {
        const unlistenPromise = listen(eventName, (event) => {
          const payload = event.payload as BridgeEventPayload;
          
          if (logEvents) {
            console.log(`[桥接事件] ${eventName}:`, payload);
          }

          // 调用用户定义的处理器
          handler(payload);

          // 可选的toast通知
          if (showToasts) {
            showEventToast(eventName, payload);
          }
        });
        
        unlistenFunctions.push(unlistenPromise);
      }
    });

    // 清理函数
    return () => {
      Promise.all(unlistenFunctions).then(unlistenFns => {
        unlistenFns.forEach(unlisten => unlisten());
      });
    };
  }, [handlers, showToasts, logEvents]);
}

/**
 * 显示事件相关的toast通知
 */
function showEventToast(eventName: string, payload: BridgeEventPayload) {
  const { source = 'backend', timestamp, ...data } = payload;
  
  switch (eventName) {
    case 'tags-updated':
      toast.success('标签已更新', {
        description: data.description || '标签云数据已刷新'
      });
      break;
      
    case 'task-completed':
      if (data.success !== false) {
        toast.success('任务完成', {
          description: `任务 ${data.task_id || '未知'} 已完成`
        });
      } else {
        toast.error('任务失败', {
          description: `任务 ${data.task_id || '未知'} 执行失败`
        });
      }
      break;
      
    case 'file-processed':
      toast.info('文件处理完成', {
        description: data.description || `已处理: ${data.file_path || '未知文件'}`
      });
      break;
      
    case 'error-occurred':
      toast.error('系统错误', {
        description: data.message || '发生未知错误'
      });
      break;
      
    case 'system-status':
      if (data.status === 'ready') {
        toast.success('系统状态', {
          description: data.message || '系统准备就绪'
        });
      } else {
        toast.info('系统状态', {
          description: data.message || `状态: ${data.status}`
        });
      }
      break;
      
    default:
      // 对于未知事件类型，显示通用消息
      toast.info(`事件: ${eventName}`, {
        description: data.message || data.description || '收到后端事件'
      });
  }
}

/**
 * 进度事件监听Hook
 * 
 * 专门用于监听进度相关的事件
 */
export function useProgressEvents(
  onProgress: (type: string, current: number, total: number, percentage: number, message?: string) => void
) {
  useEffect(() => {
    const progressEventTypes = ['parsing-progress', 'screening-progress'];
    const unlistenFunctions: Promise<UnlistenFn>[] = [];

    progressEventTypes.forEach(eventType => {
      const unlistenPromise = listen(eventType, (event) => {
        const payload = event.payload as BridgeEventPayload & {
          current: number;
          total: number;
          percentage: number;
          message?: string;
        };
        
        onProgress(
          eventType.replace('-progress', ''),
          payload.current,
          payload.total,
          payload.percentage,
          payload.message
        );
      });
      
      unlistenFunctions.push(unlistenPromise);
    });

    return () => {
      Promise.all(unlistenFunctions).then(unlistenFns => {
        unlistenFns.forEach(unlisten => unlisten());
      });
    };
  }, [onProgress]);
}

/**
 * 简化的标签更新监听Hook
 * 
 * 专门用于监听标签更新事件的便捷Hook
 */
export function useTagsUpdateListener(onTagsUpdated: () => void) {
  useBridgeEvents({
    'tags-updated': () => {
      console.log('标签已更新，触发刷新');
      onTagsUpdated();
    }
  });
}
