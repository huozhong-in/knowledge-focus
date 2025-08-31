import { Pin, PinOff, FileText, File, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area";
import { useFileListStore } from "@/lib/fileListStore";
import { TaggedFile } from "@/types/file-types";
import { FileService } from "@/api/file-service";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { fetch } from '@tauri-apps/plugin-http';
import { useState } from "react";
import { VectorizationProgress } from "@/components/VectorizationProgress";
import { useVectorizationStore } from "@/stores/useVectorizationStore";
import { toast } from "sonner";
import { useSettingsStore } from "./App";
import { useTranslation } from "react-i18next";

interface FileItemProps {
  file: TaggedFile;
  onTogglePin: (fileId: number, filePath: string) => void;
  onTagClick: (tagName: string) => void;
}

function FileItem({ file, onTogglePin, onTagClick }: FileItemProps) {
  const { getFileStatus } = useVectorizationStore();
  const vectorizationState = getFileStatus(file.path);
  const getFileIcon = (extension?: string) => {
    if (!extension) return <File className="h-3 w-3" />;
    
    const textExtensions = ['txt', 'md', 'doc', 'docx', 'pdf'];
    if (textExtensions.includes(extension.toLowerCase())) {
      return <FileText className="h-3 w-3" />;
    }
    
    return <File className="h-3 w-3" />;
  };

  // 生成随机颜色的标签样式
  const getTagColorClass = (index: number) => {
    const colors = [
      'bg-red-100 text-red-800 hover:bg-red-200',
      'bg-blue-100 text-blue-800 hover:bg-blue-200', 
      'bg-green-100 text-green-800 hover:bg-green-200',
      'bg-yellow-100 text-yellow-800 hover:bg-yellow-200',
      'bg-purple-100 text-purple-800 hover:bg-purple-200',
      'bg-pink-100 text-pink-800 hover:bg-pink-200',
      'bg-indigo-100 text-indigo-800 hover:bg-indigo-200',
      'bg-orange-100 text-orange-800 hover:bg-orange-200',
    ];
    return colors[index % colors.length];
  };

  const handleTagClick = (tagName: string, event: React.MouseEvent) => {
    event.stopPropagation(); // 防止触发文件点击事件
    onTagClick(tagName);
  };

  const handleRevealInDir = async (event: React.MouseEvent) => {
    event.stopPropagation();
    try {
      await revealItemInDir(file.path);
    } catch (error) {
      console.error('Failed to reveal item in directory:', error);
    }
  };

  const { t } = useTranslation();

  return (
    <div className={`flex flex-1 border rounded-md p-2 mb-1.5 group relative min-w-0 @container ${file.pinned ? 'border-primary bg-primary/5' : 'border-border bg-background'} hover:bg-muted/50 transition-colors`}>
      <div className="flex items-start gap-1.5 min-w-0 flex-1">
        <div className="mt-0.5 shrink-0">
          {getFileIcon(file.extension)}
        </div>
        <div className="flex-1 min-w-0 w-0 pr-2"> {/* w-0 强制宽度为0，flex-1让它填充，pr-2为按钮留空间 */}
          <div className="font-medium text-xs truncate leading-tight" title={file.file_name}>
            {file.file_name}
          </div>
          <div className="text-[10px] text-muted-foreground truncate leading-tight mt-0.5" title={file.path}>
            {file.path}
          </div>
          
          {/* 标签列表 - 多彩可点击 */}
          {file.tags && file.tags.length > 0 && (
            <div className="flex flex-wrap gap-0.5 mt-1">
              {file.tags.slice(0, 3).map((tag, index) => (
                <Button
                  key={index}
                  className={`h-4 inline-block text-[9px] px-1 py-0.5 rounded leading-none cursor-pointer transition-colors ${getTagColorClass(index)}`}
                  title={tag}
                  onClick={(e) => handleTagClick(tag, e)}
                >
                  {tag.length > 8 ? `${tag.slice(0, 8)}..` : tag}
                </Button>
              ))}
              {file.tags.length > 3 && (
                <span className="inline-block bg-muted text-muted-foreground text-[9px] px-1 py-0.5 rounded leading-none">
                  +{file.tags.length - 3}
                </span>
              )}
            </div>
          )}

          {/* 向量化进度显示 */}
          {vectorizationState && (
            <div className="mt-1">
              <VectorizationProgress
                filePath={file.path}
                state={vectorizationState}
                onRetry={() => onTogglePin(file.id, file.path)}
                className="text-xs"
              />
            </div>
          )}
        </div>
      </div>
      
      {/* 浮动按钮区域 - 绝对定位，不占用布局空间 */}
      <div className="absolute top-2 right-2 flex gap-1">
        {/* Reveal in Dir 按钮 - hover时显示 */}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRevealInDir}
          className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 transition-opacity bg-background/80 hover:bg-background border border-border/50"
          title={t('FILELIST.show-in-folder')}
        >
          <FolderOpen className="h-2.5 w-2.5" />
        </Button>
        
        {/* Pin 按钮 - pinned时始终显示，未pinned时hover显示 */}
        <Button
          variant={file.pinned ? "default" : "ghost"}
          size="sm"
          onClick={() => onTogglePin(file.id, file.path)}
          className={`h-5 w-5 p-0 transition-opacity ${
            file.pinned 
              ? 'opacity-100' 
              : 'opacity-0 group-hover:opacity-100 bg-background/80 hover:bg-background border border-border/50'
          }`}
          title={file.pinned ? t('FILELIST.unpin-file') : t('FILELIST.pin-file')}
        >
          {file.pinned ? <Pin className="h-2.5 w-2.5" /> : <PinOff className="h-2.5 w-2.5" />}
        </Button>
      </div>
    </div>
  );
}

interface FileListProps {
  currentSessionId?: number | null;
  onAddTempPinnedFile?: (filePath: string, fileName: string, metadata?: Record<string, any>) => void;
  onRemoveTempPinnedFile?: (filePath: string) => void;
}

export function FileList({ currentSessionId, onAddTempPinnedFile, onRemoveTempPinnedFile }: FileListProps) {
  const { getFilteredFiles, togglePinnedFile, isLoading, error, setFiles, setLoading, setError } = useFileListStore();
  const { setFileStatus, setFileStarted, setFileFailed } = useVectorizationStore();
  const { openSettingsPage } = useSettingsStore();
  const files = getFilteredFiles();
  
  // 搜索框状态
  const [searchKeyword, setSearchKeyword] = useState("");

  const { t } = useTranslation();

  // Pin文件API调用
  const pinFileAPI = async (filePath: string): Promise<{ success: boolean; taskId?: number; error?: string }> => {
    try {
      let result: any;

      if (currentSessionId) {
        // 有会话时，首先使用会话相关的pin-file API将文件关联到会话
        const sessionUrl = `http://127.0.0.1:60315/chat/sessions/${currentSessionId}/pin-file`;
        const sessionBody = {
          file_path: filePath,
          file_name: filePath.split('/').pop() || filePath,
          metadata: {}
        };

        const sessionResponse = await fetch(sessionUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(sessionBody),
        });

        if (!sessionResponse.ok) {
          throw new Error(`Session pin failed: HTTP ${sessionResponse.status}: ${sessionResponse.statusText}`);
        }

        const sessionResult = await sessionResponse.json();
        
        if (!sessionResult.success) {
          throw new Error(`Session pin failed: ${sessionResult.error || 'Unknown error'}`);
        }

        // 成功关联到会话后，再调用向量化任务创建API
        const vectorizeUrl = 'http://127.0.0.1:60315/pin-file';
        const vectorizeBody = { file_path: filePath };

        const vectorizeResponse = await fetch(vectorizeUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(vectorizeBody),
        });

        if (!vectorizeResponse.ok) {
          throw new Error(`Vectorization failed: HTTP ${vectorizeResponse.status}: ${vectorizeResponse.statusText}`);
        }

        result = await vectorizeResponse.json();
        
        // 检查是否是模型配置缺失的错误
        if (!result.success && result.error_type === 'model_missing') {
          handleModelMissingError(result);
          return result;
        }
    } else {
        // 没有会话时，使用临时pin机制
        // 1. 添加到临时pin文件列表
        const fileName = filePath.split('/').pop() || filePath;
        onAddTempPinnedFile?.(filePath, fileName, {});
        
        // 2. 调用向量化API进行处理
        const url = 'http://127.0.0.1:60315/pin-file';
        const body = { file_path: filePath };

        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        result = await response.json();
      }

      // 检查是否是模型配置缺失的错误
      if (!result.success && result.error_type === 'model_missing') {
        handleModelMissingError(result);
        return result;
      }

      return result;
    } catch (error) {
      console.error('Pin file API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误'
      };
    }
  };

  // 处理模型配置缺失的情况
  const handleModelMissingError = (response: any) => {
    const confirmMessage = `${response.message}\n\njump to settings page to configure?`;
    
    // 使用原生confirm对话框
    if (confirm(confirmMessage)) {
      // 用户确认跳转到设置页面
      openSettingsPage("aimodels");
    }
  };

  // 取消Pin文件API调用
  const unpinFileAPI = async (filePath: string): Promise<{ success: boolean; error?: string }> => {
    try {
      if (currentSessionId) {
        // 有会话时，使用会话相关的unpin-file API
        const url = `http://127.0.0.1:60315/chat/sessions/${currentSessionId}/pinned-files`;
        const response = await fetch(`${url}?file_path=${encodeURIComponent(filePath)}`, {
          method: 'DELETE',
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        return result;
      } else {
        // 没有会话时，从临时pin文件列表中移除
        onRemoveTempPinnedFile?.(filePath);
        return { success: true };
      }
    } catch (error) {
      console.error('Unpin file API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误'
      };
    }
  };

  const handleTogglePin = async (fileId: number, filePath: string) => {
    const file = files.find(f => f.id === fileId);
    if (!file) return;

    // 如果要取消pin，调用unpin API
    if (file.pinned) {
      try {
        const result = await unpinFileAPI(filePath);
        
        if (result.success) {
          togglePinnedFile(fileId);
          toast.success(t('FILELIST.unpin-file-success', { file_name: file.file_name }));
        } else {
          toast.error(`${t('FILELIST.unpin-file-failure')}: ${result.error}`);
        }
      } catch (error) {
        toast.error(`${t('FILELIST.unpin-file-failure')}: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
      return;
    }

    // 如果要pin文件，调用API并设置向量化状态
    try {
      // 设置初始状态
      setFileStatus(filePath, 'queued');

      // 调用API
      const result = await pinFileAPI(filePath);
      
      if (result.success) {
        // API成功，更新pin状态和向量化任务ID
        togglePinnedFile(fileId);
        setFileStarted(filePath, result.taskId?.toString() || '');

        toast.success(t('FILELIST.vectorization-start', { file_name: file.file_name }));
      } else {
        // 检查是否是模型配置缺失的错误
        if ((result as any).error_type === 'model_missing') {
          // 处理模型配置缺失的情况
          handleModelMissingError(result);
          // 不设置向量化失败状态，因为这是配置问题不是文件问题
        } else {
          // API失败，设置错误状态
          setFileFailed(filePath, '', {
            message: result.error || t('FILELIST.VectorizationFileState.failed'),
            helpLink: 'https://github.com/huozhong-in/knowledge-focus/wiki/troubleshooting'
          });

          toast.error(`${t('FILELIST.VectorizationFileState.failed')}: ${result.error}`);
        }
      }
    } catch (error) {
      // 网络或其他错误
      setFileFailed(filePath, '', {
        message: error instanceof Error ? error.message : t('FILELIST.NetworkError'),
        helpLink: 'https://github.com/huozhong-in/knowledge-focus/wiki/troubleshooting'
      });

      toast.error(t('FILELIST.NetworkError'));
    }
  };

  const handleTagClick = async (tagName: string) => {
    try {
      setLoading(true);
      setError(null);
      
      // 按标签名搜索文件
      const newFiles = await FileService.searchFilesByTags([tagName], 'AND');
      setFiles(newFiles);
      
      console.log(`Found ${newFiles.length} files for tag: ${tagName}`);
    } catch (error) {
      console.error('Error searching files by tag:', error);
      setError(error instanceof Error ? error.message : t('FILELIST.search-failure'));
    } finally {
      setLoading(false);
    }
  };

  // 处理路径搜索
  const handlePathSearch = async () => {
    if (!searchKeyword.trim()) {
      return;
    }

    try {
      setLoading(true);
      setError(null);
      
      // 按路径关键字搜索文件
      const newFiles = await FileService.searchFilesByPath(searchKeyword.trim());
      setFiles(newFiles);
      
      console.log(`Found ${newFiles.length} files for path keyword: ${searchKeyword}`);
    } catch (error) {
      console.error('Error searching files by path:', error);
      setError(error instanceof Error ? error.message : t('FILELIST.search-failure'));
    } finally {
      setLoading(false);
    }
  };

  // 处理回车键搜索
  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      handlePathSearch();
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b p-2 shrink-0">
          <p className="text-sm">{t('FILELIST.search-results')}</p>
          <p className="text-xs text-muted-foreground">Searching...</p>
        </div>
        <div className="p-2 space-y-1.5">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="border rounded-md p-2 animate-pulse">
              <div className="h-3 bg-muted rounded mb-1"></div>
              <div className="h-2 bg-muted rounded w-3/4"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b p-2 shrink-0">
          <p className="text-sm">{t('FILELIST.search-results')}</p>
          <p className="text-xs text-destructive">{t('FILELIST.search-failure')}</p>
        </div>
        <div className="p-2 text-center text-xs text-muted-foreground">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full h-full overflow-auto">
      <div className="p-3 h-[50px]">
        <div className="text-sm">{t('FILELIST.pin-file-for-chat')}</div>
        <div className="text-xs text-muted-foreground">
          {t('FILELIST.tap-tag-or-search-file-name')}
        </div>
      </div>
      <div className="h-[40px] flex flex-row w-full items-center justify-end p-2 gap-2 border-b border-border/50">
        <Input 
          type="text" 
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          onKeyDown={handleKeyPress}
          className="h-6 text-xs max-w-36 border border-muted-foreground/30 bg-background/90 focus:border-primary/50 focus:bg-background transition-all duration-200" 
        />
        <Button 
          type="submit" 
          variant="secondary" 
          size="sm"
          onClick={handlePathSearch}
          disabled={isLoading || !searchKeyword.trim()}
          className="h-6 px-3 text-xs bg-primary/10 hover:bg-primary/20 border border-primary/30 hover:border-primary/50 text-primary hover:text-primary transition-all duration-200 disabled:opacity-50"
        >
          {t('FILELIST.search')}
        </Button>
      </div>
      <ScrollArea className="flex-1 p-3 h-[calc(100%-90px)] @container">
        {files.length === 0 ? (
          <div className="text-center py-6">
            <FileText className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
            <p className="text-xs text-muted-foreground px-2 leading-relaxed">
              {t('tap-tag-or-search-file-name-detail')}
            </p>
          </div>
        ) : (
          <div className="space-y-0 min-w-0 w-[98cqw]">
            {files.map((file) => (
              <FileItem 
                key={file.id}
                file={file} 
                onTogglePin={handleTogglePin}
                onTagClick={handleTagClick}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}