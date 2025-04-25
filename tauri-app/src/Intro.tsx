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
              <li>文件管理新生代！人工智能加持的文档看板，帮你轻松管理散落各处的文档。</li>
              <li>建立个人知识库！仅通过跟文件聊天方式完成知识的抽取和提炼，让知识彼此关联形成网状结构。</li>
              <li>开放的导出能力！智能组合知识片段导出文件，给到商业应用使用，充分利用其先进的模型能力和产品形态。</li>
            </ul>
          </div>
          
          <div className="text-lg">
            <h2 className="font-semibold mb-2">使用提示：</h2>
            <ul className="list-disc list-inside space-y-2">
              <li>请授权本应用读取您的各个文档文件夹</li>
              <li>首次启动需要下载本地小模型，请您耐心等待...</li>
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