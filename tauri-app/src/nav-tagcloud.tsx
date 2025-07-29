import { useEffect, useRef } from "react";
import { 
  Tag,
} from "lucide-react"
import {
} from "@/components/ui/dropdown-menu"
import {
  SidebarGroup,
  SidebarGroupLabel,
} from "@/components/ui/sidebar"
import { useTranslation } from 'react-i18next';
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/main"; // 引入AppStore以获取API就绪状态
import { Skeleton } from "@/components/ui/skeleton";
import { useTagsUpdateListenerWithApiCheck } from "@/hooks/useBridgeEvents"; // 引入封装好的桥接事件Hook
import { useTagCloudStore } from "@/lib/tagCloudStore"; // 引入标签云全局状态
import { useFileListStore } from "@/lib/fileListStore"; // 引入文件列表状态
import { FileService } from "@/api/file-service"; // 引入文件服务

export function NavTagCloud() {
  const { t } = useTranslation();
  const appStore = useAppStore(); // 获取全局AppStore实例
  
  // 使用全局标签云状态
  const { tags, loading, error, fetchTagCloud } = useTagCloudStore();
  
  // 使用文件列表状态
  const { setFiles, setLoading, setError } = useFileListStore();
  
  // 防抖定时器引用
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // 防抖版本的数据获取函数
  const debouncedFetchTagCloud = () => {
    // 清除之前的定时器
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    
    // 设置新的定时器
    debounceTimerRef.current = setTimeout(() => {
      console.log('⏰ 防抖延迟后执行标签云数据获取');
      fetchTagCloud();
    }, 1000); // 1秒防抖延迟
  };
  
  // 组件挂载和卸载监控
  useEffect(() => {
    console.log('🏷️ NavTagCloud 组件已挂载, API状态:', appStore.isApiReady, '时间:', new Date().toLocaleTimeString());
    
    // 如果 API 已就绪，立即尝试获取数据（会自动检查缓存）
    if (appStore.isApiReady) {
      console.log('🚀 组件挂载时尝试获取标签云数据');
      fetchTagCloud();
    }
    
    return () => {
      console.log('🏷️ NavTagCloud 组件正在卸载, API状态:', appStore.isApiReady, '时间:', new Date().toLocaleTimeString());
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        console.log('🧹 清理了防抖定时器');
      }
    };
  }, []); // 只在首次挂载时执行
  
  // 监听API就绪状态变化
  useEffect(() => {
    if (appStore.isApiReady) {
      console.log('🔗 API就绪，尝试获取标签云数据');
      fetchTagCloud();
    }
  }, [appStore.isApiReady, fetchTagCloud]);
  
  // 使用封装好的标签更新监听Hook（带API就绪状态检查）
  useTagsUpdateListenerWithApiCheck(
    () => {
      try {
        console.log('收到标签更新事件，触发防抖刷新');
        debouncedFetchTagCloud();
      } catch (error) {
        console.error('处理标签更新事件时出错:', error);
      }
    },
    appStore.isApiReady,
    { showToasts: false } // 不显示toast，避免过多通知
  );
  
  // 根据标签权重计算字体大小
  // const getFontSize = (weight: number) => {
  //   const minSize = 10;
  //   const maxSize = 16;
    
  //   if (!tags || tags.length <= 1) return minSize;
    
  //   // 找出最大和最小权重
  //   const weights = tags.map(tag => tag.weight);
  //   const maxWeight = Math.max(...weights);
  //   const minWeight = Math.min(...weights);
    
  //   if (maxWeight === minWeight) return minSize;
    
  //   // 计算权重对应的字体大小
  //   const size = minSize + ((weight - minWeight) / (maxWeight - minWeight)) * (maxSize - minSize);
  //   return Math.round(size);
  // };
  
  // 处理标签点击
  const handleTagClick = async (tagId: number) => {
    console.log('Tag clicked:', tagId);
    
    // 找到对应的标签
    const tag = tags.find(t => t.id === tagId);
    if (!tag) {
      console.error('Tag not found:', tagId);
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      
      // 按标签名搜索文件
      const files = await FileService.searchFilesByTags([tag.name], 'AND');
      setFiles(files);
      
      console.log(`Found ${files.length} files for tag: ${tag.name}`);
    } catch (error) {
      console.error('Error searching files by tag:', error);
      setError(error instanceof Error ? error.message : '搜索失败');
    } finally {
      setLoading(false);
    }
  };
  
  //  shadow-sm border border-border
  return (
    <SidebarGroup className=" bg-background rounded-md pr-0">
      <SidebarGroupLabel>
        <Tag className="mr-2 h-4 w-4" />
        {t('file-tags')}
      </SidebarGroupLabel>
      
      <ScrollArea className="h-[250px] p-0 m-0">
        <div className="flex flex-wrap gap-1 p-1 justify-start">
          {loading || tags.length === 0 ? (
            <>
              <Skeleton className="h-6 w-16 rounded-full" />
              <Skeleton className="h-6 w-24 rounded-full" />
              <Skeleton className="h-6 w-12 rounded-full" />
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-6 w-18 rounded-full" />
              <Skeleton className="h-6 w-14 rounded-full" />
              <Skeleton className="h-6 w-22 rounded-full" />
              <Skeleton className="h-6 w-16 rounded-full" />
              <Skeleton className="h-6 w-28 rounded-full" />
              <Skeleton className="h-6 w-10 rounded-full" />
              <Skeleton className="h-6 w-26 rounded-full" />
              <Skeleton className="h-6 w-15 rounded-full" />
            </>
          ) : error ? (
            <div className="text-sm text-destructive">
              {error}
            </div>
          ) : (
            tags.map(tag => (
              <Badge
                key={tag.id}
                variant="secondary"
                className={cn(
                  "cursor-pointer hover:bg-muted transition-all", 
                  tag.type === 'SYSTEM' ? "border-primary" : "border-secondary"
                )}
                // style={{ fontSize: `${getFontSize(tag.weight)}px` }}
                onClick={() => handleTagClick(tag.id)}
              >
                {tag.name}
                <span className="ml-1 text-xs text-muted-foreground">
                  ({tag.weight})
                </span>
                
              </Badge>
            ))
          )}
        </div>
      </ScrollArea>
    </SidebarGroup>
  )
}
