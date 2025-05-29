import React from "react";
import ReactDOM from "react-dom/client";
import { create } from 'zustand';
import { load } from '@tauri-apps/plugin-store';
import { TrayIcon } from '@tauri-apps/api/tray';
import { resourceDir, join, appDataDir } from '@tauri-apps/api/path';
import App from "./App";

interface AppGlobalState {
  showIntroPage: boolean;
  setShowIntroPage: (show: boolean) => Promise<void>; // Make it explicitly Promise

  // For UI state management during first launch
  isFirstLaunchDbCheckPending: boolean;
  isDbInitializing: boolean; 
  dbInitializationError: string | null;

  // Actions
  setFirstLaunchDbCheckPending: (pending: boolean) => void;
  setIsDbInitializing: (initializing: boolean) => void;
  setDbInitializationError: (error: string | null) => void;
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
  showIntroPage: true, // 默认显示介绍页
  isFirstLaunchDbCheckPending: false,
  isDbInitializing: false,
  dbInitializationError: null,

  setShowIntroPage: async (show: boolean) => {
    try {
      const appDataPath = await appDataDir();
      const storePath = await join(appDataPath, 'settings.json');
      const store = await load(storePath, { autoSave: false });
      
      // 先更新zustand状态
      set({ showIntroPage: show });
      
      if (!show) { // Means user is leaving intro, first launch "acknowledged"
        // Update the persistent store to reflect that the app has been launched at least once.
        await store.set('isFirstLaunch', false);
        await store.save();
        console.log('settings.json updated: isFirstLaunch=false.');
      }
    } catch (error) {
      console.error('Failed to update store in setShowIntroPage:', error);
      // Even if store op fails, update UI state.
      set({ showIntroPage: show });
    }
  },
  setFirstLaunchDbCheckPending: (pending: boolean) => set({ isFirstLaunchDbCheckPending: pending }),
  setIsDbInitializing: (initializing: boolean) => set({ isDbInitializing: initializing }),
  setDbInitializationError: (error: string | null) => set({ dbInitializationError: error }),
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
      showIntroPage: isActuallyFirstLaunch,
      isFirstLaunchDbCheckPending: isActuallyFirstLaunch
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
