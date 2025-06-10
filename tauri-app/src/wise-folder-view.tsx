import { useState, useEffect } from 'react';
import { WiseFoldersService } from './api/wise-folders-service';
import { WiseFolder, WiseFolderFile } from './types/wise-folder-types';
import { useAppStore } from './main'; // 导入全局状态
import { FileIcon, Calendar, FileText, ExternalLink, Copy, Folder } from 'lucide-react';
import { toast } from 'sonner';
import { openPath, revealItemInDir } from "@tauri-apps/plugin-opener";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./components/ui/table";
import { Button } from "./components/ui/button";
import { Skeleton } from "./components/ui/skeleton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";
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
} from "./components/ui/hover-card";

interface WiseFolderViewProps {
  folder: WiseFolder;
}

export default function WiseFolderView({ folder }: WiseFolderViewProps) {
  const { isApiReady } = useAppStore(); // 使用全局API准备状态
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<WiseFolderFile[]>([]);

  useEffect(() => {
    // 只有当API就绪时才尝试获取数据
    if (!isApiReady) {
      setLoading(true);
      return;
    }

    const fetchFilesInFolder = async () => {
      try {
        setLoading(true);
        const folderFiles = await WiseFoldersService.getFilesInFolder(
          folder.type,
          folder.criteria
        );
        setFiles(folderFiles);
        setError(null);
      } catch (err) {
        console.error('获取文件夹文件失败:', err);
        setError('无法加载文件列表');
      } finally {
        setLoading(false);
      }
    };

    fetchFilesInFolder();
  }, [folder, isApiReady]); // 依赖isApiReady，当API就绪状态改变时重新执行

  // 打开文件
  const openFile = async (filePath: string) => {
    try {
      await openPath(filePath);
    } catch (error) {
      console.error('打开文件失败:', error);
      toast.error(`打开文件失败: ${error}`);
    }
  };

  // 在文件管理器中显示文件
  const showInFileManager = async (filePath: string) => {
    try {
      await revealItemInDir(filePath);
    } catch (error) {
      console.error('在文件管理器中显示文件失败:', error);
      toast.error(`打开文件夹失败: ${error}`);
    }
  };

  // 格式化文件大小
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // 格式化日期时间
  const formatDateTime = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return dateString || '未知';
    }
  };

  // 获取图标
  const getFileIcon = (extension: string | undefined) => {
    // 根据文件扩展名返回适当的图标
    if (!extension) return <FileText className="h-5 w-5 text-gray-500" />;
    
    const ext = extension.toLowerCase().replace('.', '');
    switch(ext) {
      case 'pdf':
        return <FileText className="h-5 w-5 text-red-500" />;
      case 'doc':
      case 'docx':
        return <FileText className="h-5 w-5 text-blue-500" />;
      case 'xls':
      case 'xlsx':
        return <FileText className="h-5 w-5 text-green-500" />;
      case 'ppt':
      case 'pptx':
        return <FileText className="h-5 w-5 text-orange-500" />;
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
        return <FileText className="h-5 w-5 text-purple-500" />;
      default:
        return <FileText className="h-5 w-5 text-gray-500" />;
    }
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
        <>
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </>
      )}
    </div>
  );

  // 渲染错误状态
  const renderError = () => (
    <div className="p-4 bg-red-50 rounded-md border border-red-200 text-red-700">
      <p className="font-semibold">加载失败</p>
      <p>{error}</p>
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{folder.name}</CardTitle>
        <CardDescription>
          {folder.description || '智慧归类的文件集合'} · {files.length} 个文件
        </CardDescription>
      </CardHeader>
      
      <CardContent>
        {loading ? (
          renderLoading()
        ) : error ? (
          renderError()
        ) : files.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <FileIcon className="h-12 w-12 mx-auto mb-2 opacity-30" />
            <p>此文件夹没有文件</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table className="table-fixed w-full">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[60%] min-w-[200px]">文件名</TableHead>
                  <TableHead className="w-[15%] text-right whitespace-nowrap">修改日期</TableHead>
                  <TableHead className="w-[10%] text-right whitespace-nowrap">大小</TableHead>
                  <TableHead className="w-[15%] text-right whitespace-nowrap">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
              {files.map((file) => (
                <TableRow key={file.id}>
                  <ContextMenu>
                    <ContextMenuTrigger>
                      <TableCell className="max-w-0 w-0 overflow-hidden">
                        <div
                          className="flex items-center space-x-2 cursor-pointer w-full"
                          onClick={() => openFile(file.file_path)}
                        >
                          <div className="flex-shrink-0">
                            {getFileIcon(file.extension)}
                          </div>
                          <HoverCard>
                            <HoverCardTrigger asChild>
                              <span className="truncate inline-block w-full">
                                {file.file_name}
                              </span>
                            </HoverCardTrigger>
                            <HoverCardContent className="w-auto max-w-[400px] p-2">
                              <p className="break-all">{file.file_name}</p>
                              <p className="text-xs text-gray-500 mt-1">{file.file_path}</p>
                            </HoverCardContent>
                          </HoverCard>
                        </div>
                      </TableCell>
                    </ContextMenuTrigger>
                    <ContextMenuContent className="w-64">
                      <ContextMenuItem onClick={() => openFile(file.file_path)}>
                        <ExternalLink className="h-4 w-4 mr-2" /> 打开文件
                      </ContextMenuItem>                        <ContextMenuItem onClick={() => showInFileManager(file.file_path)}>
                        <Folder className="h-4 w-4 mr-2" /> 打开所在文件夹
                      </ContextMenuItem>
                      <ContextMenuSeparator />
                      <ContextMenuItem onClick={() => {
                        navigator.clipboard.writeText(file.file_path)
                          .then(() => toast.success("文件路径已复制到剪贴板"))
                          .catch(err => {
                            console.error("复制失败:", err);
                            toast.error("复制文件路径失败");
                          })
                      }}>
                        <Copy className="h-4 w-4 mr-2" /> 复制文件路径
                        复制文件路径
                      </ContextMenuItem>
                    </ContextMenuContent>
                  </ContextMenu>
                  <TableCell className="text-right whitespace-nowrap">
                    <div className="flex items-center justify-end space-x-2">
                      <Calendar className="h-4 w-4 text-gray-500" />
                      <span>{formatDateTime(file.modified_time)}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {formatFileSize(file.file_size)}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <div className="flex justify-end space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => showInFileManager(file.file_path)}
                      >
                        <ExternalLink className="h-4 w-4 mr-1" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}