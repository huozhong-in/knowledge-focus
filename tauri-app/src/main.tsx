import React from "react";
import ReactDOM from "react-dom/client";
import { create } from 'zustand';
import { load } from '@tauri-apps/plugin-store';
import { TrayIcon } from '@tauri-apps/api/tray';
import { resourceDir, join, appDataDir } from '@tauri-apps/api/path';
import App from "./App";
import { setupI18nWithStore } from './i18n';

interface AppGlobalState {
  showWelcomeDialog: boolean;
  setShowWelcomeDialog: (show: boolean) => Promise<void>;

  // For UI state management during first launch
  isFirstLaunch: boolean;
  isInitializing: boolean; 
  initializationError: string | null;

  // API readiness state
  isApiReady: boolean; // New state
  
  // 语言设置
  language: string;
  
  
  // Actions
  setFirstLaunch: (pending: boolean) => void;
  setIsInitializing: (initializing: boolean) => void;
  setInitializationError: (error: string | null) => void;
  setApiReady: (ready: boolean) => void; // New action
  
  // 语言相关操作
  setLanguage: (lang: string) => Promise<void>;
  
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
    tray.setTooltip("KnowledgeFocus");
  }
}

// 创建 Zustand store
export const useAppStore = create<AppGlobalState>((set, _get) => ({
  showWelcomeDialog: true, // 默认显示介绍页
  isFirstLaunch: false,
  isInitializing: false, // Will be set to true by initializeApp
  initializationError: null,
  isApiReady: false, // Initialize API as not ready
  language: 'en', // 默认使用英文

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
  
  
  
  // 设置语言并保存到设置文件中
  setLanguage: async (lang: string) => {
    try {
      // 首先更新state
      set({ language: lang });
      
      // 保存到settings.json
      const appDataPath = await appDataDir();
      const storePath = await join(appDataPath, 'settings.json');
      const store = await load(storePath, { autoSave: false });
      
      await store.set('language', lang);
      await store.save();
      console.log(`Language preference saved to settings.json: ${lang}`);
      
    } catch (error) {
      console.error('Failed to save language preference:', error);
    }
  }
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
    
    // 获取保存的语言设置
    const savedLanguage = await store.get('language') as string | null;
    const language = savedLanguage || 'en'; // 如果没有保存语言设置，默认使用英文

    console.log(`initializeApp: isFirstLaunchValue from store: ${isFirstLaunchValue}, isActuallyFirstLaunch: ${isActuallyFirstLaunch}`);
    console.log(`initializeApp: Loaded language preference: ${language}`);
    
    // Set initial Zustand states based on whether it's the first launch
    useAppStore.setState({ 
      showWelcomeDialog: true, // 始终显示欢迎对话框，作为 splash 屏幕
      isFirstLaunch: isActuallyFirstLaunch,
      isInitializing: false, // 不再使用单独的初始化状态，由 IntroDialog 处理
      isApiReady: false,     // API is not ready at this point
      language: language     // 设置语言
    });

    // 设置 i18n 和 Zustand store 的集成
    setupI18nWithStore(useAppStore);

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
