import { useEffect, useState } from "react";
import { 
  Tag,
  // FolderEdit,
  // ListIcon,
  // MoreHorizontal,
  // Pin,
  // PinOff,
  // type LucideIcon,
} from "lucide-react"

import {
  // DropdownMenu,
  // DropdownMenuContent,
  // DropdownMenuItem,
  // DropdownMenuSeparator,
  // DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
// import { usePageStore } from "@/App"
import {
  SidebarGroup,
  SidebarGroupLabel,
  // SidebarMenu,
  // SidebarMenuAction,
  // SidebarMenuButton,
  // SidebarMenuItem,
  // useSidebar,
} from "@/components/ui/sidebar"
import { useTranslation } from 'react-i18next';
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/main"; // 引入AppStore以获取API就绪状态
import { Skeleton } from "@/components/ui/skeleton";

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
  const appStore = useAppStore(); // 获取全局AppStore实例
  
  // 获取标签云数据
  const fetchTagCloudData = async () => {
    if (!appStore.isApiReady) {
      console.log('API尚未就绪，暂不获取标签云数据');
      return;
    }
    
    try {
      setLoading(true);
      // 调用后端API获取标签云数据
      const tagData = await invoke<TagItem[]>('get_tag_cloud_data', { limit: 100 });
      console.log('成功获取标签云数据:', tagData.length);
      setTags(tagData);
    } catch (error) {
      console.error('Error fetching tag cloud data:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // 监听API就绪状态变化
  useEffect(() => {
    if (appStore.isApiReady) {
      console.log('API就绪，获取标签云数据');
      fetchTagCloudData();
    }
  }, [appStore.isApiReady]);
  
  // 监听标签更新事件
  useEffect(() => {
    if (!appStore.isApiReady) {
      return; // API未就绪不设置监听器
    }
    
    // 监听标签更新事件
    const unlistenFn = listen('tags-updated', () => {
      console.log('收到tags-updated事件，刷新标签云');
      fetchTagCloudData();
    });
    
    return () => {
      // 清理事件监听器
      unlistenFn.then(unlisten => unlisten());
    };
  }, [appStore.isApiReady]);
  
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
    // 可以导航到标签搜索结果页面
    // navigate(`/search?tagIds=${tagId}`);
    // 或者通过其他方式处理
  };

  return (
    <SidebarGroup>
      <SidebarGroupLabel>
        <Tag className="mr-2 h-4 w-4" />
        {t('File Tags')}
      </SidebarGroupLabel>
      
      <ScrollArea className="h-[250px] px-0">
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
