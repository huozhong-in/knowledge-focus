import { useEffect, useRef, useState, useCallback } from "react";
import { 
  Tags,
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/main"; // 引入AppStore以获取API就绪状态
import { Skeleton } from "@/components/ui/skeleton";
import { useTagsUpdateListenerWithApiCheck, useScreeningResultUpdated } from "@/hooks/useBridgeEvents"; // 引入封装好的桥接事件Hook
import { useTagCloudStore } from "@/lib/tagCloudStore"; // 引入标签云全局状态
import { useFileListStore } from "@/lib/fileListStore"; // 引入文件列表状态
import { FileService } from "@/api/file-service"; // 引入文件服务

export function NavTagCloud() {
  const { t } = useTranslation();
  const appStore = useAppStore(); // 获取全局AppStore实例
  
  // 使用全局标签云状态
  const { tags, loading, fetchTagCloud } = useTagCloudStore();
  
  // 使用文件列表状态
  const { setFiles, setLoading, setError } = useFileListStore();
  
  // 标签统计状态
  const [taggedCount, setTaggedCount] = useState<number>(0);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [statsLoading, setStatsLoading] = useState<boolean>(false);
  
  // 防抖定时器引用
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // 获取标签统计数据
  const fetchTaggingStats = useCallback(async () => {
    if (!appStore.isApiReady) {
      console.log('🏷️ API未就绪，跳过标签统计获取');
      return;
    }
    
    try {
      setStatsLoading(true);
      const url = "http://127.0.0.1:60315/file-screening/tagging-stats";
      const response = await fetch(url);
      const result = await response.json();
      
      if (result.success) {
        setTaggedCount(result.tagged_count || 0);
        setTotalCount(result.total_count || 0);
        console.log(`📊 标签统计更新: ${result.tagged_count}/${result.total_count}`);
      }
    } catch (error) {
      console.error('获取标签统计失败:', error);
    } finally {
      setStatsLoading(false);
    }
  }, [appStore.isApiReady]);
  
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
      fetchTaggingStats(); // 同时更新统计数据
    }, 1000); // 1秒防抖延迟
  };
  
  // 组件挂载和卸载监控
  useEffect(() => {
    console.log('🏷️ NavTagCloud 组件已挂载, API状态:', appStore.isApiReady, '时间:', new Date().toLocaleTimeString());
    
    // 如果 API 已就绪，立即尝试获取数据（会自动检查缓存）
    if (appStore.isApiReady) {
      console.log('🚀 组件挂载时尝试获取标签云数据');
      fetchTagCloud();
      fetchTaggingStats(); // 同时获取统计数据
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
      fetchTaggingStats(); // 同时获取统计数据
    }
  }, [appStore.isApiReady, fetchTaggingStats]); // 添加 fetchTaggingStats 依赖
  
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
  
  // 监听筛选结果更新事件（也会影响统计）
  useScreeningResultUpdated(() => {
    try {
      console.log('收到筛选结果更新事件，刷新标签统计');
      fetchTaggingStats();
    } catch (error) {
      console.error('处理筛选结果更新事件时出错:', error);
    }
  });
  
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
      setError(error instanceof Error ? error.message : 'search error');
    } finally {
      setLoading(false);
    }
  };
  
  //  shadow-sm border border-border
  return (
    <SidebarGroup className=" bg-background rounded-md pr-0">
      <SidebarGroupLabel className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Tags className="h-4 w-4" />
          <span>{t('APPSIDEBAR.file-tags')}</span>
        </div>
        
        {/* 标签统计指示器 - 在标题右侧 */}
        {statsLoading ? (
          <Skeleton className="h-6 w-20 rounded-full" />
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20 cursor-help">
                <div className="w-1 h-1 rounded-full bg-primary animate-pulse"></div>
                <span className="text-[10px] font-medium text-primary">
                  {taggedCount}
                </span>
                <span className="text-[10px] text-muted-foreground/60">/</span>
                <span className="text-[10px] text-muted-foreground font-medium">
                  {totalCount}
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">
                <span className="font-medium">tagged / total files</span>
              </p>
            </TooltipContent>
          </Tooltip>
        )}
      </SidebarGroupLabel>
      
      <ScrollArea className="h-[calc(22vh)] p-0 m-0">
        <div className="flex flex-wrap gap-1 p-1 justify-start">
          {loading ? (
            // 状态1: 加载中 - 显示skeleton
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
          ) : tags.length === 0 ? (
            // 状态2: 无标签 - 数据为空（内置模型加载中或尚未生成标签）
            <div className="text-sm text-muted-foreground text-center w-full">
              no tags available
              <br />
              <span className="text-xs">
                Please perform file scanning and tag generation first.
              </span>
            </div>
          ) : (
            // 状态2: 有标签 - 显示标签云
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
