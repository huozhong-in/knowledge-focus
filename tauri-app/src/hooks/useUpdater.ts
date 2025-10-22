import { useCallback, useEffect } from 'react';
import { check } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';
import { useAppStore } from '@/main';
import { toast } from 'sonner';

const UPDATE_CHECK_INTERVAL = 24 * 60 * 60 * 1000; // 24小时（毫秒）

export const useUpdater = () => {
  const {
    updateAvailable,
    updateVersion,
    updateNotes,
    downloadProgress,
    isDownloading,
    isReadyToInstall,
    lastUpdateCheck,
    updateError,
    setUpdateAvailable,
    setDownloadProgress,
    setIsDownloading,
    setIsReadyToInstall,
    setLastUpdateCheck,
    setUpdateError,
    resetUpdateState
  } = useAppStore();

  // 检查更新
  const checkForUpdates = useCallback(async (manual = false) => {
    try {
      console.log('[更新检查] 开始检查更新...');
      console.log('[更新检查] 配置信息:', {
        endpoints: ['https://github.com/huozhong-in/knowledge-focus/releases/latest/download/latest.json'],
        timeout: 30000
      });
      
      // 重置之前的状态
      if (manual) {
        resetUpdateState();
      }
      
      // 配置代理和超时
      const update = await check({
        timeout: 30000, // 30秒超时
        headers: {
          'User-Agent': 'KnowledgeFocus-Updater/1.0',
          'Cache-Control': 'no-cache'
        }
        // 如果需要代理，可以添加这个配置
        // proxy: 'http://127.0.0.1:7890'
      });
      const now = Date.now();
      
      console.log('[更新检查] 检查完成，结果:', update ? '发现更新' : '无更新');
      
      // 更新检查时间
      await setLastUpdateCheck(now);
      
      if (update) {
        console.log(`[更新检查] 发现新版本: ${update.version}`);
        console.log(`[更新检查] 发布日期: ${update.date}`);
        console.log(`[更新检查] 更新说明: ${update.body}`);
        
        setUpdateAvailable(true, update.version, update.body);
        
        if (manual) {
          toast.success(`发现新版本 ${update.version}！`);
        }
        
        return update;
      } else {
        console.log('[更新检查] 当前已是最新版本');
        setUpdateAvailable(false);
        
        if (manual) {
          toast.success('当前已是最新版本');
        }
        
        return null;
      }
    } catch (error) {
      console.error('[更新检查] 检查更新失败:', error);
      
      // 提取更详细的错误信息
      let errorMessage = 'error while checking for updates';
      if (error instanceof Error) {
        errorMessage = error.message;
        
        // 更具体的错误类型判断
        if (error.message.includes('fetch')) {
          errorMessage = '网络连接失败，请检查网络连接';
        } else if (error.message.includes('timeout')) {
          errorMessage = '请求超时，请稍后重试';
        } else if (error.message.includes('SSL') || error.message.includes('certificate')) {
          errorMessage = 'SSL证书验证失败';
        } else if (error.message.includes('JSON') || error.message.includes('parse')) {
          errorMessage = '服务器响应格式错误';
        } else if (error.message.includes('signature')) {
          errorMessage = '更新包签名验证失败';
        }
      }
      
      console.error('[更新检查] 详细错误信息:', errorMessage);
      setUpdateError(errorMessage);
      
      if (manual) {
        toast.error(`failed to check for updates: ${errorMessage}`);
      }
      
      return null;
    }
  }, [setUpdateAvailable, setLastUpdateCheck, setUpdateError, resetUpdateState]);

  // 下载并安装更新
  const downloadAndInstall = useCallback(async () => {
    try {
      console.log('[更新下载] 开始下载更新...');
      setIsDownloading(true);
      setDownloadProgress(0);
      setUpdateError(null);
      
      const update = await check();
      if (!update) {
        throw new Error('未找到可用更新');
      }
      
      let downloaded = 0;
      let contentLength = 0;
      
      // 开始下载并安装
      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case 'Started':
            contentLength = event.data.contentLength || 0;
            console.log(`[更新下载] 开始下载 ${Math.round(contentLength / 1024 / 1024 * 100) / 100} MB`);
            break;
            
          case 'Progress':
            downloaded += event.data.chunkLength;
            const progress = Math.round((downloaded / contentLength) * 100);
            setDownloadProgress(progress);
            console.log(`[更新下载] 进度: ${progress}% (${Math.round(downloaded / 1024 / 1024 * 100) / 100}MB / ${Math.round(contentLength / 1024 / 1024 * 100) / 100}MB)`);
            break;
            
          case 'Finished':
            console.log('[更新下载] 下载完成');
            setDownloadProgress(100);
            break;
        }
      });
      
      console.log('[更新安装] 更新安装完成');
      setIsDownloading(false);
      setIsReadyToInstall(true);
      toast.success('更新下载完成！点击重启应用以完成更新。');
      
    } catch (error) {
      console.error('[更新下载] 下载更新失败:', error);
      const errorMessage = error instanceof Error ? error.message : '下载更新失败';
      setUpdateError(errorMessage);
      setIsDownloading(false);
      toast.error(`下载更新失败: ${errorMessage}`);
    }
  }, [setIsDownloading, setDownloadProgress, setIsReadyToInstall, setUpdateError]);

  // 重启应用
  const restartApp = useCallback(async () => {
    try {
      console.log('[应用重启] 正在重启应用...');
      await relaunch();
    } catch (error) {
      console.error('[应用重启] 重启失败:', error);
      toast.error('重启失败，请手动重启应用');
    }
  }, []);

  // 自动检查更新（每天一次）
  useEffect(() => {
    const shouldAutoCheck = () => {
      if (!lastUpdateCheck) {
        return true; // 如果从未检查过，则检查
      }
      
      const timeSinceLastCheck = Date.now() - lastUpdateCheck;
      return timeSinceLastCheck >= UPDATE_CHECK_INTERVAL;
    };

    // 延迟5秒后进行自动检查，避免影响应用启动
    const autoCheckTimer = setTimeout(() => {
      if (shouldAutoCheck()) {
        console.log('[自动更新检查] 执行定期更新检查');
        checkForUpdates(false);
      } else {
        if (lastUpdateCheck) {
          const nextCheck = new Date(lastUpdateCheck + UPDATE_CHECK_INTERVAL);
          console.log(`[自动更新检查] 下次检查时间: ${nextCheck.toLocaleString()}`);
        }
      }
    }, 5000);

    return () => clearTimeout(autoCheckTimer);
  }, [lastUpdateCheck, checkForUpdates]);

  return {
    // 状态
    updateAvailable,
    updateVersion,
    updateNotes,
    downloadProgress,
    isDownloading,
    isReadyToInstall,
    lastUpdateCheck,
    updateError,
    
    // 操作
    checkForUpdates,
    downloadAndInstall,
    restartApp,
    resetUpdateState
  };
};
