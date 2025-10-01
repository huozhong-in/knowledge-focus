
import React, { useState, useEffect } from 'react';
import { useAppStore } from '@/main';
import { Button } from "./components/ui/button";
import { toast } from "sonner";
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { 
  checkFullDiskAccessPermission, 
  requestFullDiskAccessPermission 
} from "tauri-plugin-macos-permissions-api";
import { relaunch } from '@tauri-apps/plugin-process';
import { useTranslation } from 'react-i18next';

interface SplashProps {
  setShowSplash: (showSplash: boolean) => void;
}

const Splash: React.FC<SplashProps> = ({setShowSplash: setShowSplash }) => {
  // 使用 selector 获取 Zustand store 中的状态，避免不必要的重渲染
  const isApiReady = useAppStore(state => state.isApiReady);
  const [loading, setLoading] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState("Checking permissions...");
  const [hasFullDiskAccess, setHasFullDiskAccess] = useState(false);
  const [checkingPermission, setCheckingPermission] = useState(true);
  const [permissionRequested, setPermissionRequested] = useState(false);
  
  // API 启动日志相关状态
  const [apiLogs, setApiLogs] = useState<string[]>([]);
  const [hasApiError, setHasApiError] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  
  const { t } = useTranslation();
  
  // 检查完全磁盘访问权限
  const checkFullDiskAccess = async () => {
    try {
      setCheckingPermission(true);
      setLoadingMessage(t('INTRO.checking-permission'));
      
      // 使用tauri-plugin-macos-permissions-api检查权限
      const permission = await checkFullDiskAccessPermission();
      // console.log("[权限检查] 完全磁盘访问权限状态:", permission);
      setHasFullDiskAccess(!!permission);
      
      if (permission) {
        setLoadingMessage(t('INTRO.permission-verified'));
        // console.log("[权限检查] 权限检查通过，等待API就绪后自动启动后端扫描");
      } else {
        setLoadingMessage(t('INTRO.permission-denied'));
        // console.log("[权限检查] 权限未获得，阻止进入应用");
      }
      
      return !!permission;
    } catch (error) {
      console.error("[权限检查] 检查完全磁盘访问权限失败:", error);
      setLoadingMessage(t('INTRO.permission-check-failed'));
      toast.error(t('INTRO.permission-check-failed'));
      setHasFullDiskAccess(false);
      return false;
    } finally {
      setCheckingPermission(false);
    }
  };

  // 请求完全磁盘访问权限
  const requestFullDiskAccess = async () => {
    try {
      setCheckingPermission(true);
      setLoadingMessage(t('INTRO.requesting-permission'));
      
      // 使用tauri-plugin-macos-permissions-api请求权限
      const result = await requestFullDiskAccessPermission();
      console.log("[权限请求] 请求结果:", result);
      
      // 标记已请求权限，这将改变按钮行为
      setPermissionRequested(true);
      
      // 提供明确的授权指导
      toast.success(
        t('INTRO.requesting-permission-steps'), 
        { duration: 10000 }
      );
      
      setLoadingMessage(t('INTRO.requesting-permission-detail'));
      
      // 延迟检查权限状态 - 用户可能在系统设置中立即授予权限
      const checkPermissionWithDelay = async () => {
        // 等待用户可能在系统设置中进行的操作
        // console.log("[权限请求] 延迟3秒后重新检查权限状态");
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        // 重新检查权限
        const hasPermissionNow = await checkFullDiskAccess();
        if (hasPermissionNow) {
          // console.log("[权限请求] 重新检查发现权限已授予");
          toast.success(t('INTRO.permission-granted'));
        } else {
          // console.log("[权限请求] 重新检查后权限仍未授予");
          // 用户可能需要重启应用以使权限生效
          toast.info(t('INTRO.permission-not-effective'), { duration: 8000 });
        }
      };
      
      // 执行延迟检查
      checkPermissionWithDelay();
      
    } catch (error) {
      console.error("[权限请求] 请求完全磁盘访问权限失败:", error);
      toast.error(t('INTRO.permission-request-failed'));
      
      // 即使出错也给出明确的手动操作指南
      toast.info(
        t('INTRO.requesting-permission-steps'),
        { duration: 10000 }
      );
    } finally {
      setCheckingPermission(false);
    }
  };
  
  // 初始化时最优先检查权限，确保在任何后端操作之前进行
  useEffect(() => {
    const initPermissionCheck = async () => {
      // console.log("[初始化] 开始检查完全磁盘访问权限");
      
      try {
        setCheckingPermission(true);
        setLoadingMessage(t('INTRO.checking-permission'));
        
        // 使用tauri-plugin-macos-permissions-api检查权限
        const permission = await checkFullDiskAccessPermission();
        // console.log("[初始化] 完全磁盘访问权限状态:", permission);
        setHasFullDiskAccess(!!permission);
        
        // 如果有权限，设置加载状态等待API就绪
        if (permission) {
          // console.log("[初始化] 权限检查通过，等待API就绪后启动后端扫描");
          setLoading(true);
          setLoadingMessage(t('INTRO.permission-verified'));
        } else {
          // console.log("[初始化] 权限检查未通过，阻止后端初始化");
          // 没有权限，显示请求权限界面，不允许进入应用或开始后端扫描
          setLoading(false);
          setLoadingMessage(t('INTRO.permission-denied'));
        }
      } catch (error) {
        console.error("[初始化] 权限检查过程中出错:", error);
        setHasFullDiskAccess(false);
        setLoading(false);
        setLoadingMessage(t('INTRO.permission-check-failed'));
      } finally {
        setCheckingPermission(false);
      }
    };
    
    // 立即执行权限检查，确保是应用启动的第一个操作
    initPermissionCheck();
  }, []);
  
  // 监听 API 启动日志
  useEffect(() => {
    let apiLogUnlisten: (() => void) | null = null;
    let apiErrorUnlisten: (() => void) | null = null;
    let isMounted = true;
    
    const setupApiLogListeners = async () => {
      try {
        // 监听 API 日志
        apiLogUnlisten = await listen<string>('api-log', (event) => {
          if (!isMounted) return; // 组件已卸载，忽略事件
          
          const logLine = event.payload;
          if (logLine && logLine.trim()) {
            const trimmedLog = logLine.trim();
            // 避免重复日志
            setApiLogs(prev => {
              if (prev[prev.length - 1] !== trimmedLog) {
                return [...prev, trimmedLog];
              }
              return prev;
            });
            
            // 根据日志内容更新状态消息
            if (trimmedLog.includes('正在同步 Python 虚拟环境') || trimmedLog.includes('sync') || trimmedLog.includes('Syncing')) {
              setLoadingMessage('正在同步 Python 环境...');
              setShowLogs(true);
            } else if (trimmedLog.includes('download') || trimmedLog.includes('install') || trimmedLog.includes('Downloading')) {
              setLoadingMessage('正在下载安装依赖包...');
              setShowLogs(true);
            } else if (trimmedLog.includes('FastAPI') || trimmedLog.includes('Uvicorn') || trimmedLog.includes('服务已启动')) {
              setLoadingMessage('正在启动 API 服务器...');
              setShowLogs(true);
            } else if (trimmedLog.includes('虚拟环境同步完成') || trimmedLog.includes('sync completed')) {
              setLoadingMessage('Python 环境准备完成，启动 API...');
            }
          }
        });
        
        // 监听 API 错误
        if (isMounted) {
          apiErrorUnlisten = await listen<string>('api-error', (event) => {
            if (!isMounted) return; // 组件已卸载，忽略事件
            
            const errorLine = event.payload;
            if (errorLine && errorLine.trim()) {
              const trimmedError = errorLine.trim();
              // 避免重复错误日志
              setApiLogs(prev => {
                const errorMsg = `ERROR: ${trimmedError}`;
                if (prev[prev.length - 1] !== errorMsg) {
                  return [...prev, errorMsg];
                }
                return prev;
              });
              setHasApiError(true);
              setShowLogs(true);
              setLoadingMessage('API 启动过程中出现错误，请查看详细日志');
            }
          });
        }
      } catch (error) {
        if (isMounted) {
          console.error('设置 API 日志监听器失败:', error);
        }
      }
    };
    
    setupApiLogListeners();
    
    return () => {
      console.log('[Splash] 组件卸载，清理 API 日志监听器');
      isMounted = false;
      // 清理监听器
      try {
        if (apiLogUnlisten) {
          apiLogUnlisten();
          console.log('[Splash] API 日志监听器已清理');
        }
        if (apiErrorUnlisten) {
          apiErrorUnlisten();
          console.log('[Splash] API 错误监听器已清理');
        }
      } catch (error) {
        console.error('[Splash] 清理监听器时出错:', error);
      }
    };
  }, []);
  
  useEffect(() => {
    // 只有在已经获取到权限且API就绪的情况下才启动后端扫描
    if (hasFullDiskAccess && isApiReady) {
      const startBackendScan = async () => {
        try {
          setLoadingMessage("Starting backend file scanning...");
          await invoke('start_backend_scanning');
          // console.log("[API就绪] 已通知Rust后端开始粗筛工作");
          setLoadingMessage("Backend scanning started, preparing to enter the app...");
        } catch (error) {
          console.error("[API就绪] 启动后端扫描失败:", error);
          setLoadingMessage("Backend scanning failed to start, please restart the app");
          toast.error("Backend scanning failed to start, please restart the app");
          return;
        }
        
        setLoading(false); // 更新本地加载状态
        
        // 设置消息为自动关闭提示
        setLoadingMessage(t('INTRO.initialization-complete'));
        // 略微延迟关闭Splash以便用户能看到成功信息
        setTimeout(() => {
          setShowSplash(false); // 自动关闭Splash
        }, 800);
      };
      
      startBackendScan();
    } else if (!hasFullDiskAccess) {
      // 如果API就绪但权限不足，仍然阻止进入
      setLoading(false);
    }
  }, [isApiReady, hasFullDiskAccess]);

  return (
    <div className="flex flex-col items-center justify-center max-w-md mx-auto h-screen p-5">
      <div>
        <div className="text-2xl font-bold text-center">{t('INTRO.welcome')}</div>
        <div className="text-center">
          {t('INTRO.description')}
        </div>
      </div>
      
      {/* 加载指示器容器 - 固定高度防止布局跳动 */}
      <div className="h-20 flex justify-center items-center my-4">
        {(loading || checkingPermission) && (
          <div className="relative w-12 h-12">
            <svg className="animate-spin" viewBox="0 0 24 24" fill="none" stroke="#D29B71" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="2" x2="12" y2="6"></line>
              <line x1="12" y1="18" x2="12" y2="22"></line>
              <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
              <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
              <line x1="2" y1="12" x2="6" y2="12"></line>
              <line x1="18" y1="12" x2="22" y2="12"></line>
              <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
              <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
            </svg>
          </div>
        )}
        
        {/* 权限状态图标 */}
        {!loading && !checkingPermission && (
          <div className={`flex items-center justify-center p-3 rounded-full ${hasFullDiskAccess ? 'bg-green-100' : 'bg-yellow-100'}`}>
            {hasFullDiskAccess ? (
              <svg className="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path>
              </svg>
            ) : (
              <svg className="w-10 h-10 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
              </svg>
            )}
          </div>
        )}
      </div>
      
      <p className={`text-center mb-4 ${
        hasFullDiskAccess && isApiReady 
          ? "text-green-600" 
          : !hasFullDiskAccess 
            ? "text-yellow-600 font-semibold" 
            : "text-whiskey-700 animate-pulse"
      }`}>
        {loadingMessage}
      </p>
      
      {/* API 启动日志显示区域 */}
      {showLogs && (
        <div className="w-full mb-4">
          <div className="bg-gray-50 border border-gray-200 rounded-md p-3 max-h-40 overflow-y-auto">
            <div className="text-xs font-mono space-y-1">
              {apiLogs.length > 0 ? (
                apiLogs.slice(-20).map((log, index) => (
                  <div 
                    key={index} 
                    className={`${log.startsWith('ERROR:') ? 'text-red-600' : 'text-gray-700'}`}
                  >
                    {log}
                  </div>
                ))
              ) : (
                <div className="text-gray-500 italic">Waiting for logs...</div>
              )}
            </div>
          </div>
          
          {/* 如果有错误，显示文档链接 */}
          {hasApiError && (
            <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-700 mb-2">
                API 启动过程中出现错误，可能是网络连接问题导致依赖包下载失败。
              </p>
              <a 
                href="https://kf.huozhong.in/doc" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:text-blue-800 underline font-medium"
              >
                📖 查看解决方案文档
              </a>
            </div>
          )}
        </div>
      )}
      
      {/* 权限说明 */}
      {!hasFullDiskAccess && !checkingPermission && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-4">
          <p className="text-sm text-yellow-700 mb-2">
            {t('INTRO.permission-request')}
          </p>
          <p className="text-sm text-yellow-700">
            {t('INTRO.permission-request-detail')}
          </p>
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-2 sm:gap-0">          
        {/* 未获得权限时显示请求权限按钮或重启App按钮 */}
        {!hasFullDiskAccess && !checkingPermission && (
          <Button
            onClick={permissionRequested ? () => relaunch() : requestFullDiskAccess}
            className={`w-full sm:w-auto text-white ${permissionRequested ? 'bg-green-600 hover:bg-green-700' : 'bg-yellow-600 hover:bg-yellow-700'} rounded-lg`}
          >
            {permissionRequested ? t('INTRO.restart-app') : t('INTRO.request-permission')}
          </Button>
        )}
      </div>
    </div>
  )
};

export default Splash;