import React, { useState, useEffect } from 'react';
import { useAppStore } from '../main';
import { usePageStore } from '../App';
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface IntroDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const IntroDialog: React.FC<IntroDialogProps> = ({ open, onOpenChange }) => {
  // 使用引用而不是解构来避免无限循环问题
  const appStore = useAppStore();
  const setPage = usePageStore(state => state.setPage);
  const [loading, setLoading] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState("正在初始化后端系统...");
  
  // 使用全局状态的 isApiReady 值而不是直接监听事件
  useEffect(() => {
    // 当 API 就绪时
    if (appStore.isApiReady) {
      setLoading(false); // 更新本地加载状态
      
      // 处理非首次启动的逻辑
      if (!appStore.isFirstLaunch) {
        // 设置消息为自动关闭提示
        setLoadingMessage("初始化完成，正在进入应用...");
        // 略微延迟关闭对话框以便用户能看到成功信息
        setTimeout(() => {
          console.log('非首次启动：自动关闭对话框');
          onOpenChange(false); // 自动关闭对话框
        }, 800);
      } else {
        // 首次启动时显示就绪消息，等待用户操作
        setLoadingMessage("后端系统就绪，可以开始使用应用");
      }
    }
  }, [appStore.isApiReady, appStore.isFirstLaunch, onOpenChange]);

  const handleEnterApp = async () => {
    try {
      // 关闭对话框
      onOpenChange(false);
      // 更新状态以便将来不再显示首次启动对话框
      await appStore.setShowWelcomeDialog(false);
      // 导航到文件夹授权页面（仅在首次启动时需要）
      setPage("home-authorization", "Home", "Authorization");
      console.log('首次启动流程：欢迎对话框已关闭，状态已更新，跳转到文件夹授权页面');
    } catch (error) {
      console.error('更新首次启动状态时出错:', error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-center">欢迎使用 Knowledge Focus</DialogTitle>
          <DialogDescription className="text-center">
            让知识管理变得更加简单高效
          </DialogDescription>
        </DialogHeader>
        
        {/* 加载指示器 */}
        {loading && (
          <div className="flex justify-center items-center my-4">
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
          </div>
        )}
        
        <p className={`text-center mb-4 ${appStore.isApiReady ? "text-green-600" : "text-whiskey-700 animate-pulse"}`}>
          {loadingMessage}
        </p>

        <DialogFooter>
          {/* 只在首次启动时显示按钮 */}
          {appStore.isFirstLaunch && (
            <Button
              onClick={handleEnterApp}
              disabled={loading || !appStore.isApiReady} 
              className={`w-full sm:w-auto text-white rounded-lg ${loading || !appStore.isApiReady 
                ? "bg-gray-400 cursor-not-allowed" 
                : "bg-blue-600 hover:bg-blue-700"}`}
            >
              开始使用
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default IntroDialog;
