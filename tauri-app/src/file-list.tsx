import {
  Pin,
  PinOff,
  FileText,
  File,
  FolderOpen,
  FileImageIcon,
  MessageCircle,
  ArrowDownLeftIcon,
  ArrowDownRightIcon,
  DramaIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useFileListStore } from "@/lib/fileListStore"
import { TaggedFile } from "@/types/file-types"
import { FileService } from "@/api/file-service"
import { revealItemInDir } from "@tauri-apps/plugin-opener"
import { fetch } from "@tauri-apps/plugin-http"
import { useState, useEffect, useRef, useCallback } from "react"
import { VectorizationProgress } from "@/components/VectorizationProgress"
import { useVectorizationStore } from "@/stores/useVectorizationStore"
import { toast } from "sonner"
import { useSettingsStore } from "./App"
import { useTranslation } from "react-i18next"
import { useScreeningResultUpdated } from "@/hooks/useBridgeEvents"
import { enterCoReadingMode, type ChatSession } from "@/lib/chat-session-api"
import { handlePdfReading } from "@/lib/pdfCoReadingTools"
import { useSidebar } from "@/components/ui/sidebar"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface FileItemProps {
  file: TaggedFile
  onTogglePin: (fileId: number, filePath: string) => void
  onTagClick: (tagName: string) => void
  onSelectImage?: (imagePath: string) => void // 新增图片选择回调
  onDramaIconClick?: (filePath: string) => void // 新增DramaIcon点击回调
}

function FileItem({
  file,
  onTogglePin,
  onTagClick,
  onSelectImage,
  onDramaIconClick,
}: FileItemProps) {
  const { getFileStatus } = useVectorizationStore()
  const vectorizationState = getFileStatus(file.path)
  const textExtensions = ["pdf", "docx", "pptx", "txt", "md", "markdown"]
  const imageExtensions = ["png", "jpg", "jpeg", "gif", "webp"] // bmp/svg不支持
  const getFileIcon = (extension?: string) => {
    if (!extension) return <File className="size-4" />

    if (textExtensions.includes(extension.toLowerCase())) {
      return <FileText className="size-4" />
    }
    if (imageExtensions.includes(extension.toLowerCase())) {
      return <FileImageIcon className="size-4" />
    }

    return <File className="size-4" />
  }

  // 生成随机颜色的标签样式
  const getTagColorClass = (index: number) => {
    const colors = [
      "bg-red-100 text-red-800 hover:bg-red-200",
      "bg-blue-100 text-blue-800 hover:bg-blue-200",
      "bg-green-100 text-green-800 hover:bg-green-200",
      "bg-yellow-100 text-yellow-800 hover:bg-yellow-200",
      "bg-purple-100 text-purple-800 hover:bg-purple-200",
      "bg-pink-100 text-pink-800 hover:bg-pink-200",
      "bg-indigo-100 text-indigo-800 hover:bg-indigo-200",
      "bg-orange-100 text-orange-800 hover:bg-orange-200",
    ]
    return colors[index % colors.length]
  }

  const handleTagClick = (tagName: string, event: React.MouseEvent) => {
    event.stopPropagation() // 防止触发文件点击事件
    onTagClick(tagName)
  }

  const handleRevealInDir = async (event: React.MouseEvent) => {
    event.stopPropagation()
    try {
      await revealItemInDir(file.path)
    } catch (error) {
      console.error("Failed to reveal item in directory:", error)
    }
  }

  const { t } = useTranslation()

  return (
    <div
      className={cn(
        "flex flex-1 border rounded-md p-2 mb-1.5 group relative min-w-0 @container hover:bg-muted/50 transition-colors",
        file.pinned ? "border-primary bg-primary/5" : "border-border bg-background"
      )}
    >
      <div className="flex items-start gap-1.5 min-w-0 flex-1">
        <div className="mt-0.5 shrink-0">{getFileIcon(file.extension)}</div>
        <div className="flex-1 min-w-0 w-0 pr-2">
          {" "}
          {/* w-0 强制宽度为0，flex-1让它填充，pr-2为按钮留空间 */}
          <div
            className="font-medium text-xs truncate leading-tight"
            title={file.file_name}
          >
            {file.file_name}
          </div>
          <div
            className="text-[10px] text-muted-foreground truncate leading-tight mt-0.5"
            title={file.path}
          >
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
        {/* 如果是图片文件，则多一个MessageCircle浮动按钮 */}
        {imageExtensions.includes(
          file.path.split(".").pop()?.toLocaleLowerCase() || ""
        ) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onSelectImage?.(file.path)}
            className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 transition-opacity bg-background/80 hover:bg-muted border border-border/50"
            title={t("FILELIST.send-to-chat")}
          >
            <MessageCircle className="h-2.5 w-2.5" />
          </Button>
        )}
        {/* 如果是PDF文件，则多一个DramaIcon浮动按钮 */}
        {(
          file.path.split(".").pop()?.toLocaleLowerCase() === "pdf"
        ) && (() => {
          const pdfVectorizationState = getFileStatus(file.path)
          const isVectorized = pdfVectorizationState?.status === 'completed'
          const isProcessing = pdfVectorizationState?.status === 'processing' || pdfVectorizationState?.status === 'queued'
          const isPinned = file.pinned
          
          // 只有同时满足已向量化且已Pin的条件才能点击共读
          const canCoRead = isVectorized && isPinned
          
          // 构建title文本
          let titleText = t("FILELIST.co-reading")
          if (!isPinned) {
            titleText += " (pin the file to enable)"
          } else if (!pdfVectorizationState) {
            titleText += " (not yet vectorized)"
          } else if (isProcessing) {
            titleText += " (vectorization in progress...)"
          } else if (pdfVectorizationState.status === 'failed') {
            titleText += " (vectorization failed, please retry pinning)"
          } else if (canCoRead) {
            titleText += " (ready to co-read)"
          } else {
            titleText += " (unable to co-read)"
          }
          
          return (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                if (canCoRead) {
                  onDramaIconClick?.(file.path)
                }
              }}
              className={cn(
                "h-5 w-5 p-0 !opacity-0 group-hover:!opacity-100 transition-opacity border border-border/50",
                {
                  "bg-green-50/90 hover:bg-green-100 text-green-600 group-hover:animate-bounce cursor-pointer": canCoRead,
                  "bg-yellow-50/90 hover:bg-yellow-100 text-yellow-600 animate-pulse cursor-wait": isProcessing && isPinned && !canCoRead,
                  "bg-muted/50 hover:bg-muted text-muted-foreground cursor-not-allowed": !canCoRead && !(isProcessing && isPinned)
                }
              )}
              title={titleText}
              disabled={!canCoRead}
            >
              <DramaIcon className="h-2.5 w-2.5" />
              {/* 向量化完成且已Pin状态指示器 */}
              {canCoRead && (
                <div className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-green-500 rounded-full border border-white" />
              )}
              {/* 处理中状态指示器（仅当已Pin时显示） */}
              {isProcessing && isPinned && (
                <div className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-yellow-500 rounded-full border border-white animate-pulse" />
              )}
            </Button>
          )
        })()}
        {/* Reveal in Dir 按钮 - hover时显示 */}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRevealInDir}
          className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 transition-opacity bg-background/80 hover:bg-muted border border-border/50"
          title={t("FILELIST.show-in-folder")}
        >
          <FolderOpen className="h-2.5 w-2.5" />
        </Button>

        {/* Pin 按钮 - pinned时始终显示，未pinned时hover显示 */}
        {textExtensions.includes(
          file.path.split(".").pop()?.toLocaleLowerCase() || ""
        ) && (
          <Button
            variant={file.pinned ? "default" : "ghost"}
            size="sm"
            onClick={() => onTogglePin(file.id, file.path)}
            className={`h-5 w-5 p-0 transition-opacity ${
              file.pinned
                ? "opacity-100"
                : "opacity-0 group-hover:opacity-100 bg-background/80 hover:bg-muted border border-border/50"
            }`}
            title={
              file.pinned ? t("FILELIST.unpin-file") : t("FILELIST.pin-file")
            }
          >
            {file.pinned ? (
              <Pin className="h-2.5 w-2.5" />
            ) : (
              <PinOff className="h-2.5 w-2.5" />
            )}
          </Button>
        )}
      </div>
    </div>
  )
}

interface FileListProps {
  currentSessionId?: number | null
  onAddTempPinnedFile?: (
    filePath: string,
    fileName: string,
    metadata?: Record<string, any>
  ) => void
  onRemoveTempPinnedFile?: (filePath: string) => void
  onSelectImage?: (imagePath: string) => void // 新增图片选择回调
  onSessionUpdate?: (updatedSession: any) => void // 新增会话更新回调
  onCreateSessionFromMessage?: (firstMessageContent: string) => Promise<ChatSession> // 新增创建会话回调
}

export function FileList({
  currentSessionId,
  onAddTempPinnedFile,
  onRemoveTempPinnedFile,
  onSelectImage,
  onSessionUpdate,
  onCreateSessionFromMessage,
}: FileListProps) {
  const {
    getFilteredFiles,
    togglePinnedFile,
    isLoading,
    error,
    setFiles,
    setLoading,
    setError,
  } = useFileListStore()
  const { setFileStatus, setFileStarted, setFileFailed, getFileStatus } =
    useVectorizationStore()
  const { openSettingsPage } = useSettingsStore()
  const files = getFilteredFiles()

  // 搜索框状态和引用
  const [searchKeyword, setSearchKeyword] = useState("")
  const searchInputRef = useRef<HTMLInputElement>(null)

  // 共读模式确认对话框状态
  const [coReadingDialogOpen, setCoReadingDialogOpen] = useState(false)
  const [selectedPdfPath, setSelectedPdfPath] = useState<string | null>(null)
  const [coReadingSessionId, setCoReadingSessionId] = useState<number | null>(null)

  // 获取侧边栏控制函数
  const { setOpen } = useSidebar()

  const { t } = useTranslation()

  const [screeningResultCount, setScreeningResultCount] = useState<number>(0)
  const fetchScreeningResultCount = useCallback(async () => {
    // 调用API获取筛选结果数量
    const url = "http://127.0.0.1:60315/file-screening/total"
    const response = await fetch(url)
    const result = await response.json()
    if (result.success) {
      setScreeningResultCount(result.total_count)
    }
  }, [])
  useEffect(() => {
    fetchScreeningResultCount()
    // return () => {

    // };
  }, [])

  // 监听筛选结果数量变化事件
  useScreeningResultUpdated(() => {
    try {
      fetchScreeningResultCount()
    } catch (error) {
      console.error("处理筛选结果更新事件时出错:", error)
    }
  })

  // 添加键盘快捷键监听 - Cmd+K 聚焦搜索框
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // 检测 Cmd+K (macOS) 或 Alt+K (Windows/Linux)
      if ((event.metaKey || event.altKey) && event.key === "k") {
        event.preventDefault()
        // 聚焦到搜索输入框
        searchInputRef.current?.focus()
        searchInputRef.current?.select() // 同时选中现有文本
      }
    }

    document.addEventListener("keydown", handleKeyDown)

    return () => {
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  // Pin文件API调用
  const pinFileAPI = async (
    filePath: string
  ): Promise<{ success: boolean; taskId?: number; error?: string }> => {
    try {
      let result: any

      if (currentSessionId) {
        // 有会话时，首先使用会话相关的pin-file API将文件关联到会话
        const sessionUrl = `http://127.0.0.1:60315/chat/sessions/${currentSessionId}/pin-file`
        const sessionBody = {
          file_path: filePath,
          file_name: filePath.split("/").pop() || filePath,
          metadata: {},
        }

        const sessionResponse = await fetch(sessionUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(sessionBody),
        })

        if (!sessionResponse.ok) {
          throw new Error(
            `Session pin failed: HTTP ${sessionResponse.status}: ${sessionResponse.statusText}`
          )
        }

        const sessionResult = await sessionResponse.json()

        if (!sessionResult.success) {
          throw new Error(
            `Session pin failed: ${sessionResult.error || "Unknown error"}`
          )
        }

        // 成功关联到会话后，再调用向量化任务创建API
        const vectorizeUrl = "http://127.0.0.1:60315/pin-file"
        const vectorizeBody = { file_path: filePath }

        const vectorizeResponse = await fetch(vectorizeUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(vectorizeBody),
        })

        if (!vectorizeResponse.ok) {
          throw new Error(
            `Vectorization failed: HTTP ${vectorizeResponse.status}: ${vectorizeResponse.statusText}`
          )
        }

        result = await vectorizeResponse.json()

        // 检查是否是模型配置缺失的错误
        if (!result.success && result.error_type === "model_missing") {
          handleModelMissingError(result)
          return result
        }
      } else {
        // 没有会话时，使用临时pin机制
        // 1. 添加到临时pin文件列表
        const fileName = filePath.split("/").pop() || filePath
        onAddTempPinnedFile?.(filePath, fileName, {})

        // 2. 调用向量化API进行处理
        const url = "http://127.0.0.1:60315/pin-file"
        const body = { file_path: filePath }

        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        result = await response.json()
      }

      // 检查是否是模型配置缺失的错误
      if (!result.success && result.error_type === "model_missing") {
        handleModelMissingError(result)
        return result
      }

      return result
    } catch (error) {
      console.error("Pin file API error:", error)
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      }
    }
  }

  // 处理模型配置缺失的情况
  const handleModelMissingError = (response: any) => {
    const confirmMessage = `${response.message}\n\njump to settings page to configure?`

    // 使用原生confirm对话框
    if (confirm(confirmMessage)) {
      // 用户确认跳转到设置页面
      openSettingsPage("aimodels")
    }
  }

  // 取消Pin文件API调用
  const unpinFileAPI = async (
    filePath: string
  ): Promise<{ success: boolean; error?: string }> => {
    try {
      if (currentSessionId) {
        // 有会话时，使用会话相关的unpin-file API
        const url = `http://127.0.0.1:60315/chat/sessions/${currentSessionId}/pinned-files`
        const response = await fetch(
          `${url}?file_path=${encodeURIComponent(filePath)}`,
          {
            method: "DELETE",
          }
        )

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const result = await response.json()
        return result
      } else {
        // 没有会话时，从临时pin文件列表中移除
        onRemoveTempPinnedFile?.(filePath)
        return { success: true }
      }
    } catch (error) {
      console.error("Unpin file API error:", error)
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      }
    }
  }

  const handleTogglePin = async (fileId: number, filePath: string) => {
    const file = files.find((f) => f.id === fileId)
    if (!file) return

    // 如果要取消pin，调用unpin API
    if (file.pinned) {
      try {
        const result = await unpinFileAPI(filePath)

        if (result.success) {
          togglePinnedFile(fileId)
          toast.success(
            t("FILELIST.unpin-file-success", { file_name: file.file_name })
          )
        } else {
          toast.error(`${t("FILELIST.unpin-file-failure")}: ${result.error}`)
        }
      } catch (error) {
        toast.error(
          `${t("FILELIST.unpin-file-failure")}: ${error instanceof Error ? error.message : "Unknown error"}`
        )
      }
      return
    }

    // 如果要pin文件，调用API并设置向量化状态
    try {
      // 设置初始状态
      setFileStatus(filePath, "queued")

      // 调用API
      const result = await pinFileAPI(filePath)

      if (result.success) {
        // API成功，更新pin状态和向量化任务ID
        togglePinnedFile(fileId)
        setFileStarted(filePath, result.taskId?.toString() || "")

        toast.success(
          t("FILELIST.vectorization-start", { file_name: file.file_name })
        )
      } else {
        // 检查是否是模型配置缺失的错误
        if ((result as any).error_type === "model_missing") {
          // 处理模型配置缺失的情况
          handleModelMissingError(result)
          // 不设置向量化失败状态，因为这是配置问题不是文件问题
        } else {
          // API失败，设置错误状态
          setFileFailed(filePath, "", {
            message:
              result.error || t("FILELIST.VectorizationFileState.failed"),
            helpLink:
              "https://github.com/huozhong-in/knowledge-focus/wiki/troubleshooting",
          })

          toast.error(
            `${t("FILELIST.VectorizationFileState.failed")}: ${result.error}`
          )
        }
      }
    } catch (error) {
      // 网络或其他错误
      setFileFailed(filePath, "", {
        message:
          error instanceof Error ? error.message : t("FILELIST.NetworkError"),
        helpLink:
          "https://github.com/huozhong-in/knowledge-focus/wiki/troubleshooting",
      })

      toast.error(t("FILELIST.NetworkError"))
    }
  }

  const handleTagClick = async (tagName: string) => {
    try {
      setLoading(true)
      setError(null)

      // 按标签名搜索文件
      const newFiles = await FileService.searchFilesByTags([tagName], "AND")
      setFiles(newFiles)

      console.log(`Found ${newFiles.length} files for tag: ${tagName}`)
    } catch (error) {
      console.error("Error searching files by tag:", error)
      setError(
        error instanceof Error ? error.message : t("FILELIST.search-failure")
      )
    } finally {
      setLoading(false)
    }
  }

  // 处理DramaIcon点击 - 打开确认对话框
  const handleDramaIconClick = async (filePath: string) => {
    // 如果没有当前会话ID，自动创建一个新会话
    let sessionId = currentSessionId
    if (!sessionId && onCreateSessionFromMessage) {
      try {
        const fileName = filePath.split('/').pop() || 'unknown'
        const newSession = await onCreateSessionFromMessage(`PDF共读: ${fileName}`)
        sessionId = newSession.id
        
        // 通知父组件会话已创建
        onSessionUpdate?.(newSession)
        
        toast.success("已自动创建新会话用于PDF共读")
      } catch (error) {
        console.error("创建会话失败:", error)
        toast.error("Failed to create session. Unable to enter co-reading mode.")
        return
      }
    } else if (!sessionId) {
      toast.error("Unable to create session. Please select a session first.")
      return
    }

    // 确保PDF文件被pin到会话中
    try {
      const fileName = filePath.split('/').pop() || 'unknown'
      // 检查文件是否已经被pin，如果没有则pin它
      const file = getFilteredFiles().find(f => f.path === filePath)
      if (file && !file.pinned) {
        onAddTempPinnedFile?.(filePath, fileName, { type: 'pdf', auto_pinned_for_co_reading: true })
      }
    } catch (error) {
      console.warn("Pin PDF文件失败:", error)
      // 不阻止共读流程，继续执行
    }

    // 保存会话ID供后续使用
    setCoReadingSessionId(sessionId)

    // 检查多模态向量化状态 - 只有完成向量化的PDF文件才能进入共读模式
    const vectorizationState = getFileStatus(filePath)
    if (!vectorizationState || vectorizationState.status !== 'completed') {
      if (!vectorizationState) {
        toast.error("The file has not undergone multimodal vectorization yet. Please pin the file to complete vectorization before trying to co-read.")
      } else if (vectorizationState.status === 'processing') {
        toast.error("The file is currently being processed for multimodal vectorization. Please wait for it to complete before trying to co-read.")
      } else if (vectorizationState.status === 'queued') {
        toast.error("The file's multimodal vectorization task is queued. Please wait for it to complete before trying to co-read.")
      } else if (vectorizationState.status === 'failed') {
        toast.error("The file's multimodal vectorization failed. Please re-pin the file or check the file format.")
      }
      return
    }

    setSelectedPdfPath(filePath)
    setCoReadingDialogOpen(true)
  }

  // 处理进入共读模式（确认后执行）
  const handleEnterCoReading = async () => {
    // 使用保存的会话ID，如果没有则使用当前会话ID
    const sessionIdToUse = coReadingSessionId || currentSessionId
    
    if (!selectedPdfPath || !sessionIdToUse) {
      console.error("缺少必要参数:", { selectedPdfPath, sessionIdToUse, coReadingSessionId, currentSessionId })
      return
    }

    try {
      setCoReadingDialogOpen(false) // 先关闭对话框
      
      // 调用进入共读模式API
      const updatedSession = await enterCoReadingMode(sessionIdToUse, selectedPdfPath)
      
      // console.log('🎯 [DEBUG] FileList收到API返回的updatedSession:', {
      //   id: updatedSession.id,
      //   scenario_id: updatedSession.scenario_id,
      //   metadata: updatedSession.metadata,
      //   'metadata.pdf_path': updatedSession.metadata?.pdf_path,
      //   '是否有metadata': !!updatedSession.metadata,
      //   '是否有pdf_path': !!updatedSession.metadata?.pdf_path,
      //   'pdf_path值': updatedSession.metadata?.pdf_path,
      //   'selectedPdfPath': selectedPdfPath,
      //   '路径是否一致': updatedSession.metadata?.pdf_path === selectedPdfPath,
      //   '完整会话数据': JSON.stringify(updatedSession, null, 2)
      // })
      
      // 通知父组件会话已更新
      onSessionUpdate?.(updatedSession)
      // console.log('🔄 [DEBUG] FileList调用onSessionUpdate，传递会话:', updatedSession.id)

      toast.success(`Entered PDF Co-Reading Mode: ${selectedPdfPath.split('/').pop()}`)
      // console.log('进入共读模式成功:', updatedSession)
      
      // 调用PDF阅读器工具，打开PDF并设置分屏布局
      // console.log('开始调用handlePdfReading打开PDF阅读器...')
      const pdfCenterPoint = await handlePdfReading({ pdfPath: selectedPdfPath })
      
      if (pdfCenterPoint) {
        // console.log('PDF阅读器已成功打开并设置分屏布局:', pdfCenterPoint)
        toast.success('PDF reader opened and split layout set')
      } else {
        console.warn('PDF阅读器打开失败或未能设置分屏布局')
        toast.warning('PDF reader may not have been correctly set up for split layout')
      }
      
      // 🎯 开启共读模式后自动收起侧边栏，为PDF阅读提供更大空间
      // console.log('📱 [共读优化] 自动收起侧边栏以优化阅读布局...')
      setOpen(false)
    } catch (error) {
      console.error('进入共读模式失败:', error)
      toast.error(`Enter Co-Reading Mode Failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setSelectedPdfPath(null)
      setCoReadingSessionId(null)
    }
  }

  // 处理路径搜索
  const handlePathSearch = async () => {
    if (!searchKeyword.trim()) {
      return
    }

    try {
      setLoading(true)
      setError(null)

      // 按路径关键字搜索文件
      const newFiles = await FileService.searchFilesByPath(searchKeyword.trim())
      setFiles(newFiles)

      console.log(
        `Found ${newFiles.length} files for path keyword: ${searchKeyword}`
      )
    } catch (error) {
      console.error("Error searching files by path:", error)
      setError(
        error instanceof Error ? error.message : t("FILELIST.search-failure")
      )
    } finally {
      setLoading(false)
    }
  }

  // 处理回车键搜索
  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === "Enter") {
      handlePathSearch()
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b p-2 shrink-0">
          <p className="text-sm">{t("FILELIST.search-results")}</p>
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
    )
  }

  if (error) {
    return (
      <div className="flex flex-col h-full">
        <div className="border-b p-2 shrink-0">
          <p className="text-sm">{t("FILELIST.search-results")}</p>
          <p className="text-xs text-destructive">
            {t("FILELIST.search-failure")}
          </p>
        </div>
        <div className="p-2 text-center text-xs text-muted-foreground">
          {error}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col w-full h-full overflow-auto">
      <div className="p-3 h-[50px]">
        <div className="text-sm">{t("FILELIST.pin-file-for-chat")}</div>
        <div className="flex flex-row items-end text-xs text-muted-foreground">
          <ArrowDownLeftIcon className="size-3" />
          {t("FILELIST.tap-tag-or-search-file-name")}
          <ArrowDownRightIcon className="size-3" />
        </div>
      </div>
      <div className="h-[45px] flex flex-row w-full items-center justify-between p-2 gap-2 border-b border-border/50 bg-gradient-to-r from-background to-muted/20">
        <div className="flex items-center gap-2">
          {/* 文件数量展示 - 简洁可爱的徽章样式 */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20">
            <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></div>
            <span className="text-xs font-medium text-primary">
              {files.length}
            </span>
            <span className="text-xs text-muted-foreground/60">of</span>
            <span className="text-xs text-muted-foreground font-medium">
              {screeningResultCount.toLocaleString()}
            </span>
          </div>
        </div>
        <div className="flex flex-row items-center gap-2 justify-end">
          <Input
            ref={searchInputRef}
            type="text"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            onKeyDown={handleKeyPress}
            className="h-7 text-xs max-w-36 border border-muted-foreground/30 bg-background/90 focus:border-primary/50 focus:bg-background transition-all duration-200 placeholder:text-muted-foreground/50"
            placeholder="⌘ K to search"
          />
          <Button
            type="submit"
            variant="secondary"
            size="sm"
            onClick={handlePathSearch}
            disabled={isLoading || !searchKeyword.trim()}
            className="h-7 px-3 text-xs bg-primary/10 hover:bg-primary/20 border border-primary/30 hover:border-primary/50 text-primary hover:text-primary transition-all duration-200 disabled:opacity-50 font-medium"
          >
            {t("FILELIST.search")}
          </Button>
        </div>
      </div>
      <ScrollArea className="flex-1 p-3 h-[calc(100%-95px)] @container">
        {files.length === 0 ? (
          <div className="text-center py-6">
            <FileText className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
            <p className="text-xs text-muted-foreground px-2 leading-relaxed">
              {t("FILELIST.tap-tag-or-search-file-name-detail")}
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
                onSelectImage={onSelectImage}
                onDramaIconClick={handleDramaIconClick}
              />
            ))}
          </div>
        )}
      </ScrollArea>

      {/* PDF共读模式确认对话框 */}
      <Dialog open={coReadingDialogOpen} onOpenChange={setCoReadingDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>📖 Enter PDF Co-Reading Mode</DialogTitle>
            <DialogDescription>
              The default PDF reader will be used to open the following file, and a split-screen layout will be set:
              <br />
              <span className="font-mono text-sm mt-2 block truncate" title={selectedPdfPath || ""}>
                {selectedPdfPath?.split('/').pop()}
              </span>
              <span className="text-xs text-muted-foreground block mt-1">
                The application will automatically adjust to display on the left, with the PDF reader on the right.
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCoReadingDialogOpen(false)
                setSelectedPdfPath(null)
                setCoReadingSessionId(null)
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleEnterCoReading}>
              Confirm Start Co-Reading
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
