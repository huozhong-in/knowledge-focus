import React, { useState, useEffect } from 'react';
import { useAppStore } from '@/main';
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Progress } from "./components/ui/progress";
import { ScrollArea } from "./components/ui/scroll-area";
import { Alert, AlertDescription, AlertTitle } from "./components/ui/alert";
import { toast } from "sonner";
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { 
  checkFullDiskAccessPermission, 
  requestFullDiskAccessPermission 
} from "tauri-plugin-macos-permissions-api";
import { relaunch } from '@tauri-apps/plugin-process';
import { useTranslation } from 'react-i18next';
import { cn } from './lib/utils';
import { 
  Loader2, 
  CheckCircle, 
  AlertTriangle, 
  ChevronDown, 
  Copy, 
  ExternalLink,
  Package,
  Server,
  Download
} from 'lucide-react';
import { motion } from 'framer-motion';

// ============ 类型定义 ============

type PhaseStatus = 'pending' | 'running' | 'success' | 'error';

interface StartupPhase {
  id: string;
  title: string;
  icon: React.ReactNode;
  status: PhaseStatus;
  progress?: number;
  message?: string;
  error?: string;
}

interface SplashProps {
  setShowSplash: (showSplash: boolean) => void;
}

// ============ 主组件 ============

const Splash: React.FC<SplashProps> = ({ setShowSplash }) => {
  const { t } = useTranslation();
  const isApiReady = useAppStore(state => state.isApiReady);
  
  // 三个阶段的状态
  const [phases, setPhases] = useState<StartupPhase[]>([
    {
      id: 'env-setup',
      title: 'Python 环境',
      icon: <Package className="w-6 h-6" />,
      status: 'running',
      progress: 0,
      message: '正在初始化...'
    },
    {
      id: 'api-start',
      title: 'API 服务',
      icon: <Server className="w-6 h-6" />,
      status: 'pending',
      message: '等待中...'
    },
    {
      id: 'model-download',
      title: '全能小模型',
      icon: <Download className="w-6 h-6" />,
      status: 'pending',
      message: '等待中...'
    }
  ]);
  
  // 日志相关
  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  
  // 权限相关
  const [hasFullDiskAccess, setHasFullDiskAccess] = useState(false);
  const [checkingPermission, setCheckingPermission] = useState(false);
  const [permissionRequested, setPermissionRequested] = useState(false);
  
  // 模型下载
  const [selectedMirror, setSelectedMirror] = useState<'huggingface' | 'hf-mirror'>('huggingface');
  
  // 更新某个阶段的状态
  const updatePhase = (id: string, updates: Partial<StartupPhase>) => {
    setPhases(prev => prev.map(phase => 
      phase.id === id ? { ...phase, ...updates } : phase
    ));
  };
  
  // 添加日志（去重 + 限制数量）
  const addLog = (log: string) => {
    setLogs(prev => {
      const newLogs = [...prev, log];
      // 去重：如果最后一条和当前相同，不添加
      if (prev.length > 0 && prev[prev.length - 1] === log) {
        return prev;
      }
      // 限制最多 200 条
      return newLogs.slice(-200);
    });
  };
  
  // 复制日志
  const copyLogs = () => {
    const text = logs.join('\n');
    navigator.clipboard.writeText(text);
    toast.success('日志已复制到剪贴板');
  };
  
  // ============ 事件监听 ============
  
  // 监听 API 日志
  useEffect(() => {
    let unlistenLog: (() => void) | null = null;
    let unlistenError: (() => void) | null = null;
    let isMounted = true;
    
    const setup = async () => {
      try {
        unlistenLog = await listen<string>('api-log', (event) => {
          if (!isMounted) return;
          const log = event.payload;
          addLog(log);
          
          // 解析日志判断阶段
          // Phase 1: Python 环境初始化
          if (log.includes('uv sync') || log.includes('Resolved ') || log.includes('Prepared ')) {
            updatePhase('env-setup', { status: 'running', message: 'Python 依赖同步中...' });
          } 
          // Phase 1 完成标志
          else if (log.includes('Python virtual environment sync completed')) {
            updatePhase('env-setup', { status: 'success', message: 'Python 环境就绪' });
            updatePhase('api-start', { status: 'running', message: '正在启动 FastAPI...' });
          }
          // Phase 2: FastAPI 启动
          else if (log.includes('Starting Python API service') || log.includes('Initializing FastAPI')) {
            updatePhase('api-start', { status: 'running', message: '正在启动 FastAPI...' });
          }
          // Phase 2 完成标志
          else if (log.includes('Uvicorn running') || log.includes('Application startup complete')) {
            updatePhase('api-start', { status: 'success', message: 'API 服务已启动' });
            updatePhase('model-download', { status: 'running', message: '准备下载模型...' });
          }
        });
        
        unlistenError = await listen<string>('api-error', (event) => {
          if (!isMounted) return;
          const error = event.payload;
          addLog(`[ERROR] ${error}`);
          
          // 判断错误属于哪个阶段
          if (error.includes('uv sync')) {
            updatePhase('env-setup', { status: 'error', error });
          } else if (error.includes('FastAPI') || error.includes('Uvicorn')) {
            updatePhase('api-start', { status: 'error', error });
          }
        });
      } catch (error) {
        console.error('设置 API 监听器失败:', error);
      }
    };
    
    setup();
    
    return () => {
      isMounted = false;
      if (unlistenLog) unlistenLog();
      if (unlistenError) unlistenError();
    };
  }, []);
  
  // 监听模型下载进度
  useEffect(() => {
    let unlistenProgress: (() => void) | null = null;
    let unlistenCompleted: (() => void) | null = null;
    let unlistenFailed: (() => void) | null = null;
    let isMounted = true;
    
    const setup = async () => {
      try {
        unlistenProgress = await listen<{
          current: number;
          total: number;
          message?: string;
          stage?: string;
        }>('model-download-progress', (event) => {
          if (!isMounted) return;
          const { current, total, message } = event.payload;
          const progress = total > 0 ? Math.round((current / total) * 100) : 0;
          
          updatePhase('model-download', {
            status: 'running',
            progress,
            message: message || `下载中 ${progress}%`
          });
          
          if (message) {
            addLog(`[MODEL] ${message}`);
          }
        });
        
        unlistenCompleted = await listen('model-download-completed', () => {
          if (!isMounted) return;
          updatePhase('model-download', {
            status: 'success',
            progress: 100,
            message: '模型下载完成'
          });
          addLog('[MODEL] 模型下载完成');
        });
        
        unlistenFailed = await listen<{error_message: string}>('model-download-failed', (event) => {
          if (!isMounted) return;
          const error = event.payload.error_message || '下载失败';
          updatePhase('model-download', {
            status: 'error',
            error
          });
          addLog(`[MODEL ERROR] ${error}`);
        });
      } catch (error) {
        console.error('设置模型下载监听器失败:', error);
      }
    };
    
    setup();
    
    return () => {
      isMounted = false;
      if (unlistenProgress) unlistenProgress();
      if (unlistenCompleted) unlistenCompleted();
      if (unlistenFailed) unlistenFailed();
    };
  }, []);
  
  // API 就绪后初始化模型
  useEffect(() => {
    if (!isApiReady) return;
    
    const initModel = async () => {
      try {
        addLog('[MODEL] 开始检查和下载模型...');
        
        const response = await fetch('http://127.0.0.1:60315/models/builtin/initialize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mirror: selectedMirror })
        });
        
        const result = await response.json();
        
        if (result.status === 'ready') {
          updatePhase('model-download', {
            status: 'success',
            message: '模型已就绪'
          });
          addLog('[MODEL] 模型已存在');
        } else if (result.status === 'downloading') {
          updatePhase('model-download', {
            status: 'running',
            message: '正在下载模型...'
          });
          addLog('[MODEL] 开始下载模型');
        }
      } catch (error) {
        console.error('初始化模型失败:', error);
        updatePhase('model-download', {
          status: 'error',
          error: '无法连接到 API'
        });
      }
    };
    
    initModel();
  }, [isApiReady, selectedMirror]);
  
  // 模型下载完成后检查权限
  useEffect(() => {
    const modelPhase = phases.find(p => p.id === 'model-download');
    if (modelPhase?.status === 'success' && isApiReady) {
      checkPermissionAndEnter();
    }
  }, [phases, isApiReady]);
  
  // 检查权限并进入应用
  const checkPermissionAndEnter = async () => {
    try {
      setCheckingPermission(true);
      const permission = await checkFullDiskAccessPermission();
      setHasFullDiskAccess(!!permission);
      setCheckingPermission(false);
      
      if (!permission) {
        return;
      }
      
      // 启动后端扫描
      await invoke('start_backend_scanning');
      addLog('[COMPLETE] 初始化完成，进入应用');
      
      setTimeout(() => {
        setShowSplash(false);
      }, 800);
    } catch (error) {
      console.error('权限检查失败:', error);
      setCheckingPermission(false);
    }
  };
  
  // 请求权限
  const requestPermission = async () => {
    try {
      setCheckingPermission(true);
      await requestFullDiskAccessPermission();
      setPermissionRequested(true);
      
      toast.success(t('INTRO.requesting-permission-steps'), { duration: 10000 });
      
      setTimeout(async () => {
        const hasPermission = await checkFullDiskAccessPermission();
        setHasFullDiskAccess(!!hasPermission);
        setCheckingPermission(false);
        
        if (hasPermission) {
          toast.success(t('INTRO.permission-granted'));
          checkPermissionAndEnter();
        } else {
          toast.info(t('INTRO.permission-not-effective'), { duration: 8000 });
        }
      }, 3000);
    } catch (error) {
      console.error('请求权限失败:', error);
      setCheckingPermission(false);
      toast.error(t('INTRO.permission-request-failed'));
    }
  };
  
  // ============ 渲染组件 ============
  
  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 bg-gradient-to-b from-background to-muted/20">
      {/* Logo 和标题 */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-12"
      >
        <h1 className="text-3xl font-bold mb-2">{t('INTRO.welcome')}</h1>
        <p className="text-muted-foreground">{t('INTRO.description')}</p>
        <p className="text-sm text-muted-foreground mt-2">
          预计需要 3-5 分钟（首次启动）
        </p>
      </motion.div>
      
      {/* 三个阶段 - 横向布局 */}
      <div className="w-full max-w-4xl mb-8">
        <div className="flex items-start gap-4">
          {phases.map((phase, index) => (
            <React.Fragment key={phase.id}>
              {/* 阶段指示器 */}
              <PhaseIndicator phase={phase} index={index} />
              
              {/* 连接线 */}
              {index < phases.length - 1 && (
                <div className="flex items-center pt-6">
                  <div 
                    className={cn(
                      "w-16 h-0.5 transition-colors duration-500",
                      phase.status === 'success' ? "bg-green-500" : "bg-gray-300"
                    )}
                  />
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
      
      {/* 专家模式 - 日志面板 */}
      <div className="w-full max-w-4xl">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowLogs(!showLogs)}
          className="w-full justify-between mb-2"
        >
          <span className="flex items-center gap-2">
            <ChevronDown className={cn(
              "w-4 h-4 transition-transform",
              showLogs && "rotate-180"
            )} />
            {showLogs ? '隐藏' : '查看'}详细日志
          </span>
          <Badge variant="secondary">{logs.length}</Badge>
        </Button>
        
        {showLogs && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border border-border rounded-lg overflow-hidden"
          >
            <div className="bg-black/90 p-4">
              <ScrollArea className="h-48 font-mono text-xs text-green-400">
                {logs.map((log, i) => (
                  <div key={i} className="py-0.5">{log}</div>
                ))}
              </ScrollArea>
              
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="secondary" onClick={copyLogs}>
                  <Copy className="w-4 h-4 mr-2" />
                  复制日志
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    invoke('open_url', {
                      url: 'https://github.com/huozhong-in/knowledge-focus/issues/new'
                    });
                  }}
                >
                  <ExternalLink className="w-4 h-4 mr-2" />
                  报告问题
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </div>
      
      {/* 错误恢复面板 */}
      {phases.some(p => p.status === 'error') && (
        <ErrorRecoveryPanel 
          phases={phases}
          selectedMirror={selectedMirror}
          setSelectedMirror={setSelectedMirror}
          onRetry={() => window.location.reload()}
        />
      )}
      
      {/* 权限请求 */}
      {!hasFullDiskAccess && !checkingPermission && phases.every(p => p.status === 'success') && (
        <div className="w-full max-w-4xl mt-4">
          <Alert variant="default" className="border-yellow-200 bg-yellow-50">
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
            <AlertTitle className="text-yellow-900">{t('INTRO.permission-request')}</AlertTitle>
            <AlertDescription className="text-yellow-800">
              <p className="mb-3">{t('INTRO.permission-request-detail')}</p>
              <Button
                onClick={permissionRequested ? () => relaunch() : requestPermission}
                className={cn(
                  "w-full",
                  permissionRequested 
                    ? "bg-green-600 hover:bg-green-700" 
                    : "bg-yellow-600 hover:bg-yellow-700"
                )}
              >
                {permissionRequested ? t('INTRO.restart-app') : t('INTRO.request-permission')}
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      )}
    </div>
  );
};

// ============ 子组件 ============

// 阶段指示器组件
const PhaseIndicator: React.FC<{ phase: StartupPhase; index: number }> = ({ phase, index }) => {
  return (
    <div className="flex-1">
      <div className="flex flex-col items-center">
        {/* 图标圈 */}
        <div
          className={cn(
            "w-16 h-16 rounded-full flex items-center justify-center mb-3 transition-all duration-300",
            phase.status === 'pending' && "bg-gray-200",
            phase.status === 'running' && "bg-blue-500 animate-pulse",
            phase.status === 'success' && "bg-green-500",
            phase.status === 'error' && "bg-red-500 animate-shake"
          )}
        >
          {phase.status === 'pending' && (
            <span className="text-gray-600 font-bold">{index + 1}</span>
          )}
          {phase.status === 'running' && (
            <Loader2 className="w-8 h-8 text-white animate-spin" />
          )}
          {phase.status === 'success' && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 260, damping: 20 }}
            >
              <CheckCircle className="w-8 h-8 text-white" />
            </motion.div>
          )}
          {phase.status === 'error' && (
            <AlertTriangle className="w-8 h-8 text-white" />
          )}
        </div>
        
        {/* 标题 */}
        <h3 className="font-semibold text-center mb-2">{phase.title}</h3>
        
        {/* 消息 */}
        <p className={cn(
          "text-sm text-center min-h-[2.5rem]",
          phase.status === 'error' ? "text-red-600" : "text-muted-foreground"
        )}>
          {phase.error || phase.message}
        </p>
        
        {/* 进度条 */}
        {phase.status === 'running' && typeof phase.progress === 'number' && (
          <div className="w-full mt-2">
            <Progress value={phase.progress} className="h-2" />
            <p className="text-xs text-center text-muted-foreground mt-1">
              {phase.progress}%
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

// 错误恢复面板
const ErrorRecoveryPanel: React.FC<{
  phases: StartupPhase[];
  selectedMirror: string;
  setSelectedMirror: (mirror: 'huggingface' | 'hf-mirror') => void;
  onRetry: () => void;
}> = ({ phases, selectedMirror, setSelectedMirror, onRetry }) => {
  const errorPhase = phases.find(p => p.status === 'error');
  if (!errorPhase) return null;
  
  return (
    <div className="w-full max-w-4xl mt-4">
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>启动失败</AlertTitle>
        <AlertDescription>
          <p className="mb-3">{errorPhase.error}</p>
          
          {errorPhase.id === 'model-download' && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <label className="text-sm">切换镜像:</label>
                <select
                  value={selectedMirror}
                  onChange={(e) => setSelectedMirror(e.target.value as 'huggingface' | 'hf-mirror')}
                  className="text-sm border rounded px-2 py-1 bg-background"
                >
                  <option value="huggingface">HuggingFace (全球)</option>
                  <option value="hf-mirror">HF-Mirror (国内)</option>
                </select>
              </div>
            </div>
          )}
          
          <Button onClick={onRetry} className="w-full mt-3">
            重试
          </Button>
          
          {errorPhase.id === 'env-setup' && (
            <p className="text-xs mt-2">
              如果重试仍然失败，请检查网络连接或查看详细日志排查问题。
            </p>
          )}
        </AlertDescription>
      </Alert>
    </div>
  );
};

export default Splash;
