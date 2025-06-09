import React, { useState, useEffect } from "react";
import { format } from "date-fns";
import { zhCN } from "date-fns/locale";
import { openPath, revealItemInDir } from "@tauri-apps/plugin-opener";
import { 
  File, FileText, Image, Music, Video, FileArchive, FileCode, FilePenLine, 
  FileSpreadsheet, FileX, Copy, Folder, ExternalLink, Search, FolderOpen
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { toast } from "sonner";
import { FileSearchResult } from "@/components/askme-form";
import { useAppStore } from './main';

// 格式化文件大小
const formatFileSize = (size: number): string => {
  if (size < 1024) {
    return `${size} B`;
  } else if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  } else if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  } else {
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  }
};

// 文件类型图标映射
const getFileIcon = (extension?: string | null) => {
  if (!extension) return <FileX size={18} />;
  
  extension = extension.toLowerCase();
  
  // 图片文件
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff'].includes(extension)) {
    return <Image size={18} className="text-blue-500" />;
  }
  
  // 音频文件
  if (['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac'].includes(extension)) {
    return <Music size={18} className="text-purple-500" />;
  }
  
  // 视频文件
  if (['mp4', 'avi', 'mov', 'flv', 'wmv', 'webm', 'mkv', 'm4v'].includes(extension)) {
    return <Video size={18} className="text-pink-500" />;
  }
  
  // 压缩文件
  if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'].includes(extension)) {
    return <FileArchive size={18} className="text-amber-500" />;
  }
  
  // 代码文件
  if (['js', 'ts', 'jsx', 'tsx', 'html', 'css', 'py', 'java', 'c', 'cpp', 'go', 'rs', 'php'].includes(extension)) {
    return <FileCode size={18} className="text-green-500" />;
  }
  
  // 文档文件
  if (['doc', 'docx', 'txt', 'rtf', 'md', 'pdf'].includes(extension)) {
    return <FileText size={18} className="text-sky-500" />;
  }
  
  // 表格文件
  if (['xls', 'xlsx', 'csv'].includes(extension)) {
    return <FileSpreadsheet size={18} className="text-emerald-500" />;
  }
  
  // 其他文本类型
  if (['json', 'xml', 'yaml', 'yml', 'ini', 'conf', 'config'].includes(extension)) {
    return <FilePenLine size={18} className="text-orange-500" />;
  }
  
  // 默认文件图标
  return <File size={18} className="text-gray-500" />;
};

// 文件操作菜单组件
interface FileActionMenuProps {
  file: FileSearchResult;
}

const FileActionMenu: React.FC<FileActionMenuProps> = ({ file }) => {
  const openContainingFolder = async () => {
    try {
      // 获取文件所在的目录后让文件被选中
      await revealItemInDir(file.file_path);
    } catch (error) {
      console.error("打开文件夹失败:", error);
      toast.error("打开文件夹失败");
    }
  };

  const openFileDirectly = async () => {
    try {
      await openPath(file.file_path);
    } catch (error) {
      console.error("打开文件失败:", error);
      toast.error("打开文件失败");
    }
  };

  const copyFilePath = () => {
    navigator.clipboard.writeText(file.file_path)
      .then(() => {
        toast.success("文件路径已复制到剪贴板");
      })
      .catch(err => {
        console.error("复制文件路径失败:", err);
        toast.error("复制文件路径失败");
      });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center justify-center rounded-md p-1 hover:bg-whiskey-100 dark:hover:bg-whiskey-800">
        <ExternalLink size={14} />
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>文件操作</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={openFileDirectly}>
          <File className="mr-2 size-4" />
          打开文件
        </DropdownMenuItem>
        <DropdownMenuItem onClick={openContainingFolder}>
          <FolderOpen className="mr-2 size-4" />
          打开所在文件夹
        </DropdownMenuItem>
        <DropdownMenuItem onClick={copyFilePath}>
          <Copy className="mr-2 size-4" />
          复制文件路径
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

interface SearchResultsProps {
  results: FileSearchResult[];
  searchQuery: string;
}

export const SearchResults: React.FC<SearchResultsProps> = ({ results, searchQuery }) => {
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest' | 'name' | 'size'>('newest');
  const [filterExtension, setFilterExtension] = useState<string>('all');
  const [uniqueExtensions, setUniqueExtensions] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  // 提取所有唯一的文件扩展名
  useEffect(() => {
    if (Array.isArray(results) && results.length > 0) {
      const extensions = results
        .map(file => file.extension)
        .filter((ext): ext is string => !!ext)
        .filter((value, index, self) => self.indexOf(value) === index)
        .sort();
      setUniqueExtensions(extensions);
    } else {
      setUniqueExtensions([]);
    }
  }, [results]);

  // 根据排序和过滤条件处理文件列表
  const processedFiles = React.useMemo(() => {
    // 确保results是一个数组
    if (!Array.isArray(results) || results.length === 0) return [];

    // 先应用过滤
    let filtered = results;
    if (filterExtension !== 'all') {
      filtered = results.filter(file => file.extension === filterExtension);
    }

    // 再应用排序
    return [...filtered].sort((a, b) => {
      switch (sortOrder) {
        case 'newest':
          return new Date(b.modified_time || 0).getTime() - new Date(a.modified_time || 0).getTime();
        case 'oldest':
          return new Date(a.modified_time || 0).getTime() - new Date(b.modified_time || 0).getTime();
        case 'name':
          return a.file_name.localeCompare(b.file_name);
        case 'size':
          return b.file_size - a.file_size;
        default:
          return 0;
      }
    });
  }, [results, sortOrder, filterExtension]);

  // 如果没有搜索结果
  if (!searchQuery.trim()) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-whiskey-500">
        <Search size={48} className="mb-4 opacity-50" />
        <h3 className="text-lg font-medium">输入关键词搜索文件</h3>
        <p className="text-sm opacity-75">搜索将匹配文件路径的任意部分</p>
      </div>
    );
  }

  // 有搜索查询但没有结果
  if (searchQuery.trim() && (!Array.isArray(results) || results.length === 0)) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-whiskey-500">
        <Search size={48} className="mb-4 opacity-50" />
        <h3 className="text-lg font-medium">没有找到匹配的文件</h3>
        <p className="text-sm opacity-75">尝试使用其他搜索词</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center">
          <h2 className="text-lg font-semibold">搜索结果: {Array.isArray(results) ? results.length : 0} 个文件</h2>
          <Badge variant="outline" className="ml-2">{searchQuery}</Badge>
        </div>
        <div className="flex space-x-2">
          <select
            className="rounded-md border border-whiskey-200 bg-white px-2 py-1 text-sm"
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as any)}
          >
            <option value="newest">最新修改</option>
            <option value="oldest">最早修改</option>
            <option value="name">文件名</option>
            <option value="size">文件大小</option>
          </select>
          <select
            className="rounded-md border border-whiskey-200 bg-white px-2 py-1 text-sm"
            value={filterExtension}
            onChange={(e) => setFilterExtension(e.target.value)}
          >
            <option value="all">所有类型</option>
            {uniqueExtensions.map(ext => (
              <option key={ext} value={ext}>{ext}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 文件列表 */}
      {processedFiles.length > 0 ? (
        <div className="grid grid-cols-1 gap-2">
          {processedFiles.map((file, index) => (
            <ContextMenu key={file.id ? `file-${file.id}` : `file-index-${index}`}>
              <ContextMenuTrigger asChild>
                <div
                  className={`flex cursor-pointer items-center justify-between rounded-md p-2 hover:bg-whiskey-100 ${selectedFile === file.file_path ? 'bg-whiskey-100' : ''}`}
                  onClick={() => setSelectedFile(file.file_path === selectedFile ? null : file.file_path)}
                  onDoubleClick={async () => {
                    try {
                      await openPath(file.file_path);
                    } catch (error) {
                      console.error("打开文件失败:", error);
                      toast.error("打开文件失败");
                    }
                  }}
                >
                  <div className="flex items-center space-x-3">
                    <div className="flex-shrink-0">
                      {getFileIcon(file.extension)}
                    </div>
                    <div className="flex flex-col">
                      <HoverCard>
                        <HoverCardTrigger asChild>
                          <span className="max-w-[340px] truncate font-medium">{file.file_name}</span>
                        </HoverCardTrigger>
                        <HoverCardContent className="w-[400px]" side="top">
                          <div className="space-y-1">
                            <p className="text-sm font-medium">{file.file_name}</p>
                            <p className="text-xs text-whiskey-500">{file.file_path}</p>
                            {file.tags && file.tags.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {file.tags.map((tag, idx) => (
                                  <Badge key={idx} variant="secondary" className="text-xs">{tag}</Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        </HoverCardContent>
                      </HoverCard>
                      <span className="text-xs text-whiskey-500 truncate max-w-[340px]">{file.file_path}</span>
                    </div>
                  </div>
                  <div className="flex items-center space-x-4">
                    <div className="text-sm text-whiskey-500">
                      {file.modified_time && format(new Date(file.modified_time), 'yyyy-MM-dd HH:mm', { locale: zhCN })}
                    </div>
                    <div className="text-sm text-whiskey-500 w-20 text-right">
                      {formatFileSize(file.file_size)}
                    </div>
                    <FileActionMenu file={file} />
                  </div>
                </div>
              </ContextMenuTrigger>
              <ContextMenuContent>
                <ContextMenuItem onClick={async () => {
                  try {
                    await openPath(file.file_path);
                  } catch (error) {
                    console.error("打开文件失败:", error);
                    toast.error("打开文件失败");
                  }
                }}>
                  <File className="mr-2 size-4" />
                  打开文件
                </ContextMenuItem>
                <ContextMenuItem onClick={async () => {
                  try {
                    await revealItemInDir(file.file_path);
                  } catch (error) {
                    console.error("打开文件夹失败:", error);
                    toast.error("打开文件夹失败");
                  }
                }}>
                  <Folder className="mr-2 size-4" />
                  打开所在文件夹
                </ContextMenuItem>
                <ContextMenuSeparator />
                <ContextMenuItem onClick={() => {
                  navigator.clipboard.writeText(file.file_path)
                    .then(() => toast.success("文件路径已复制到剪贴板"))
                    .catch(() => toast.error("复制文件路径失败"));
                }}>
                  <Copy className="mr-2 size-4" />
                  复制文件路径
                </ContextMenuItem>
              </ContextMenuContent>
            </ContextMenu>
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center p-8 text-whiskey-500">
          <p>没有找到符合条件的文件</p>
        </div>
      )}
    </div>
  );
};

export default SearchResults;
