import React from "react";
import ReactDOM from "react-dom/client";
import { create } from 'zustand';
import { load } from '@tauri-apps/plugin-store';
import { TrayIcon } from '@tauri-apps/api/tray';
import { resourceDir, join, appDataDir } from '@tauri-apps/api/path';
import App from "./App";

interface AppGlobalState {
  showWelcomeDialog: boolean;
  setShowWelcomeDialog: (show: boolean) => Promise<void>;

  // For UI state management during first launch
  isFirstLaunch: boolean;
  isInitializing: boolean; 
  initializationError: string | null;

  // API readiness state
  isApiReady: boolean; // New state

  // Actions
  setFirstLaunch: (pending: boolean) => void;
  setIsInitializing: (initializing: boolean) => void;
  setInitializationError: (error: string | null) => void;
  setApiReady: (ready: boolean) => void; // New action
}


// 设置系统托盘图标
async function setTrayIcon() {
  let newIconPath;
  
  if (import.meta.env.MODE === 'development') {
    // console.log("当前环境: 开发");
    newIconPath = await join(await resourceDir(), '../../../mac-tray-icon.png');
  } else {
    newIconPath = await join(await resourceDir(), 'mac-tray-icon.png');
  }
  
  // console.log("图标路径:", newIconPath);
  
  if (newIconPath) {
    const tray = await TrayIcon.getById("1");
    if (!tray) {
      console.error("托盘图标未找到");
      return;
    }
    tray.setIcon(newIconPath);
    tray.setTooltip("Knowledge Focus");
  }
}

// 创建 Zustand store
export const useAppStore = create<AppGlobalState>((set) => ({
  showWelcomeDialog: true, // 默认显示介绍页
  isFirstLaunch: false,
  isInitializing: false, // Will be set to true by initializeApp
  initializationError: null,
  isApiReady: false, // Initialize API as not ready

  setShowWelcomeDialog: async (show: boolean) => {
    try {
      const appDataPath = await appDataDir();
      const storePath = await join(appDataPath, 'settings.json');
      const store = await load(storePath, { autoSave: false });
      
      // 先更新zustand状态
      set({ showWelcomeDialog: show });
      
      if (!show) { // 用户关闭欢迎对话框，标记首次启动已完成
        // 更新持久化存储，标记应用已至少启动过一次
        await store.set('isFirstLaunch', false);
        await store.save();
        console.log('settings.json updated: isFirstLaunch=false.');
      }
    } catch (error) {
      console.error('Failed to update store in setShowWelcomeDialog:', error);
      // Even if store op fails, update UI state.
      set({ showWelcomeDialog: show });
    }
  },
  setFirstLaunch: (pending: boolean) => set({ isFirstLaunch: pending }),
  setIsInitializing: (initializing: boolean) => set({ isInitializing: initializing }),
  setInitializationError: (error: string | null) => set({ initializationError: error }),
  setApiReady: (ready: boolean) => set({ isApiReady: ready }), // Implement new action
}));

// Root组件现在直接渲染主应用，不再条件渲染Intro页面
const Root: React.FC = () => {
  // 直接渲染App组件，欢迎信息已改为Dialog形式
  return <App />;
};

// 初始化检查是否首次启动
const initializeApp = async () => {
  try {
    // 初始化系统托盘图标
    await setTrayIcon();
    
    const appDataPath = await appDataDir();
    const storePath = await join(appDataPath, 'settings.json');
    const store = await load(storePath, { autoSave: false });
    const isFirstLaunchValue = await store.get('isFirstLaunch');
    const isActuallyFirstLaunch = isFirstLaunchValue === null || isFirstLaunchValue === undefined || isFirstLaunchValue === true;
    
    console.log(`initializeApp: isFirstLaunchValue from store: ${isFirstLaunchValue}, isActuallyFirstLaunch: ${isActuallyFirstLaunch}`);
    
    // Set initial Zustand states based on whether it's the first launch
    useAppStore.setState({ 
      showWelcomeDialog: isActuallyFirstLaunch,
      isFirstLaunch: isActuallyFirstLaunch,
      isInitializing: true, // Start in initializing state
      isApiReady: false     // API is not ready at this point
    });

    // 渲染应用
    ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
      <React.StrictMode>
        <Root />
      </React.StrictMode>
    );
  } catch (error) {
    console.error('Failed to initialize app:', error);
  }
};

// 启动应用
initializeApp();
