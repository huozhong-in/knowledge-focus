import { useEffect, useRef } from 'react';
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
  'model-validation-failed'?: (payload: BridgeEventPayload) => void;
  'database-updated'?: (payload: BridgeEventPayload) => void;
  'error-occurred'?: (payload: BridgeEventPayload) => void;
  'system-status'?: (payload: BridgeEventPayload) => void;
  'api-ready'?: (payload: BridgeEventPayload) => void;
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
  
  // 使用 ref 来保持最新的 handlers 引用，避免频繁重建监听器
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    // 存储取消监听函数的数组
    const unlistenFunctions: UnlistenFn[] = [];
    let isMounted = true;
    let setupComplete = false;

    // 异步设置监听器
    const setupListeners = async () => {
      try {
        for (const [eventName] of Object.entries(handlersRef.current)) {
          if (isMounted) {
            try {
              const unlisten = await listen(eventName, (event) => {
                if (!isMounted) return; // 组件已卸载，忽略事件
                
                const payload = event.payload as BridgeEventPayload;
                
                // 获取最新的 handler
                const currentHandler = handlersRef.current[eventName];
                if (!currentHandler) return;
                
                if (logEvents) {
                  console.log(`[桥接事件] ${eventName}:`, payload);
                }

                // 调用用户定义的处理器
                try {
                  currentHandler(payload);
                } catch (error) {
                  console.error(`处理桥接事件 ${eventName} 时出错:`, error);
                }

                // 可选的toast通知
                if (showToasts) {
                  try {
                    showEventToast(eventName, payload);
                  } catch (error) {
                    console.error(`显示事件toast时出错:`, error);
                  }
                }
              });
              
              if (isMounted) {
                unlistenFunctions.push(unlisten);
              } else {
                // 如果组件已经卸载，立即清理这个监听器
                try {
                  if (typeof unlisten === 'function') {
                    unlisten();
                  }
                } catch (error) {
                  console.warn('清理单个监听器失败:', error);
                }
              }
            } catch (error) {
              console.error(`设置事件监听器 ${eventName} 失败:`, error);
              // 继续设置其他监听器
            }
          }
        }
        setupComplete = true;
      } catch (error) {
        console.error('设置桥接事件监听器失败:', error);
      }
    };

    setupListeners();

    // 清理函数
    return () => {
      isMounted = false;
      
      // 等待setup完成后再清理，避免竞争条件
      const cleanup = () => {
        unlistenFunctions.forEach((unlisten, index) => {
          try {
            if (typeof unlisten === 'function') {
              unlisten();
            }
          } catch (error) {
            console.error(`清理桥接事件监听器 ${index} 失败:`, error);
            // 继续清理其他监听器，不要因为一个失败就停止
          }
        });
      };

      if (setupComplete) {
        cleanup();
      } else {
        // 如果setup还没完成，等待一下再清理
        setTimeout(cleanup, 100);
      }
    };
  }, [showToasts, logEvents]); // 移除 handlers 依赖，避免频繁重建
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
  const onProgressRef = useRef(onProgress);
  onProgressRef.current = onProgress;

  useEffect(() => {
    const progressEventTypes = ['parsing-progress', 'screening-progress'];
    const unlistenFunctions: UnlistenFn[] = [];
    let isMounted = true;

    const setupListeners = async () => {
      try {
        for (const eventType of progressEventTypes) {
          if (isMounted) {
            const unlisten = await listen(eventType, (event) => {
              if (!isMounted) return;
              
              const payload = event.payload as BridgeEventPayload & {
                current: number;
                total: number;
                percentage: number;
                message?: string;
              };
              
              onProgressRef.current(
                eventType.replace('-progress', ''),
                payload.current,
                payload.total,
                payload.percentage,
                payload.message
              );
            });
            
            if (isMounted) {
              unlistenFunctions.push(unlisten);
            } else {
              unlisten();
            }
          }
        }
      } catch (error) {
        console.error('设置进度事件监听器失败:', error);
      }
    };

    setupListeners();

    return () => {
      isMounted = false;
      unlistenFunctions.forEach(unlisten => {
        try {
          unlisten();
        } catch (error) {
          console.error('清理进度事件监听器失败:', error);
        }
      });
    };
  }, []); // 移除 onProgress 依赖
}

/**
 * 简化的标签更新监听Hook
 * 
 * 专门用于监听标签更新事件的便捷Hook
 * 
 * @param onTagsUpdated 标签更新时的回调函数
 * @param options 配置选项
 */
export function useTagsUpdateListener(
  onTagsUpdated: () => void,
  options: {
    showToasts?: boolean;    // 是否显示toast通知
  } = {}
) {
  const { showToasts = false } = options;
  
  useBridgeEvents({
    'tags-updated': (payload) => {
      console.log('标签已更新，触发刷新', payload);
      onTagsUpdated();
    }
  }, { showToasts });
}

/**
 * 带API就绪状态检查的标签更新监听Hook
 * 
 * 专门用于需要检查API状态的组件使用
 * 
 * @param onTagsUpdated 标签更新时的回调函数
 * @param isApiReady API是否就绪
 * @param options 配置选项
 */
export function useTagsUpdateListenerWithApiCheck(
  onTagsUpdated: () => void,
  isApiReady: boolean,
  options: {
    showToasts?: boolean;
  } = {}
) {
  useTagsUpdateListener(() => {
    if (isApiReady) {
      console.log('API就绪，执行标签更新回调');
      onTagsUpdated();
    } else {
      console.log('收到tags-updated事件，但API尚未就绪，忽略');
    }
  }, options);
}
