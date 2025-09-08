import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Tags, MessageCircle } from "lucide-react"
import { useTagCloudStore } from "@/lib/tagCloudStore"
import { ChatSession } from "./lib/chat-session-api"
import { useFileListStore } from "@/lib/fileListStore"
import { FileService } from "@/api/file-service"

interface CollapsedQuickAccessProps {
  sessions: ChatSession[]
  onSessionClick: (session: ChatSession) => void
}

export function CollapsedQuickAccess({ 
  sessions, 
  onSessionClick 
}: CollapsedQuickAccessProps) {
  // 获取标签数据
  const { tags } = useTagCloudStore()
  const { setFiles, setLoading, setError } = useFileListStore()

  // 获取Top10标签（按权重排序）
  const topTags = tags
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 10)

  // 获取Top10对话（按时间排序，和展开状态一致）
  const topSessions = sessions.slice(0, 10)

  // 处理标签点击
  const handleTagClick = async (tagName: string) => {
    try {
      setLoading(true)
      setError(null)
      
      // 按标签名搜索文件
      const files = await FileService.searchFilesByTags([tagName], 'AND')
      setFiles(files)
      
      console.log(`Found ${files.length} files for tag: ${tagName}`)
    } catch (error) {
      console.error('Error searching files by tag:', error)
      setError(error instanceof Error ? error.message : '搜索失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full justify-start items-center pl-1">
        <div className="space-y-1">
          <Separator className="bg-border my-4" />
          {/* 标签Top10区域 */}
          {topTags.length > 0 && (
            <div className="space-y-1">
              {/* 分组标题 */}
              <div className="flex items-center justify-center">
                <Tags className="size-4" />
              </div>
              
              {/* 标签按钮列表 */}
              <div className="space-y-1">
                {topTags.map((tag, index) => (
                  <Tooltip key={tag.id} delayDuration={0}>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="size-5 p-0 text-xs font-medium justify-center "
                        onClick={() => handleTagClick(tag.name)}
                      >
                        <span className="font-semibold">
                          {index + 1}
                        </span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs">
                      <div className="text-sm">
                        <div className="font-medium">{tag.name}</div>
                        <div className="text-xs">
                          Files: {tag.weight}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </div>
          )}

          {/* 分隔线 */}
          {topTags.length > 0 && topSessions.length > 0 && (
            <Separator className="bg-border my-4" />
          )}

          {/* 对话Top10区域 */}
          {topSessions.length > 0 && (
            <div className="space-y-1">
              {/* 分组标题 */}
              <div className="flex items-center justify-center">
                <MessageCircle className="size-4" />
              </div>
              
              {/* 对话按钮列表 */}
              <div className="space-y-1">
                {topSessions.map((session, index) => (
                  <Tooltip key={session.id} delayDuration={0}>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="size-5 p-0 text-xs font-medium justify-center "
                        onClick={() => onSessionClick(session)}
                      >
                        <span className="font-semibold">
                          {index + 1}
                        </span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs">
                      <div className="text-sm">
                        <div className="font-medium line-clamp-2">{session.name}</div>
                        <div className="text-xs">
                          {new Date(session.updated_at).toLocaleDateString()}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </div>
          )}
        </div>
    </div>
  )
}
