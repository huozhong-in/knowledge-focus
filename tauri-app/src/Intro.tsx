import React from 'react';
import { useAppStore } from './main';
import { Button } from "./components/ui/button";
import "./index.css";

const Intro: React.FC = () => {
  const setShowIntroPage = useAppStore(state => state.setShowIntroPage);
  const showIntroPage = useAppStore(state => state.showIntroPage);

  const handleEnterApp = async () => {
    try {
      console.log('当前状态:', showIntroPage);
      setShowIntroPage(false);
      console.log('状态已更新');
    } catch (error) {
      console.error('更新状态时出错:', error);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-100 p-4">
      <div className="max-w-2xl w-full bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-3xl font-bold text-center mb-6">欢迎使用 Knowledge Focus</h1>
        
        <div className="space-y-4 mb-8">
          <div className="text-lg">
            <h2 className="font-semibold mb-2">主要功能：</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>高效的知识管理</li>
              <li>智能笔记整理</li>
              <li>快速检索功能</li>
              <li>多设备同步</li>
            </ul>
          </div>
          
          <div className="text-lg">
            <h2 className="font-semibold mb-2">使用提示：</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>使用快捷键提高效率</li>
              <li>定期备份重要数据</li>
              <li>合理组织知识结构</li>
            </ul>
          </div>
        </div>

        <div className="text-center">
          <Button
            onClick={handleEnterApp}
            className="px-8 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
          >
            开始使用
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Intro;