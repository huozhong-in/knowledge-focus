import React from 'react';
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
  const setShowWelcomeDialog = useAppStore(state => state.setShowWelcomeDialog);
  const setPage = usePageStore(state => state.setPage);

  const handleEnterApp = async () => {
    try {
      // 关闭对话框
      onOpenChange(false);
      // 更新状态以便将来不再显示
      await setShowWelcomeDialog(false);
      // 导航到文件夹授权页面
      setPage("home-authorization", "Home", "Authorization");
      console.log('欢迎对话框已关闭，状态已更新，跳转到文件夹授权页面');
    } catch (error) {
      console.error('更新状态时出错:', error);
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

        <div className="space-y-4 my-6">
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
              <li>点击"开始使用"将直接进入文件夹授权管理页面</li>
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleEnterApp}
            className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
          >
            开始使用
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default IntroDialog;
