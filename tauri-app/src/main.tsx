import React from "react";
import ReactDOM from "react-dom/client";
import { create } from 'zustand';
import { load } from '@tauri-apps/plugin-store';
import { TrayIcon } from '@tauri-apps/api/tray';
import { resourceDir, join, appDataDir } from '@tauri-apps/api/path';
import App from "./App";
import { setupI18nWithStore } from './i18n';
import { ThemeProvider } from "./tweakcn/components/theme-provider";

// // 导入工具初始化模块
// import './lib/initializeTools';

interface AppGlobalState {
  // For UI state management during first launch
  // isInitializing: boolean; 
  // initializationError: string | null;

  // API readiness state
  isApiReady: boolean; // New state
  
  // 语言设置
  language: string;
  
  // 更新相关状态
  updateAvailable: boolean;
  updateVersion: string | null;
  updateNotes: string | null;
  downloadProgress: number; // 0-100
  isDownloading: boolean;
  isReadyToInstall: boolean;
  lastUpdateCheck: number | null; // timestamp
  updateError: string | null;
  
  // Actions
  // setIsInitializing: (initializing: boolean) => void;
  // setInitializationError: (error: string | null) => void;
  setApiReady: (ready: boolean) => void; // New action
  
  // 语言相关操作
  setLanguage: (lang: string) => Promise<void>;
  
  // 更新相关操作
  setUpdateAvailable: (available: boolean, version?: string, notes?: string) => void;
  setDownloadProgress: (progress: number) => void;
  setIsDownloading: (downloading: boolean) => void;
  setIsReadyToInstall: (ready: boolean) => void;
  setLastUpdateCheck: (timestamp: number) => Promise<void>;
  setUpdateError: (error: string | null) => void;
  resetUpdateState: () => void;
}

// 设置系统托盘图标
async function setTrayIcon() {
  let newIconPath;
  
  if (import.meta.env.MODE === 'development') {
    newIconPath = await join(await resourceDir(), '../../../mac-tray-icon.png');
  } else {
    newIconPath = await join(await resourceDir(), 'mac-tray-icon.png');
  }
  
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
  isApiReady: false, // Initialize API as not ready
  language: 'en', // 默认使用英文
  // 更新相关状态初始值
  updateAvailable: false,
  updateVersion: null,
  updateNotes: null,
  downloadProgress: 0,
  isDownloading: false,
  isReadyToInstall: false,
  lastUpdateCheck: null,
  updateError: null,

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
  },

  // 更新相关操作实现
  setUpdateAvailable: (available: boolean, version?: string, notes?: string) => 
    set({ 
      updateAvailable: available, 
      updateVersion: version || null, 
      updateNotes: notes || null,
      updateError: null // 清除之前的错误
    }),
  
  setDownloadProgress: (progress: number) => set({ downloadProgress: progress }),
  
  setIsDownloading: (downloading: boolean) => set({ isDownloading: downloading }),
  
  setIsReadyToInstall: (ready: boolean) => set({ isReadyToInstall: ready }),
  
  setLastUpdateCheck: async (timestamp: number) => {
    try {
      set({ lastUpdateCheck: timestamp });
      
      // 保存到settings.json
      const appDataPath = await appDataDir();
      const storePath = await join(appDataPath, 'settings.json');
      const store = await load(storePath, { autoSave: false });
      
      await store.set('lastUpdateCheck', timestamp);
      await store.save();
      console.log(`Last update check saved: ${new Date(timestamp).toISOString()}`);
      
    } catch (error) {
      console.error('Failed to save last update check:', error);
    }
  },
  
  setUpdateError: (error: string | null) => set({ updateError: error }),
  
  resetUpdateState: () => set({
    updateAvailable: false,
    updateVersion: null,
    updateNotes: null,
    downloadProgress: 0,
    isDownloading: false,
    isReadyToInstall: false,
    updateError: null
  })
}));

// 初始化检查是否首次启动
const initializeApp = async () => {
  try {
    // 初始化系统托盘图标
    await setTrayIcon();
    
    const appDataPath = await appDataDir();
    const storePath = await join(appDataPath, 'settings.json');
    const store = await load(storePath, { autoSave: false });
    
    // 获取保存的语言设置
    const savedLanguage = await store.get('language') as string | null;
    const language = savedLanguage || 'en'; // 如果没有保存语言设置，默认使用英文

    // 获取上次更新检查时间
    const savedLastUpdateCheck = await store.get('lastUpdateCheck') as number | null;


    console.log(`initializeApp: Loaded language preference: ${language}`);
    console.log(`initializeApp: Last update check: ${savedLastUpdateCheck ? new Date(savedLastUpdateCheck).toISOString() : 'never'}`);
    
    // Set initial Zustand states based on whether it's the first launch
    useAppStore.setState({ 
      isApiReady: false,     // API is not ready at this point
      language: language,    // 设置语言
      lastUpdateCheck: savedLastUpdateCheck // 设置上次更新检查时间
    });

    // 设置 i18n 和 Zustand store 的集成
    setupI18nWithStore(useAppStore);

    // 渲染应用
    ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
      <React.StrictMode>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </React.StrictMode>
    );
  } catch (error) {
    console.error('Failed to initialize app:', error);
  }
};

// 启动应用
initializeApp();

document.addEventListener("DOMContentLoaded", () => {
  const dragRegionDiv = document.createElement("div");
  dragRegionDiv.setAttribute("data-tauri-drag-region", "");
  dragRegionDiv.className = "dragble-state";
  document.documentElement.insertBefore(dragRegionDiv, document.body);
});
