import React from "react";
import ReactDOM from "react-dom/client";
import { create } from 'zustand';
import { load } from '@tauri-apps/plugin-store';
import { TrayIcon } from '@tauri-apps/api/tray';
import { resourceDir, join, appDataDir } from '@tauri-apps/api/path';
import Intro from "./Intro";
import App from "./App";

interface AppGlobalState {
  showIntroPage: boolean;
  setShowIntroPage: (show: boolean) => Promise<void>; // Make it explicitly Promise

  // For first launch DB initialization process
  isFirstLaunchDbCheckPending: boolean; // True when app starts, set by initializeApp if it's a first launch
  isDbInitializing: boolean; // True when App.tsx is actively running init_db
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
  isFirstLaunchDbCheckPending: false, // Will be set true if actually first launch
  isDbInitializing: false,
  dbInitializationError: null,

  setShowIntroPage: async (show: boolean) => {
    try {
      const appDataPath = await appDataDir();
      const storePath = await join(appDataPath, 'store.json');
      const store = await load(storePath, { autoSave: false });
      
      // 先更新zustand状态
      set({ showIntroPage: show });
      
      if (!show) { // Means user is leaving intro, first launch "acknowledged"
        // Update the persistent store to reflect that the app has been launched at least once.
        await store.set('isFirstLaunch', false);
        await store.save();
        console.log('store.json updated: isFirstLaunch=false.');
        // isFirstLaunchDbCheckPending remains true; App.tsx will consume and clear it after DB init.
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

// Root组件用于响应式地处理页面切换
const Root: React.FC = () => {
  const showIntroPage = useAppStore(state => state.showIntroPage);
  return showIntroPage ? <Intro /> : <App />;
};

// Exported function to handle database initialization with retries
export const ensureDatabaseInitialized = async (): Promise<boolean> => {
  console.log('Attempting to initialize database upon user action...');
  const maxRetries = 10; // Increased retries, as sidecar might be starting up
  const retryDelay = 2500; // Slightly increased delay (2.5 seconds)
  let retries = 0;
  let dbInitialized = false;

  while (retries < maxRetries && !dbInitialized) {
    try {
      console.log(`Attempting database initialization (Attempt ${retries + 1}/${maxRetries})...`);
      const response = await fetch('http://127.0.0.1:60000/init_db', {
        method: 'POST', // Assuming POST is still correct
      });

      if (response.ok) { // HTTP 状态码 200-299
        console.log('Database initialization successful.');
        dbInitialized = true;
      } else {
        console.error(`Database initialization API request failed (Attempt ${retries + 1}/${maxRetries}): ${response.status} ${response.statusText}`);
        if (retries < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, retryDelay));
        }
      }
    } catch (error) {
      console.error(`Error calling init_db API (Attempt ${retries + 1}/${maxRetries}):`, error);
      if (retries < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, retryDelay));
      }
    }
    retries++;
  }

  if (!dbInitialized) {
    console.error(`Database initialization failed after ${maxRetries} attempts. Please check sidecar service.`);
    alert("数据库初始化失败。Sidecar服务可能未能正确启动或响应。请尝试重启应用。如果问题持续，请检查后台服务。");
  }
  return dbInitialized;
};

// 初始化检查是否首次启动
const initializeApp = async () => {
  try {
    // 初始化系统托盘图标
    await setTrayIcon();
    
    const appDataPath = await appDataDir();
    const storePath = await join(appDataPath, 'store.json');
    const store = await load(storePath, { autoSave: false });
    const isFirstLaunchValue = await store.get('isFirstLaunch');
    const isActuallyFirstLaunch = isFirstLaunchValue === null || isFirstLaunchValue === undefined || isFirstLaunchValue === true;
    
    console.log(`initializeApp: isFirstLaunchValue from store: ${isFirstLaunchValue}, isActuallyFirstLaunch: ${isActuallyFirstLaunch}`);
    
    // Set initial Zustand states based on whether it's the first launch
    useAppStore.setState({ 
      showIntroPage: isActuallyFirstLaunch,
      isFirstLaunchDbCheckPending: isActuallyFirstLaunch // Signal to App.tsx if it needs to run the init sequence
    });

    // 渲染应用
    ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
      <React.StrictMode>
        <Root />
      </React.StrictMode>
    );
  } catch (error) {
    console.error('Failed to initialize app:', error);
    // 如果初始化失败，仍然渲染应用，默认显示介绍页
    ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
      <React.StrictMode>
        <Root />
      </React.StrictMode>
    );
  }
};

// 启动应用
initializeApp();
