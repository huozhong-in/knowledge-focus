import { SearchResults } from "./search-results";
import { useAppStore } from "./main";

export function SearchPage() {
  // 使用全局状态
  const { searchResults, searchQuery } = useAppStore();
  
  return (
    <div className="flex flex-col h-full">
      <div className="p-4">
        <h1 className="text-2xl font-bold mb-4">文件搜索</h1>
        {/* 移除重复的搜索表单，使用全局状态中的搜索结果 */}
      </div>
      <div className="flex-1 overflow-auto">
        <SearchResults results={searchResults} searchQuery={searchQuery} />
      </div>
    </div>
  );
}

export default SearchPage;
