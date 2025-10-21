import { useState, useCallback, useEffect } from 'react';
import { toast } from 'sonner';

const API_BASE_URL = 'http://127.0.0.1:60315';

// 类型定义
export interface BuiltinModel {
  model_id: string;
  display_name: string;
  description: string;
  capabilities: string[];
  size_mb: number;
  downloaded: boolean;
  local_path: string | null;
  hf_model_id: string;
}

export interface BuiltinServerStatus {
  running: boolean;
  pid: number | null;
  loaded_model: string | null;
  port: number;
}

interface DownloadState {
  downloading: boolean;
  progress: number;
  error: string | null;
  completed?: boolean;  // 标记是否已完成,防止后续事件覆盖
}

/**
 * 内置模型管理 Hook
 * 提供内置 MLX-VLM 模型的列表、下载、删除、服务器管理等功能
 */
export function useBuiltinModels() {
  const [models, setModels] = useState<BuiltinModel[]>([]);
  const [serverStatus, setServerStatus] = useState<BuiltinServerStatus>({
    running: false,
    pid: null,
    loaded_model: null,
    port: 60316,
  });
  const [downloadStates, setDownloadStates] = useState<Record<string, DownloadState>>({});
  const [loading, setLoading] = useState(false);

  /**
   * 获取内置模型列表
   */
  const fetchModels = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/models/builtin/list`);
      const result = await response.json();
      
      if (result.success) {
        setModels(result.data);
      } else {
        throw new Error(result.message || '获取模型列表失败');
      }
    } catch (error) {
      console.error('Failed to fetch builtin models:', error);
      toast.error('获取内置模型列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 获取服务器状态
   */
  const fetchServerStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/models/builtin/server/status`);
      const result = await response.json();
      
      if (result.success) {
        setServerStatus(result.data);
      }
    } catch (error) {
      console.error('Failed to fetch server status:', error);
    }
  }, []);

  /**
   * 下载模型
   * @param modelId 模型ID
   */
  const downloadModel = useCallback(async (modelId: string) => {
    try {
      // 设置下载状态
      setDownloadStates(prev => ({
        ...prev,
        [modelId]: { downloading: true, progress: 0, error: null, completed: false }
      }));

      const response = await fetch(`${API_BASE_URL}/models/builtin/${modelId}/download`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (!result.success) {
        throw new Error(result.message || '启动下载失败');
      }

      toast.info('模型下载已开始,请等待...');
      
      // 注意:实际的进度更新通过 bridge events 处理
      // 这里只是初始化状态
      
    } catch (error) {
      console.error('Failed to start download:', error);
      const errorMessage = error instanceof Error ? error.message : '下载失败';
      
      setDownloadStates(prev => ({
        ...prev,
        [modelId]: { downloading: false, progress: 0, error: errorMessage, completed: false }
      }));
      
      toast.error(errorMessage);
    }
  }, []);

  /**
   * 删除模型
   * @param modelId 模型ID
   */
  const deleteModel = useCallback(async (modelId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/models/builtin/${modelId}`, {
        method: 'DELETE',
      });
      
      const result = await response.json();
      
      if (result.success) {
        toast.success('模型删除成功');
        
        // 清除该模型的下载状态
        setDownloadStates(prev => {
          const newStates = { ...prev };
          delete newStates[modelId];
          return newStates;
        });
        
        // 刷新模型列表
        await fetchModels();
      } else {
        throw new Error(result.message || '删除失败');
      }
    } catch (error) {
      console.error('Failed to delete model:', error);
      const errorMessage = error instanceof Error ? error.message : '删除模型失败';
      toast.error(errorMessage);
    }
  }, [fetchModels]);

  /**
   * 启动服务器
   */
  const startServer = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/models/builtin/server/start`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (result.success) {
        toast.success('服务器启动成功');
        await fetchServerStatus();
      } else {
        throw new Error(result.message || '启动失败');
      }
    } catch (error) {
      console.error('Failed to start server:', error);
      const errorMessage = error instanceof Error ? error.message : '启动服务器失败';
      toast.error(errorMessage);
    }
  }, [fetchServerStatus]);

  /**
   * 停止服务器
   */
  const stopServer = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/models/builtin/server/stop`, {
        method: 'POST',
      });
      
      const result = await response.json();
      
      if (result.success) {
        toast.success('服务器已停止');
        await fetchServerStatus();
      } else {
        throw new Error(result.message || '停止失败');
      }
    } catch (error) {
      console.error('Failed to stop server:', error);
      const errorMessage = error instanceof Error ? error.message : '停止服务器失败';
      toast.error(errorMessage);
    }
  }, [fetchServerStatus]);

  /**
   * 更新下载进度
   * 此方法供外部调用(比如从 bridge events)
   */
  const updateDownloadProgress = useCallback((modelId: string, progress: number) => {
    setDownloadStates(prev => {
      // 如果已经标记为完成,忽略后续的进度更新
      if (prev[modelId]?.completed) {
        return prev;
      }
      
      return {
        ...prev,
        [modelId]: { 
          downloading: true, 
          progress, 
          error: null,
          completed: false
        }
      };
    });
  }, []);

  /**
   * 标记下载完成
   * 此方法供外部调用(比如从 bridge events)
   */
  const markDownloadCompleted = useCallback(async (modelId: string) => {
    // 先标记为完成,防止后续进度事件干扰
    setDownloadStates(prev => ({
      ...prev,
      [modelId]: {
        downloading: false,
        progress: 100,
        error: null,
        completed: true
      }
    }));
    
    // 刷新模型列表以获取最新的 downloaded 状态
    await fetchModels();
    
    // 等待模型列表刷新后再清除下载状态
    // 使用 setTimeout 确保 UI 先更新为 downloaded
    setTimeout(() => {
      setDownloadStates(prev => {
        const newStates = { ...prev };
        delete newStates[modelId];
        return newStates;
      });
    }, 100);
  }, [fetchModels]);

  /**
   * 标记下载失败
   * 此方法供外部调用(比如从 bridge events)
   */
  const markDownloadFailed = useCallback((modelId: string, error: string) => {
    setDownloadStates(prev => ({
      ...prev,
      [modelId]: { 
        downloading: false, 
        progress: 0, 
        error,
        completed: false
      }
    }));
  }, []);

  /**
   * 获取指定模型的下载状态
   */
  const getDownloadState = useCallback((modelId: string): DownloadState => {
    return downloadStates[modelId] || { 
      downloading: false, 
      progress: 0, 
      error: null,
      completed: false
    };
  }, [downloadStates]);

  // 初始加载
  useEffect(() => {
    fetchModels();
    fetchServerStatus();
  }, [fetchModels, fetchServerStatus]);

  return {
    // 数据
    models,
    serverStatus,
    loading,
    downloadStates,  // 直接暴露状态对象
    
    // 方法
    fetchModels,
    fetchServerStatus,
    downloadModel,
    deleteModel,
    startServer,
    stopServer,
    
    // 下载状态管理
    getDownloadState,
    updateDownloadProgress,
    markDownloadCompleted,
    markDownloadFailed,
  };
}
