import React from "react";
import ReactDOM from "react-dom/client";
import {create} from 'zustand'
import { load } from '@tauri-apps/plugin-store';
import { TrayIcon } from '@tauri-apps/api/tray';
import { resourceDir, join } from '@tauri-apps/api/path';
import Intro from "./Intro";
import App from "./App";

interface MyState {
  showIntroPage: boolean;
  setShowIntroPage: (show: boolean) => void;
}

// 设置系统托盘图标
async function setTrayIcon() {
  let newIconPath;
  
  if (import.meta.env.MODE === 'development') {
    console.log("当前环境: 开发");
    newIconPath = await join(await resourceDir(), '../../../mac-tray-icon.png');
  } else {
    newIconPath = await join(await resourceDir(), 'mac-tray-icon.png');
  }
  
  console.log("图标路径:", newIconPath);
  
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
export const useAppStore = create<MyState>((set) => ({
  showIntroPage: true, // 默认显示介绍页
  setShowIntroPage: async (show: boolean) => {
    try {
      const store = await load('store.json', { autoSave: false });
      console.log('更新前的store值:', await store.get('isFirstLaunch'));
      
      // 先更新zustand状态
      set({ showIntroPage: show });
      console.log('zustand状态已更新');
      
      if (!show) {
        // 再更新持久化存储
        await store.set('isFirstLaunch', false);
        await store.save();
        console.log('store文件已保存');
      }
    } catch (error) {
      console.error('Failed to update store:', error);
      // 即使store操作失败，也要更新zustand状态
      set({ showIntroPage: show });
    }
  },
}));

// Root组件用于响应式地处理页面切换
const Root: React.FC = () => {
  const showIntroPage = useAppStore(state => state.showIntroPage);
  return showIntroPage ? <Intro /> : <App />;
};

// 初始化检查是否首次启动
const initializeApp = async () => {
  try {
    // 初始化系统托盘图标
    await setTrayIcon();
    
    const store = await load('store.json', { autoSave: false });
    const isFirstLaunch = await store.get('isFirstLaunch');
    const showIntro = isFirstLaunch === null || isFirstLaunch === undefined || isFirstLaunch === true;
    useAppStore.setState({ showIntroPage: showIntro });
    
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
