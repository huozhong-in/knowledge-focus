import { useEffect, useState } from "react";
import { format } from "date-fns";
import { zhCN } from "date-fns/locale";
import { FileScannerService, FileInfo, TimeRange, FileType } from "./api/file-scanner-service";

// 文件类型定义
export interface FullDiskFolder {
  id: string;
  title: string;
  files: FileInfo[];
  count: number;
  icon: string;
  timeRange?: TimeRange; // 例如："today", "last7days", "last30days"
  fileType?: FileType; // 例如："image", "audio-video", "archive"
}

// Use FileScannerService's formatFileSize function
export const formatFileSize = FileScannerService.formatFileSize;

// Simple in-memory cache
const fileCache: Map<string, { data: FileInfo[], timestamp: number }> = new Map();
const CACHE_DURATION = 5 * 60 * 1000; // Cache for 5 minutes

// Hook to fetch data for a single pinned folder
export const usePinnedFolderData = (folderId: string) => {
  const [folderData, setFolderData] = useState<FullDiskFolder | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchFolderData = async (showLoading = false) => {
    if (!folderId) {
      setFolderData(null);
      setLoading(false);
      return;
    }

    // Check cache first
    const cached = fileCache.get(folderId);
    if (cached && (Date.now() - cached.timestamp < CACHE_DURATION)) {
      console.log(`[CACHE] Using cached data for folder: ${folderId}`);
      // Reconstruct FullDiskFolder from cached data and definition
      const definition = getFolderDefinition(folderId); // Need a way to get definition by ID
      if (definition) {
         setFolderData({
            id: folderId,
            title: definition.name, // Use name from definition for title
            files: cached.data,
            count: cached.data.length,
            icon: definition.icon, // Use icon from definition
            timeRange: definition.timeRange,
            fileType: definition.fileType,
         });
         setLastUpdated(new Date(cached.timestamp));
         setError(null);
         setLoading(false);
         return;
      }
    }

    try {
      if (showLoading) {
        setLoading(true);
      }

      let files: FileInfo[] = [];
      let title = "";
      let icon = "";
      let timeRange: TimeRange | undefined;
      let fileType: FileType | undefined;

      // Determine which scanner function to call based on folderId
      switch (folderId) {
        case "today":
          files = await FileScannerService.scanFilesByTimeRange(TimeRange.Today);
          title = `今日更新: ${format(new Date(), "yyyy年MM月dd日", { locale: zhCN })}修改了${files.length}个文件`;
          icon = "📆";
          timeRange = TimeRange.Today;
          break;
        case "last7days":
          files = await FileScannerService.scanFilesByTimeRange(TimeRange.Last7Days);
          title = `本周动态: 近7天有${files.length}个文件更新`;
          icon = "📊";
          timeRange = TimeRange.Last7Days;
          break;
        case "last30days":
          files = await FileScannerService.scanFilesByTimeRange(TimeRange.Last30Days);
          title = `本月回顾: 近30天有${files.length}个文件更新`;
          icon = "📅";
          timeRange = TimeRange.Last30Days;
          break;
        case "image": // Corresponds to FileType.Image
          files = await FileScannerService.scanFilesByType(FileType.Image);
          title = `图片文件: 共${files.length}个图片文件`;
          icon = "🖼️";
          fileType = FileType.Image;
          break;
        case "audio-video": // Corresponds to FileType.AudioVideo
          files = await FileScannerService.scanFilesByType(FileType.AudioVideo);
          title = `音视频文件: 共${files.length}个音视频文件`;
          icon = "🎬";
          fileType = FileType.AudioVideo;
          break;
        case "archive": // Corresponds to FileType.Archive
          files = await FileScannerService.scanFilesByType(FileType.Archive);
          title = `压缩包文件: 共${files.length}个压缩包文件`;
          icon = "🗃️";
          fileType = FileType.Archive;
          break;
        default:
          setError(`未知文件夹ID: ${folderId}`);
          setLoading(false);
          return;
      }

      const fetchedData: FullDiskFolder = {
        id: folderId,
        title,
        files,
        count: files.length,
        icon,
        timeRange,
        fileType,
      };

      setFolderData(fetchedData);
      const now = new Date();
      setLastUpdated(now);
      setError(null);

      // Cache the fetched data
      fileCache.set(folderId, { data: files, timestamp: now.getTime() });
      console.log(`[CACHE] Cached data for folder: ${folderId}`);

    } catch (err) {
      console.error(`扫描文件夹 ${folderId} 失败:`, err);
      setError(`扫描文件夹失败: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  // Need a way to get the folder definition (name, icon, type/range) by ID
  // This could be passed as a prop or fetched from a central place.
  // For now, let's define a helper function based on the definitions in app-sidebar.tsx
  const getFolderDefinition = (id: string) => {
      // This should ideally come from a shared place or prop,
      // but for now, hardcoding based on app-sidebar definitions
      const definitions = [
          { id: "today", name: "今日更新", icon: "📆", timeRange: TimeRange.Today },
          { id: "last7days", name: "最近7天", icon: "📊", timeRange: TimeRange.Last7Days },
          { id: "last30days", name: "最近30天", icon: "📅", timeRange: TimeRange.Last30Days },
          { id: "image", name: "图片文件", icon: "🖼️", fileType: FileType.Image },
          { id: "audio-video", name: "音视频文件", icon: "🎬", fileType: FileType.AudioVideo },
          { id: "archive", name: "归档文件", icon: "🗃️", fileType: FileType.Archive },
      ];
      // Map icon strings to LucideIcon components if needed for FullDiskFolderView
      // For now, assuming icon is just a string or handled by the view component
      return definitions.find(def => def.id === id);
  };


  useEffect(() => {
    fetchFolderData(true); // Fetch data when folderId changes or component mounts
  }, [folderId]); // Re-fetch when folderId changes

  // Manual refresh function
  const refreshData = () => {
      // Invalidate cache for this folder before fetching
      fileCache.delete(folderId);
      console.log(`[CACHE] Invalidated cache for folder: ${folderId}`);
      fetchFolderData(true);
  };


  return {
    folderData,
    loading,
    error,
    refreshData,
    lastUpdated,
  };
};


// Export FullDiskFolderView component - needs to use usePinnedFolderData
export const FullDiskFolderView = ({ folderId }: { folderId: string }) => {
  // Use the new hook to fetch data for the specific folderId
  const { folderData, loading, error, refreshData, lastUpdated } = usePinnedFolderData(folderId);
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest' | 'name' | 'size'>('newest');

  // Show loading state if data is being fetched and no previous data exists
  if (loading && !folderData) return (
    <div className="flex justify-center items-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      <span className="ml-3">加载中...</span>
    </div>
  );

  // Show error state
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

  // If folderData is null (e.g., invalid folderId)
  if (!folderData) return (
      <div className="p-8 text-center text-gray-500">
        <div className="text-2xl mb-2">⚠️</div>
        未找到此文件夹或数据
      </div>
  );


  // Folder exists but file list is empty
  if (folderData.files.length === 0) {
    return (
      <div className="p-8 text-center">
        <div className="text-gray-500 mb-4">暂无文件</div>
        <p className="mb-4">此文件夹中没有匹配的文件</p>
        <div className="text-xs text-gray-400">
          {lastUpdated && `最后更新于 ${format(lastUpdated, 'yyyy-MM-dd HH:mm:ss', { locale: zhCN })}`}
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

  // Sort files based on sortOrder
  const sortedFiles = [...folderData.files].sort((a, b) => {
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
          {/* Assuming folderData.icon is a string or handled by the view */}
          <span>{folderData.icon}</span> {folderData.title}
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
          {sortedFiles.map((file, index) => (
            <div
              key={file.file_path + '_' + index}
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
                  {FileScannerService.formatFileSize(file.file_size)}
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

// Export the new hook as default
export default usePinnedFolderData;
