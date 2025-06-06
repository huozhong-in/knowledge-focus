import { useState, useEffect } from 'react';
import { WiseFoldersService } from './api/wise-folders-service';
import { WiseFolder, WiseFolderCategory } from './types/wise-folder-types';
import WiseFolderView from './wise-folder-view';
import { useAppStore } from './main'; // 导入全局状态
import { Folder, FileIcon, FolderIcon, Calendar, Tag, Database } from 'lucide-react';
import { Button } from "./components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./components/ui/card";
import { Skeleton } from "./components/ui/skeleton";

function HomeWiseFolders() {
  const { isApiReady } = useAppStore(); // 使用全局API准备状态
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<WiseFolderCategory[]>([]);
  const [folders, setFolders] = useState<Record<string, WiseFolder[]>>({});
  const [activeTab, setActiveTab] = useState('project');
  const [selectedFolder, setSelectedFolder] = useState<WiseFolder | null>(null);

  // 加载分类
  useEffect(() => {
    // 只有当API就绪时才尝试获取数据
    if (!isApiReady) {
      setLoading(true);
      return;
    }

    const fetchCategories = async () => {
      try {
        setLoading(true);
        const categoriesData = await WiseFoldersService.getCategories();
        setCategories(categoriesData);
        
        // 设置默认活动标签
        if (categoriesData.length > 0) {
          setActiveTab(categoriesData[0].type);
        }
        
        setError(null);
      } catch (err) {
        setError('获取智慧文件夹分类失败');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchCategories();
  }, [isApiReady]); // 依赖isApiReady，当API就绪状态改变时重新执行

  // 当活动标签改变时加载对应分类的文件夹
  useEffect(() => {
    if (!isApiReady || !activeTab) return;
    
    const fetchFolders = async () => {
      try {
        if (!folders[activeTab]) {
          setLoading(true);
        }
        
        const foldersData = await WiseFoldersService.getFoldersByCategory(activeTab);
        
        setFolders(prev => ({
          ...prev,
          [activeTab]: foldersData
        }));
        
        setError(null);
      } catch (err) {
        setError(`加载${activeTab}分类下的智慧文件夹失败`);
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchFolders();
  }, [isApiReady, activeTab]);

  // 选择文件夹显示内容
  const handleFolderClick = (folder: WiseFolder) => {
    setSelectedFolder(folder);
  };

  // 返回文件夹列表
  const handleBackToList = () => {
    setSelectedFolder(null);
  };

  // 获取图标
  const getFolderIcon = (type: string) => {
    switch (type) {
      case 'project':
        return <Database className="h-6 w-6 text-blue-500" />;
      case 'category':
        return <FileIcon className="h-6 w-6 text-green-500" />;
      case 'tag':
        return <Tag className="h-6 w-6 text-purple-500" />;
      case 'time':
        return <Calendar className="h-6 w-6 text-amber-500" />;
      default:
        return <FolderIcon className="h-6 w-6 text-gray-500" />;
    }
  };

  // 获取分类名称
  const getCategoryName = (type: string) => {
    const category = categories.find(c => c.type === type);
    return category ? category.name : getFolderTypeName(type);
  };

  // 获取分类名称（备用方法）
  const getFolderTypeName = (type: string) => {
    switch (type) {
      case 'project':
        return '项目';
      case 'category':
        return '文件类型';
      case 'tag':
        return '标签';
      case 'time':
        return '时间';
      case 'other':
        return '其他';
      default:
        return '分类';
    }
  };

  // 渲染文件夹列表
  const renderFoldersList = (categoryType: string) => {
    const foldersList = folders[categoryType] || [];
    
    if (foldersList.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center h-40 text-gray-500">
          <FolderIcon className="h-16 w-16 mb-2" />
          <p>没有找到{getCategoryName(categoryType)}分类</p>
        </div>
      );
    }
    
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {foldersList.map((folder, index) => (
          <Card 
            key={`${folder.type}-${index}`}
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => handleFolderClick(folder)}
          >
            <CardHeader>
              <div className="flex items-center space-x-2">
                {getFolderIcon(folder.type)}
                <CardTitle>{folder.name}</CardTitle>
              </div>
              <CardDescription>{folder.description || '智慧归类的文件集合'}</CardDescription>
            </CardHeader>
            <CardFooter>
              <p className="text-sm text-gray-600">{folder.count || folder.file_count || 0} 个文件</p>
            </CardFooter>
          </Card>
        ))}
      </div>
    );
  };

  // 渲染加载状态
  const renderLoading = () => (
    <div className="space-y-4">
      {!isApiReady ? (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-amber-500 mb-4"></div>
          <p className="text-lg text-amber-700">等待后端服务启动...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i}>
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <Skeleton className="h-6 w-6 rounded-full" />
                  <Skeleton className="h-4 w-40" />
                </div>
                <Skeleton className="h-3 w-full mt-2" />
              </CardHeader>
              <CardFooter>
                <Skeleton className="h-3 w-16" />
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  // 渲染错误状态
  const renderError = () => (
    <div className="flex flex-col items-center justify-center h-40 p-4 bg-red-50 rounded-md border border-red-200 text-red-700">
      <p className="text-xl font-semibold mb-2">加载失败</p>
      <p>{error}</p>
      <Button 
        variant="outline" 
        className="mt-4"
        onClick={() => window.location.reload()}
      >
        重试
      </Button>
    </div>
  );

  // 主渲染函数
  return (
    <div className="container mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold mb-6 flex items-center space-x-3">
        <Folder className="h-7 w-7" />
        <span>智慧文件夹</span>
      </h1>
      
      {selectedFolder ? (
        <div>
          <Button
            variant="ghost"
            className="mb-4"
            onClick={handleBackToList}
          >
            ← 返回所有文件夹
          </Button>
          <WiseFolderView 
            folder={selectedFolder} 
          />
        </div>
      ) : (
        <>
          {loading && !Object.keys(folders).length ? (
            renderLoading()
          ) : error ? (
            renderError()
          ) : (
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="mb-6">
                {categories.map(category => (
                  <TabsTrigger 
                    key={category.type} 
                    value={category.type} 
                    className="flex items-center gap-2"
                  >
                    {getFolderIcon(category.type)}
                    {category.name} ({category.folder_count})
                  </TabsTrigger>
                ))}
              </TabsList>
              {categories.map(category => (
                <TabsContent key={category.type} value={category.type}>
                  {renderFoldersList(category.type)}
                </TabsContent>
              ))}
            </Tabs>
          )}
        </>
      )}
    </div>
  );
}

export default HomeWiseFolders;