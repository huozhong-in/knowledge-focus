import { Search, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { Label } from "@/components/ui/label"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarInput,
} from "@/components/ui/sidebar"
import { useTranslation } from 'react-i18next';
import { useEffect, useCallback } from 'react';
import { debounce } from 'lodash';
import axios from 'axios';
import { useAppStore } from '../main';

// 定义文件搜索结果接口
export interface FileSearchResult {
  id: number;
  file_path: string;
  file_name: string;
  file_size: number;
  extension: string | null;
  modified_time: string | null;
  category_id: number | null;
  labels: string[] | null;
  status: string;
}

interface AskMeFormProps extends React.ComponentProps<"form"> {
  collapsed?: boolean;
  onSearchResults?: (results: FileSearchResult[], query?: string) => void;
}

export function AskMeForm({ collapsed, className, onSearchResults, ...props }: AskMeFormProps) {
  if (collapsed) {
    return null
  }
  const { t } = useTranslation();
  
  // 使用全局状态
  const {
    searchQuery, 
    setSearchQuery, 
    isSearching, 
    setIsSearching, 
    setSearchResults,
    navigateToSearch
  } = useAppStore();
  
  // 使用debounce防止频繁请求
  const debouncedSearch = useCallback(
    debounce(async (query: string) => {
      if (!query.trim()) {
        setSearchResults([]);
        if (onSearchResults) {
          onSearchResults([]);
        }
        setIsSearching(false);
        return;
      }
      
      try {
        setIsSearching(true);
        const response = await axios.get<FileSearchResult[]>('http://localhost:60315/api/files/search', {
          params: { query, limit: 100 }
        });
        
        // 保存到全局状态
        setSearchResults(response.data);
        
        // 同时支持局部状态传递
        if (onSearchResults) {
          onSearchResults(response.data, query);
        }
      } catch (error) {
        console.error('文件搜索失败:', error);
        setSearchResults([]);
        if (onSearchResults) {
          onSearchResults([]);
        }
      } finally {
        setIsSearching(false);
      }
    }, 300),
    [setSearchResults, setIsSearching, onSearchResults] // 添加全局状态更新函数到依赖
  );
  
  // 当搜索查询变更时，触发搜索
  useEffect(() => {
    if (searchQuery.trim()) {
      setIsSearching(true);
      debouncedSearch(searchQuery);
      
      // 自动导航到搜索结果页面
      navigateToSearch();
    } else {
      setSearchResults([]);
      if (onSearchResults) {
        onSearchResults([], searchQuery);
      }
    }
    
    // 清理函数，取消待处理的debounce调用
    return () => {
      debouncedSearch.cancel();
    };
  }, [searchQuery, debouncedSearch, setSearchResults, navigateToSearch]);
  
  // 处理表单提交（阻止默认行为）
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault(); // 阻止表单默认提交行为
    
    if (searchQuery.trim()) {
      // 导航到搜索页面
      navigateToSearch();
    }
  };
  
  return (
    <form 
      className={cn("w-full", className)} 
      {...props} 
      onSubmit={handleSubmit} // 添加表单提交处理
    >
      <SidebarGroup className="py-0">
        <SidebarGroupContent className="relative">
          <Label htmlFor="ask" className="sr-only">
            {t('search-ask')}
          </Label>
          <SidebarInput
            id="ask"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('search-ask')}
            className="pl-6 pr-8 border-whiskey-300 focus-visible:ring-whiskey-400 focus-visible:ring-1 focus-visible:ring-opacity-50 focus-visible:border-whiskey-200 bg-whiskey-100 placeholder:text-whiskey-500 text-whiskey-800"
          />
          {isSearching ? (
            <Loader2 className="absolute right-2 top-1/2 size-4 -translate-y-1/2 animate-spin text-whiskey-400" />
          ) : (
            <Search 
              className="absolute left-2 top-1/2 size-4 -translate-y-1/2 select-none text-whiskey-400 hover:cursor-pointer" 
              onClick={() => {
                if (searchQuery.trim()) {
                  navigateToSearch();
                }
              }}
            />
          )}
        </SidebarGroupContent>
      </SidebarGroup>
    </form>
    // <p className="text-sm text-muted-foreground w-full flex items-center">
    //   Search{" "}
    //   <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
    //     <span className="text-xs">⌘</span>P
    //   </kbd>
    // </p>
  )
}
