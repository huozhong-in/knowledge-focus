import { useEffect, useState, useCallback, useRef } from "react";
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
import { invoke } from "@tauri-apps/api/core";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/main"; // 引入AppStore以获取API就绪状态
import { Skeleton } from "@/components/ui/skeleton";
import { useTagsUpdateListenerWithApiCheck } from "@/hooks/useBridgeEvents"; // 引入封装好的桥接事件Hook

// 标签数据类型
interface TagItem {
  id: number;
  name: string;
  weight: number;
  type: string;
}

export function NavTagCloud() {
  const { t } = useTranslation();
  const [tags, setTags] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const appStore = useAppStore(); // 获取全局AppStore实例
  
  // 防抖定时器引用
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // 使用 ref 来保持最新的函数引用，避免依赖问题
  const fetchTagCloudDataRef = useRef<() => Promise<void>>(async () => {});
  
  // 获取标签云数据
  const fetchTagCloudData = useCallback(async () => {
    if (!appStore.isApiReady) {
      console.log('API尚未就绪，暂不获取标签云数据');
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      // 调用后端API获取标签云数据
      const tagData = await invoke<TagItem[]>('get_tag_cloud_data', { limit: 100 });
      console.log('成功获取标签云数据:', tagData.length);
      setTags(tagData);
    } catch (error) {
      console.error('Error fetching tag cloud data:', error);
      setError('获取标签数据失败');
    } finally {
      setLoading(false);
    }
  }, [appStore.isApiReady]);
  
  // 更新 ref
  fetchTagCloudDataRef.current = fetchTagCloudData;
  
  // 防抖版本的数据获取函数
  const debouncedFetchTagCloudData = useCallback(() => {
    // 清除之前的定时器
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    
    // 设置新的定时器
    debounceTimerRef.current = setTimeout(() => {
      console.log('防抖延迟后执行标签云数据获取');
      fetchTagCloudDataRef.current?.();
    }, 2000); // 2秒防抖延迟
  }, []); // 移除依赖，使用 ref
  
  // 清理防抖定时器
  useEffect(() => {
    console.log('🏷️ NavTagCloud 组件已挂载, API状态:', appStore.isApiReady);
    return () => {
      console.log('🏷️ NavTagCloud 组件正在卸载, API状态:', appStore.isApiReady);
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        console.log('🏷️ 清理了防抖定时器');
      }
    };
  }, []);
  
  // 监听API就绪状态变化，使用 ref 避免依赖
  useEffect(() => {
    if (appStore.isApiReady) {
      console.log('API就绪，获取标签云数据');
      fetchTagCloudDataRef.current?.();
    }
  }, [appStore.isApiReady]);
  
  // 使用封装好的标签更新监听Hook（带API就绪状态检查）
  useTagsUpdateListenerWithApiCheck(
    () => {
      try {
        console.log('收到标签更新事件，触发防抖刷新');
        debouncedFetchTagCloudData();
      } catch (error) {
        console.error('处理标签更新事件时出错:', error);
      }
    },
    appStore.isApiReady,
    { showToasts: false } // 不显示toast，避免过多通知
  );
  
  // 根据标签权重计算字体大小
  const getFontSize = (weight: number) => {
    const minSize = 10;
    const maxSize = 16;
    
    if (!tags || tags.length <= 1) return minSize;
    
    // 找出最大和最小权重
    const weights = tags.map(tag => tag.weight);
    const maxWeight = Math.max(...weights);
    const minWeight = Math.min(...weights);
    
    if (maxWeight === minWeight) return minSize;
    
    // 计算权重对应的字体大小
    const size = minSize + ((weight - minWeight) / (maxWeight - minWeight)) * (maxSize - minSize);
    return Math.round(size);
  };
  
  // 处理标签点击
  const handleTagClick = (tagId: number) => {
    console.log('Tag clicked:', tagId);
  };
  
  //  shadow-sm border border-border
  return (
    <SidebarGroup className=" bg-background rounded-md">
      <SidebarGroupLabel>
        <Tag className="mr-2 h-4 w-4" />
        {t('file-tags')}
      </SidebarGroupLabel>
      
      <ScrollArea className="h-[250px] p-0">
        <div className="flex flex-wrap gap-1 p-1 justify-start">
          {loading ? (
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
          ) : tags.length > 0 ? (
            tags.map(tag => (
              <Badge
                key={tag.id}
                variant="secondary"
                className={cn(
                  "cursor-pointer hover:bg-muted transition-all", 
                  tag.type === 'SYSTEM' ? "border-primary" : "border-secondary"
                )}
                style={{ fontSize: `${getFontSize(tag.weight)}px` }}
                onClick={() => handleTagClick(tag.id)}
              >
                {tag.name}
                <span className="ml-1 text-xs text-muted-foreground">
                  ({tag.weight})
                </span>
                
              </Badge>
            ))
          ) : (
            <div className="text-sm text-muted-foreground">
              {t('No tags yet')}
            </div>
          )}
        </div>
      </ScrollArea>
    </SidebarGroup>
  )
}
