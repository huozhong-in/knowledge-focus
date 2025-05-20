import { useEffect, useState } from "react";
import { FileScreeningResult } from "./types/file-types";
import { format, subDays } from "date-fns";
import { zhCN } from "date-fns/locale";
import { FileService } from "./api/file-service";

// 文件类型定义
export interface FullDiskFolder {
  id: string;
  title: string;
  files: FileScreeningResult[];
  count: number;
  icon: string;
  timeRange?: string; // 例如："today", "last7days", "last30days"
  categoryId?: number; // 对应文件分类ID
}

// 格式化文件大小的辅助函数
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
};

// 按时间筛选函数
export const filterFilesByTime = (files: FileScreeningResult[], timeRange: string): FileScreeningResult[] => {
  const now = new Date();
  
  switch (timeRange) {
    case "today": {
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      return files.filter(file => new Date(file.modified_time) >= today);
    }
    case "last7days":
      return files.filter(file => new Date(file.modified_time) >= subDays(now, 7));
    case "last30days":
      return files.filter(file => new Date(file.modified_time) >= subDays(now, 30));
    default:
      return files;
  }
};

// 按文件分类筛选函数 
// 注意：下面的两个函数仅保留参考，实际的文件筛选工作现在在 Rust 实现
export const filterFilesByCategory = (files: FileScreeningResult[], categoryId: number): FileScreeningResult[] => {
  return files.filter(file => file.category_id === categoryId);
};

// 注意：以下函数现在被更高效的方法替代，但保留供参考
// 格式化当前日期
// const currentDate = format(new Date(), "yyyy年MM月dd日", { locale: zhCN });
//     {
//       id: "audio-video-files",
//       title: `音视频文件: 共${audioVideoFiles.length}个音视频文件`,
//       files: audioVideoFiles,
//       count: audioVideoFiles.length,
//       icon: "🎬",
//       categoryId: 3
//     },
//     {
//       id: "archive-files",
//       title: `压缩包文件: 共${archiveFiles.length}个压缩包文件`,
//       files: archiveFiles,
//       count: archiveFiles.length,
//       icon: "🗃️",
//       categoryId: 4
//     }
//   ];
// };

export const usePinnedFolders = () => {
  const [fullDiskFolders, setFullDiskFolders] = useState<FullDiskFolder[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const refreshInterval = 60000; // 默认1分钟

  // 定义获取结果的函数
  const fetchScreeningResults = async (showLoading = false) => {
    try {
      // 根据参数决定是否显示加载状态
      if (showLoading) {
        setLoading(true);
      }
      
      // 获取不同类型的文件
      const [todayFiles, last7DaysFiles, last30DaysFiles, imageFiles, audioVideoFiles, archiveFiles] = await Promise.all([
        FileService.getFileScreeningResults(1000, undefined, "today"),
        FileService.getFileScreeningResults(1000, undefined, "last7days"),
        FileService.getFileScreeningResults(1000, undefined, "last30days"),
        FileService.getFileScreeningResults(1000, 2), // 图片文件类别ID = 2
        FileService.getFileScreeningResults(1000, 3), // 音视频文件类别ID = 3
        FileService.getFileScreeningResults(1000, 4)  // 压缩包文件类别ID = 4
      ]);
      
      // 格式化当前日期
      const currentDate = format(new Date(), "yyyy年MM月dd日", { locale: zhCN });
      
      // 手动创建智慧文件夹
      const folders: FullDiskFolder[] = [
        {
          id: "today",
          title: `今日更新: ${currentDate}修改了${todayFiles.length}个文件`,
          files: todayFiles,
          count: todayFiles.length,
          icon: "📆",
          timeRange: "today"
        },
        {
          id: "last7days",
          title: `本周动态: 近7天有${last7DaysFiles.length}个文件更新`,
          files: last7DaysFiles,
          count: last7DaysFiles.length,
          icon: "📊",
          timeRange: "last7days"
        },
        {
          id: "last30days",
          title: `本月回顾: 近30天有${last30DaysFiles.length}个文件更新`,
          files: last30DaysFiles,
          count: last30DaysFiles.length,
          icon: "📅",
          timeRange: "last30days"
        },
        {
          id: "image-files",
          title: `图片文件: 共${imageFiles.length}个图片文件`,
          files: imageFiles,
          count: imageFiles.length,
          icon: "🖼️",
          categoryId: 2
        },
        {
          id: "audio-video-files",
          title: `音视频文件: 共${audioVideoFiles.length}个音视频文件`,
          files: audioVideoFiles,
          count: audioVideoFiles.length,
          icon: "🎬",
          categoryId: 3
        },
        {
          id: "archive-files",
          title: `压缩包文件: 共${archiveFiles.length}个压缩包文件`,
          files: archiveFiles,
          count: archiveFiles.length,
          icon: "🗃️",
          categoryId: 4
        }
      ];
      
      setFullDiskFolders(folders);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error("获取文件筛选结果失败:", err);
      setError(`获取文件筛选结果失败: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  // 手动刷新方法，展示加载指示器
  const refreshData = () => {
    fetchScreeningResults(true);
  };

  useEffect(() => {
    // 初始加载，显示加载状态
    fetchScreeningResults(true);
    
    // 设置定期刷新，后台静默更新
    const intervalId = setInterval(() => fetchScreeningResults(false), refreshInterval);
    
    // 添加窗口焦点事件监听，当用户重新关注窗口时刷新数据
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchScreeningResults(false);
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  return { 
    fullDiskFolders: fullDiskFolders, 
    loading, 
    error, 
    refreshData,
    lastUpdated
  };
};

// 导出FullDiskFolderView组件
export const FullDiskFolderView = ({ folderId }: { folderId: string }) => {
  const { fullDiskFolders, loading, error, refreshData, lastUpdated } = usePinnedFolders();
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest' | 'name' | 'size'>('newest');
  
  if (loading && !lastUpdated) return (
    <div className="flex justify-center items-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      <span className="ml-3">加载中...</span>
    </div>
  );
  
  if (error) return (
    <div className="p-8 text-center">
      <div className="text-red-500 text-lg">出现错误</div>
      <p className="mt-2 text-gray-600">{error}</p>
      <button 
        className="mt-4 px-4 py-2 bg-primary text-white rounded hover:bg-primary/80 transition-colors"
        onClick={() => refreshData()}
      >
        重试
      </button>
    </div>
  );
  
  const folder = fullDiskFolders.find(folder => folder.id === folderId);
  
  if (!folder) return (
    <div className="p-8 text-center text-gray-500">
      <div className="text-2xl mb-2">⚠️</div>
      未找到此文件夹
    </div>
  );
  
  // 文件夹存在但文件列表为空
  if (folder.files.length === 0) {
    return (
      <div className="p-8 text-center">
        <div className="text-gray-500 mb-4">暂无文件</div>
        <p className="mb-4">此文件夹中没有匹配的文件</p>
        <div className="text-xs text-gray-400">
          {lastUpdated && `最后更新于 ${new Date(lastUpdated).toLocaleString('zh-CN')}`}
        </div>
        <button 
          className="mt-4 px-4 py-2 bg-primary text-white rounded hover:bg-primary/80 transition-colors"
          onClick={() => refreshData()}
        >
          刷新
        </button>
      </div>
    );
  }
  
  // 按条件排序的文件
  const sortedFiles = [...folder.files].sort((a, b) => {
    switch (sortOrder) {
      case 'newest':
        return new Date(b.modified_time).getTime() - new Date(a.modified_time).getTime();
      case 'oldest':
        return new Date(a.modified_time).getTime() - new Date(b.modified_time).getTime();
      case 'name':
        return a.file_name.localeCompare(b.file_name);
      case 'size':
        return b.file_size - a.file_size;
      default:
        return 0;
    }
  });
  
  return (
    <div className="p-4">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <span>{folder.icon}</span> {folder.title}
        </h2>
        
        <div className="flex flex-col md:flex-row items-end md:items-center gap-2 md:gap-4 mt-2 md:mt-0">
          {lastUpdated && (
            <div className="text-xs text-gray-500">
              上次更新: {format(lastUpdated, "HH:mm:ss")}
            </div>
          )}
          
          <div className="flex items-center gap-2">
            <button
              className="p-1.5 rounded-full hover:bg-gray-100 text-gray-600 disabled:opacity-50"
              onClick={refreshData}
              disabled={loading}
              title="刷新"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            
            <select 
              className="px-3 py-1.5 border border-gray-200 rounded-md bg-white text-sm"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as any)}
            >
              <option value="newest">最新修改</option>
              <option value="oldest">最早修改</option>
              <option value="name">文件名</option>
              <option value="size">文件大小</option>
            </select>
          </div>
        </div>
      </div>
      
      {sortedFiles.length > 0 ? (
        <div className="grid gap-3">
          {sortedFiles.map((file) => (
            <div
              key={file.id}
              className="p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow border border-gray-100"
            >
              <div className="flex justify-between">
                <h3 className="font-medium truncate flex-1" title={file.file_name}>
                  {file.file_name}
                </h3>
                <span className="text-xs text-gray-500 ml-2 whitespace-nowrap">
                  {format(new Date(file.modified_time), "yyyy-MM-dd HH:mm")}
                </span>
              </div>
              <div className="text-sm text-gray-600 truncate mt-1" title={file.file_path}>
                {file.file_path}
              </div>
              <div className="mt-2 flex items-center justify-between">
                {file.extension && (
                  <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                    {file.extension}
                  </span>
                )}
                <span className="text-xs text-gray-500">
                  {formatFileSize(file.file_size)}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 bg-gray-50 rounded-lg border border-gray-200">
          <div className="text-4xl mb-2">📂</div>
          <div className="text-gray-500">未找到符合条件的文件</div>
        </div>
      )}
    </div>
  );
};

export default usePinnedFolders;