import React, { useState, useEffect } from 'react';
import { useAppStore } from '@/main';
import { Button } from "./components/ui/button";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { invoke } from '@tauri-apps/api/core';
import { 
  checkFullDiskAccessPermission, 
  requestFullDiskAccessPermission 
} from "tauri-plugin-macos-permissions-api";
import { relaunch } from '@tauri-apps/plugin-process';

interface IntroDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const IntroDialog: React.FC<IntroDialogProps> = ({ open, onOpenChange }) => {
  // 使用 selector 获取 Zustand store 中的状态，避免不必要的重渲染
  const isApiReady = useAppStore(state => state.isApiReady);
  const isFirstLaunch = useAppStore(state => state.isFirstLaunch);
  const setShowWelcomeDialog = useAppStore(state => state.setShowWelcomeDialog);
  const [loading, setLoading] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState("正在检查系统权限...");
  const [hasFullDiskAccess, setHasFullDiskAccess] = useState(false);
  const [checkingPermission, setCheckingPermission] = useState(true);
  const [permissionRequested, setPermissionRequested] = useState(false);
  
  // 检查完全磁盘访问权限
  const checkFullDiskAccess = async () => {
    try {
      setCheckingPermission(true);
      setLoadingMessage("正在检查完全磁盘访问权限...");
      
      // 使用tauri-plugin-macos-permissions-api检查权限
      const permission = await checkFullDiskAccessPermission();
      console.log("[权限检查] 完全磁盘访问权限状态:", permission);
      setHasFullDiskAccess(!!permission);
      
      if (permission) {
        setLoadingMessage("权限检查完成，等待后端API就绪...");
        console.log("[权限检查] 权限检查通过，等待API就绪后自动启动后端扫描");
      } else {
        setLoadingMessage("需要完全磁盘访问权限才能继续使用应用");
        console.log("[权限检查] 权限未获得，阻止进入应用");
      }
      
      return !!permission;
    } catch (error) {
      console.error("[权限检查] 检查完全磁盘访问权限失败:", error);
      setLoadingMessage("权限检查失败，请重启应用");
      toast.error("权限检查失败，请重启应用");
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
      setLoadingMessage("正在请求完全磁盘访问权限...");
      
      // 使用tauri-plugin-macos-permissions-api请求权限
      const result = await requestFullDiskAccessPermission();
      console.log("[权限请求] 请求结果:", result);
      
      // 标记已请求权限，这将改变按钮行为
      setPermissionRequested(true);
      
      // 提供明确的授权指导
      toast.success(
        "请在系统设置中授权:\n" +
        "1. 点击'系统偏好设置' > '安全性与隐私' > '隐私'\n" +
        "2. 选择'完全磁盘访问权限'\n" +
        "3. 勾选'KnowledgeFocus'应用\n" +
        "4. 授权完成后点击'重启App'按钮", 
        { duration: 10000 }
      );
      
      setLoadingMessage("请在系统设置中授予完全磁盘访问权限后重启应用");
      
      // 延迟检查权限状态 - 用户可能在系统设置中立即授予权限
      const checkPermissionWithDelay = async () => {
        // 等待用户可能在系统设置中进行的操作
        console.log("[权限请求] 延迟3秒后重新检查权限状态");
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        // 重新检查权限
        const hasPermissionNow = await checkFullDiskAccess();
        if (hasPermissionNow) {
          console.log("[权限请求] 重新检查发现权限已授予");
          toast.success("权限已成功获取！正在初始化系统...");
        } else {
          console.log("[权限请求] 重新检查后权限仍未授予");
          // 用户可能需要重启应用以使权限生效
          toast.info("如果您已授予权限但未生效，请重启应用", { duration: 8000 });
        }
      };
      
      // 执行延迟检查
      checkPermissionWithDelay();
      
    } catch (error) {
      console.error("[权限请求] 请求完全磁盘访问权限失败:", error);
      toast.error("权限请求失败，请手动在系统设置中开启权限");
      
      // 即使出错也给出明确的手动操作指南
      toast.info(
        "手动授权步骤:\n" +
        "1. 系统偏好设置 > 安全性与隐私 > 隐私\n" +
        "2. 选择'完全磁盘访问权限'\n" +
        "3. 添加并勾选'KnowledgeFocus'应用",
        { duration: 10000 }
      );
    } finally {
      setCheckingPermission(false);
    }
  };
  
  // 初始化时最优先检查权限，确保在任何后端操作之前进行
  useEffect(() => {
    const initPermissionCheck = async () => {
      console.log("[初始化] 开始检查完全磁盘访问权限");
      
      try {
        setCheckingPermission(true);
        setLoadingMessage("正在检查完全磁盘访问权限...");
        
        // 使用tauri-plugin-macos-permissions-api检查权限
        const permission = await checkFullDiskAccessPermission();
        console.log("[初始化] 完全磁盘访问权限状态:", permission);
        setHasFullDiskAccess(!!permission);
        
        // 如果有权限，设置加载状态等待API就绪
        if (permission) {
          console.log("[初始化] 权限检查通过，等待API就绪后启动后端扫描");
          setLoading(true);
          setLoadingMessage("权限验证通过，正在等待后端程序就绪...");
        } else {
          console.log("[初始化] 权限检查未通过，阻止后端初始化");
          // 没有权限，显示请求权限界面，不允许进入应用或开始后端扫描
          setLoading(false);
          setLoadingMessage("需要完全磁盘访问权限才能继续使用应用");
        }
      } catch (error) {
        console.error("[初始化] 权限检查过程中出错:", error);
        setHasFullDiskAccess(false);
        setLoading(false);
        setLoadingMessage("权限检查失败，请重启应用");
      } finally {
        setCheckingPermission(false);
      }
    };
    
    // 立即执行权限检查，确保是应用启动的第一个操作
    initPermissionCheck();
  }, []);
  
  // 使用全局状态的 isApiReady 值而不是直接监听事件
  useEffect(() => {
    // 只有在已经获取到权限且API就绪的情况下才启动后端扫描
    if (hasFullDiskAccess && isApiReady) {
      console.log("[API就绪] 权限检查通过且API就绪，启动后端扫描");
      
      // 启动后端扫描（仅在权限和API都就绪时）
      const startBackendScan = async () => {
        try {
          setLoadingMessage("正在启动后端文件扫描...");
          await invoke('start_backend_scanning');
          console.log("[API就绪] 已通知Rust后端开始粗筛工作");
          setLoadingMessage("后端扫描已启动，准备进入应用...");
        } catch (error) {
          console.error("[API就绪] 启动后端扫描失败:", error);
          setLoadingMessage("后端扫描启动失败，请重启应用");
          toast.error("后端扫描启动失败，请重启应用");
          return;
        }
        
        setLoading(false); // 更新本地加载状态
        
        // 处理非首次启动的逻辑
        if (!isFirstLaunch) {
          // 设置消息为自动关闭提示
          setLoadingMessage("初始化完成，正在进入应用...");
          // 略微延迟关闭对话框以便用户能看到成功信息
          setTimeout(() => {
            console.log('[API就绪] 非首次启动：自动关闭对话框');
            onOpenChange(false); // 自动关闭对话框
          }, 800);
        } else {
          // 首次启动时显示就绪消息，等待用户操作
          console.log('[API就绪] 首次启动：显示开始使用按钮');
          setLoadingMessage("后端系统就绪，可以开始使用应用");
        }
      };
      
      startBackendScan();
    } else if (!hasFullDiskAccess) {
      // 如果API就绪但权限不足，仍然阻止进入
      console.log("[API就绪] API就绪但权限不足，阻止进入应用");
      setLoading(false);
    }
  }, [isApiReady, isFirstLaunch, hasFullDiskAccess, onOpenChange]);

  const handleEnterApp = async () => {
    try {
      // 关闭对话框
      onOpenChange(false);
      // 更新状态以便将来不再显示首次启动对话框
      await setShowWelcomeDialog(false);
      console.log('首次启动流程：欢迎对话框已关闭，状态已更新');
    } catch (error) {
      console.error('更新首次启动状态时出错:', error);
    }
  };

  return (
    <Dialog 
      open={open} 
      onOpenChange={(newOpenState) => {
        // 阻止没有权限时关闭对话框
        if (!hasFullDiskAccess && newOpenState === false) {
          console.log("[对话框] 尝试在没有权限时关闭对话框，已阻止");
          toast.error("请先获取完全磁盘访问权限");
          return;
        }
        
        // 如果有权限或是打开操作，正常处理
        if (hasFullDiskAccess || newOpenState === true) {
          onOpenChange(newOpenState);
        }
      }}
    >
      <DialogContent className="sm:max-w-2xl" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-center">欢迎使用 KnowledgeFocus</DialogTitle>
          <DialogDescription className="text-center">
            从文件管理到知识管理
          </DialogDescription>
        </DialogHeader>
        
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
        
        {/* 权限说明 */}
        {!hasFullDiskAccess && !checkingPermission && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-4">
            <p className="text-sm text-yellow-700 mb-2">
              KnowledgeFocus需要完全磁盘访问权限才能正常工作。这将允许应用扫描和索引您的文件，以提供智能文件分类功能。
            </p>
            <p className="text-sm text-yellow-700">
              您的数据文件始终保存在本地，我们不会收集或上传您的文件内容。
            </p>
          </div>
        )}

        <DialogFooter className="flex flex-col sm:flex-row gap-2 sm:gap-0">
          {/* 首次启动且已获得权限时显示"开始使用"按钮 */}
          {isFirstLaunch && hasFullDiskAccess && isApiReady && (
            <Button
              onClick={handleEnterApp}
              className="w-full sm:w-auto text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
            >
              开始使用
            </Button>
          )}
          
          {/* 未获得权限时显示请求权限按钮或重启App按钮 */}
          {!hasFullDiskAccess && !checkingPermission && (
            <Button
              onClick={permissionRequested ? () => relaunch() : requestFullDiskAccess}
              className={`w-full sm:w-auto text-white ${permissionRequested ? 'bg-green-600 hover:bg-green-700' : 'bg-yellow-600 hover:bg-yellow-700'} rounded-lg`}
            >
              {permissionRequested ? "重启App" : "请求磁盘访问权限"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default IntroDialog;
