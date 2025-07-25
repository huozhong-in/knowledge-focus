import { Pin, PinOff, FileText, File, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useFileListStore } from "@/lib/fileListStore";
import { TaggedFile } from "@/types/file-types";
import { FileService } from "@/api/file-service";
import { revealItemInDir } from "@tauri-apps/plugin-opener";

interface FileItemProps {
  file: TaggedFile;
  onTogglePin: (fileId: number) => void;
  onTagClick: (tagName: string) => void;
}

function FileItem({ file, onTogglePin, onTagClick }: FileItemProps) {
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
    <div className={`w-[243px] border rounded-md p-2 mb-1.5 group relative ${file.pinned ? 'border-primary bg-primary/5' : 'border-border bg-background'} hover:bg-muted/50 transition-colors`}>
      <div className="flex items-start gap-1.5">
        <div className="mt-0.5 flex-shrink-0">
          {getFileIcon(file.extension)}
        </div>
        <div className="flex-1 min-w-0">
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
                <button
                  key={index}
                  className={`inline-block text-[9px] px-1 py-0.5 rounded leading-none cursor-pointer transition-colors ${getTagColorClass(index)}`}
                  title={tag}
                  onClick={(e) => handleTagClick(tag, e)}
                >
                  {tag.length > 8 ? `${tag.slice(0, 8)}..` : tag}
                </button>
              ))}
              {file.tags.length > 3 && (
                <span className="inline-block bg-muted text-muted-foreground text-[9px] px-1 py-0.5 rounded leading-none">
                  +{file.tags.length - 3}
                </span>
              )}
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
          onClick={() => onTogglePin(file.id)}
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
  const files = getFilteredFiles();

  const handleTogglePin = (fileId: number) => {
    togglePinnedFile(fileId);
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

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b p-2 flex-shrink-0">
          <p className="text-sm font-semibold">标签搜索结果</p>
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
        <div className="border-b p-2 flex-shrink-0">
          <p className="text-sm font-semibold">标签搜索结果</p>
          <p className="text-xs text-destructive">搜索出错</p>
        </div>
        <div className="p-2 text-center text-xs text-muted-foreground">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="border-b p-2 flex-shrink-0 h-[50px]">
        <p className="text-sm font-semibold">标签搜索结果</p>
        <p className="text-xs text-muted-foreground">
          固定文件以便在对话中参考
        </p>
      </div>
      
      <ScrollArea className="flex-1 p-1 h-[calc(100vh-90px)]">
        {/* <div className="p-0 h-full"> */}
          {files.length === 0 ? (
            <div className="text-center py-6">
              <FileText className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
              <p className="text-xs text-muted-foreground px-2 leading-relaxed">
                请点击左侧标签云中的标签来搜索相关文件
              </p>
            </div>
          ) : (
            <div className="space-y-0">
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
        {/* </div> */}
      </ScrollArea>
      <div className="h-[40px] p-2 text-xs text-muted-foreground">
        {files.length > 0 ? `找到 ${files.length} 个文件` : "点击标签查看相关文件"}
      </div>
    </div>
  );
}