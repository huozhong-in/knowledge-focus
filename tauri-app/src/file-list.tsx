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

  return (
    <div className={`flex flex-1 border rounded-md p-2 mb-1.5 group relative min-w-0 @container ${file.pinned ? 'border-primary bg-primary/5' : 'border-border bg-background'} hover:bg-muted/50 transition-colors`}>
      <div className="flex items-start gap-1.5 min-w-0 flex-1">
        <div className="mt-0.5 shrink-0">
          {getFileIcon(file.extension)}
        </div>
        <div className="flex-1 min-w-0 w-0 pr-12"> {/* w-0 强制宽度为0，flex-1让它填充，pr-12为按钮留空间 */}
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
          title="在文件夹中显示"
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
          title={file.pinned ? "取消固定" : "固定文件"}
        >
          {file.pinned ? <Pin className="h-2.5 w-2.5" /> : <PinOff className="h-2.5 w-2.5" />}
        </Button>
      </div>
    </div>
  );
}

export function FileList() {
  const { getFilteredFiles, togglePinnedFile, isLoading, error, setFiles, setLoading, setError } = useFileListStore();
  const { setFileStatus, setFileStarted, setFileFailed } = useVectorizationStore();
  const files = getFilteredFiles();
  
  // 搜索框状态
  const [searchKeyword, setSearchKeyword] = useState("");

  // Pin文件API调用
  const pinFileAPI = async (filePath: string): Promise<{ success: boolean; taskId?: number; error?: string }> => {
    try {
      const response = await fetch('http://127.0.0.1:60315/pin-file', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ file_path: filePath }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      return result;
    } catch (error) {
      console.error('Pin file API error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : '未知错误'
      };
    }
  };

  const handleTogglePin = async (fileId: number, filePath: string) => {
    const file = files.find(f => f.id === fileId);
    if (!file) return;

    // 如果要取消pin，直接调用本地toggle
    if (file.pinned) {
      togglePinnedFile(fileId);
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

        toast.success(`文件 ${file.file_name} 已开始向量化处理`);
      } else {
        // API失败，设置错误状态
        setFileFailed(filePath, '', {
          message: result.error || '向量化启动失败',
          helpLink: 'https://github.com/huozhong-in/knowledge-focus/wiki/troubleshooting'
        });

        toast.error(`向量化失败：${result.error}`);
      }
    } catch (error) {
      // 网络或其他错误
      setFileFailed(filePath, '', {
        message: error instanceof Error ? error.message : '网络连接失败',
        helpLink: 'https://github.com/huozhong-in/knowledge-focus/wiki/troubleshooting'
      });

      toast.error('向量化请求失败，请检查网络连接');
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
      setError(error instanceof Error ? error.message : '搜索失败');
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
      setError(error instanceof Error ? error.message : '搜索失败');
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
          <p className="text-sm">文件搜索结果</p>
          <p className="text-xs text-muted-foreground">正在搜索...</p>
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
          <p className="text-sm">文件搜索结果</p>
          <p className="text-xs text-destructive">搜索出错</p>
        </div>
        <div className="p-2 text-center text-xs text-muted-foreground">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full h-full overflow-auto">
      <div className="border-b p-3 shrink-0 h-[50px]">
        <p className="text-sm">文件搜索结果</p>
        <p className="text-xs text-muted-foreground">
          固定文件以便在对话中参考
        </p>
      </div>

      <ScrollArea className="flex-1 p-3 h-[calc(100%-90px)] @container">
        {files.length === 0 ? (
          <div className="text-center py-6">
            <FileText className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
            <p className="text-xs text-muted-foreground px-2 leading-relaxed">
              请点击左侧标签云中的标签来搜索相关文件
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
      <div className="h-[40px] flex flex-row w-full items-center justify-end p-2 gap-2 bg-background/60 backdrop-blur-sm border-t border-border/50">
        <Input 
          type="text" 
          placeholder="路径关键字搜索..." 
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          onKeyDown={handleKeyPress}
          className="h-6 text-[9px] shrink max-w-36 border border-muted-foreground/30 bg-background/90 px-2 py-1 focus:border-primary/50 focus:bg-background transition-all duration-200" 
        />
        <Button 
          type="submit" 
          variant="secondary" 
          size="sm"
          onClick={handlePathSearch}
          disabled={isLoading || !searchKeyword.trim()}
          className="h-6 px-3 text-xs bg-primary/10 hover:bg-primary/20 border border-primary/30 hover:border-primary/50 text-primary hover:text-primary transition-all duration-200 rounded disabled:opacity-50"
        >
          搜索
        </Button>
      </div>
      
    </div>
  );
}