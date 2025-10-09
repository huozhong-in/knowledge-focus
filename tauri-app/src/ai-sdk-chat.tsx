import { useState, useEffect, useRef, useCallback } from "react"
import { openUrl } from "@tauri-apps/plugin-opener";
import { Button } from "./components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  ChatSession,
  ChatMessage as ApiChatMessage,
  getSessionMessages,
  getSession,
  changeSessionTools,
  setMcpToolApiKey,
} from "./lib/chat-session-api"
import { useCoReadingTimer } from "./hooks/useCoReadingTimer"
import { CoReadingPauseWidget } from "./components/ui/co-reading-pause-widget"
import { exitCoReadingMode } from "./lib/chat-session-api"
import { handlePdfReaderScreenshot } from "./lib/pdfCoReadingTools"
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation"
import { Message, MessageContent, MessageAvatar } from "@/components/ai-elements/message"
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning"
import {
  PromptInput,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  // PromptInputButton,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input"
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from '@/components/ai-elements/tool';
import { useChat } from "@ai-sdk/react"
import { Response } from "@/components/ai-elements/response"
import { DefaultChatTransport } from "ai"
import { Actions, Action } from '@/components/ai-elements/actions'
import { GlobeIcon, CopyIcon, CircleXIcon, SearchIcon, RotateCcwIcon } from 'lucide-react'
import { Checkbox } from "./components/ui/checkbox"
import { useTranslation } from "react-i18next"
import { toast } from 'sonner';


interface AiSdkChatProps {
  sessionId?: string
  currentSession?: ChatSession | null // 外部传入的当前会话数据
  onCreateSessionFromMessage?: (
    firstMessageContent: string
  ) => Promise<ChatSession>
  resetTrigger?: number // 用于触发重置的数字，每次改变都会重置组件
  imagePath?: string // 用于接收从文件列表传来的图片路径
  imageSelectionKey?: number // 用于强制触发图片选择更新的key
  onSessionUpdate?: (updatedSession: ChatSession) => void // 会话更新回调
  tempSelectedTools?: string[] // 临时选择的工具列表
  onAddTempSelectedTool?: (toolName: string) => void // 添加临时工具回调
  onRemoveTempSelectedTool?: (toolName: string) => void // 移除临时工具回调
}

const createTempId = () => {
  if (typeof window !== "undefined" && typeof window.crypto !== "undefined" && "randomUUID" in window.crypto) {
    return window.crypto.randomUUID()
  }

  return `temp-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/**
 * AI SDK v5集成聊天组件
 * 使用useChat和AI Elements组件实现
 */
export function AiSdkChat({
  sessionId,
  currentSession: externalCurrentSession,
  onCreateSessionFromMessage,
  resetTrigger,
  imagePath,
  imageSelectionKey,
  onSessionUpdate,
  tempSelectedTools,
  onAddTempSelectedTool,
  onRemoveTempSelectedTool,
}: AiSdkChatProps) {
  const [effectiveSessionId, setEffectiveSessionId] = useState<
    string | undefined
  >(sessionId)
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null)
  const [isInitializing, setIsInitializing] = useState(true)
  const [input, setInput] = useState("")
  const [selectedImage, setSelectedImage] = useState<string | null>(null) // 存储选中的图片路径
  const [screenshotPreview, setScreenshotPreview] = useState<{path: string, metadata?: any} | null>(null) // 存储截图预览信息
  const [enableWebSearch, setEnableWebSearch] = useState(false) // 是否启用网络搜索功能
  // Tavily 工具相关状态
  const TAVILY_TOOL_NAME = 'search_use_tavily'
  const [tavilyEnabled, setTavilyEnabled] = useState(false)
  const [tavilyDialogOpen, setTavilyDialogOpen] = useState(false)
  const [tavilyApiKey, setTavilyApiKey] = useState("")
  // 控制 Search 下拉菜单开关，避免遮挡输入框导致无法聚焦
  const [actionMenuOpen, setActionMenuOpen] = useState(false)
  const { t } = useTranslation()

  const [refreshKey, setRefreshKey] = useState(0)

  const pendingAssistantIdRef = useRef<string | null>(null)

  // PDF共读模式定时器
  const coReadingTimer = useCoReadingTimer({
    session: currentSession,
    onPdfWindowLost: () => {
      console.log('🔴 PDF窗口失去可见性，显示暂停Widget')
    },
    onPdfWindowRegained: () => {
      console.log('🟢 PDF窗口重新可见，隐藏暂停Widget')
    },
    checkInterval: 3000 // 每3秒检查一次
  })

  // 判断是否应该显示暂停Widget (只在PDF真正不可见时显示)
  const shouldShowPauseWidget = currentSession?.scenario_id && 
                               coReadingTimer.isActive && 
                               coReadingTimer.isPdfTrulyInvisible === true

  // Widget操作处理函数
  const handleContinueReading = async () => {
    try {
      console.log('🔄 用户点击继续阅读，尝试恢复PDF窗口...')
      const success = await coReadingTimer.restorePdfWindow()
      if (success) {
        console.log('✅ PDF窗口已成功恢复')
      } else {
        console.warn('⚠️ PDF窗口恢复失败，请手动打开PDF文件')
      }
    } catch (error) {
      console.error('❌ 处理继续阅读操作失败:', error)
    }
  }

  const handleExitCoReading = async () => {
    if (currentSession) {
      try {
        const updatedSession = await exitCoReadingMode(currentSession.id)
        setCurrentSession(updatedSession)
        // 通知父组件会话已更新
        if (onSessionUpdate) {
          onSessionUpdate(updatedSession)
        }
        console.log('已退出共读模式')
      } catch (error) {
        console.error('退出共读模式失败:', error)
      }
    }
  }



  // 处理外部传入的会话数据更新
  useEffect(() => {
    if (externalCurrentSession && externalCurrentSession.id === parseInt(sessionId || '0')) {
      // console.log('📥 [DEBUG] 接收到外部会话更新, 更新内部状态:', externalCurrentSession)
      // console.log('📥 [DEBUG] 会话详细信息:', {
      //   id: externalCurrentSession.id,
      //   scenario_id: externalCurrentSession.scenario_id,
      //   metadata: externalCurrentSession.metadata,
      //   'metadata.pdf_path': externalCurrentSession.metadata?.pdf_path,
      //   'metadata全部内容': JSON.stringify(externalCurrentSession.metadata, null, 2)
      // })
      setCurrentSession(externalCurrentSession)
    }
  }, [externalCurrentSession, sessionId])

  // 处理临时工具状态：当没有真实会话时，从临时工具列表中恢复UI状态
  useEffect(() => {
    if (!currentSession?.id && tempSelectedTools) {
      const isTavilyTempSelected = tempSelectedTools.includes(TAVILY_TOOL_NAME)
      setTavilyEnabled(isTavilyTempSelected)
      setEnableWebSearch(isTavilyTempSelected)
      // console.log('📋 [DEBUG] 从临时工具状态恢复 UI:', {
      //   tempSelectedTools,
      //   tavilyEnabled: isTavilyTempSelected
      // })
    }
  }, [tempSelectedTools, currentSession?.id])

  // 当imagePath改变时，设置选中的图片
  // 使用imageSelectionKey来强制触发更新，解决取消后重新选择同一图片的bug
  useEffect(() => {
    if (imagePath) {
      setSelectedImage(imagePath)
    }
  }, [imagePath, imageSelectionKey])

  // 使用useChat hook集成AI SDK v5 - 使用DefaultChatTransport配置API
  const { messages, sendMessage, status, error, setMessages } = useChat({
    transport: new DefaultChatTransport({
      api: "http://127.0.0.1:60315/chat/agent-stream",
    }),
    onFinish: async ({ message }) => {
      console.log("[AiSdkChat] Message finished:", message.id)
      // 消息完成后的处理逻辑
    },
    onError: (error) => {
      console.error("[AiSdkChat] Chat error:", error)
    },
  })

  const clearAssistantPlaceholder = useCallback(() => {
    if (!pendingAssistantIdRef.current) return

    const placeholderId = pendingAssistantIdRef.current
    setMessages((prev: any[]) =>
      prev.filter((msg: any) => msg.id !== placeholderId)
    )
    pendingAssistantIdRef.current = null
  }, [setMessages])

  const handleRefresh = useCallback(() => {
    clearAssistantPlaceholder()
    setRefreshKey((key) => key + 1)
  }, [clearAssistantPlaceholder])

  useEffect(() => {
    if (!pendingAssistantIdRef.current) return

    const hasRealAssistantMessage = messages.some(
      (msg: any) =>
        msg.role === "assistant" &&
        msg.id !== pendingAssistantIdRef.current &&
        msg?.metadata?.placeholder !== true
    )

    if (hasRealAssistantMessage) {
      clearAssistantPlaceholder()
    }
  }, [messages, clearAssistantPlaceholder])

  useEffect(() => {
    if (status === "ready") {
      clearAssistantPlaceholder()
    }
  }, [status, clearAssistantPlaceholder])

  useEffect(() => {
    if (error) {
      clearAssistantPlaceholder()
    }
  }, [error, clearAssistantPlaceholder])

  // 当resetTrigger改变时，重置消息和输入框
  useEffect(() => {
    if (resetTrigger !== undefined) {
      setMessages([])
      setInput("")
      setEffectiveSessionId(undefined)
      setCurrentSession(null)
    }
  }, [resetTrigger, setMessages])

  // 当sessionId改变时，加载该会话的聊天记录并更新effectiveSessionId
  useEffect(() => {
    const loadSessionMessages = async () => {
      setIsInitializing(true)

      if (!sessionId) {
        // 没有sessionId时清空消息，显示欢迎状态
        setMessages([])
        setEffectiveSessionId(undefined)
        setCurrentSession(null)
        setIsInitializing(false)
        return
      }

      try {
        const sessionIdNum = parseInt(sessionId)
        if (isNaN(sessionIdNum)) {
          console.error("Invalid sessionId:", sessionId)
          setIsInitializing(false)
          return
        }

        console.log("🔄 加载会话聊天记录, sessionId:", sessionIdNum)
        
        // 加载会话信息（包含scenario_id等元数据）
        const session = await getSession(sessionIdNum)
        setCurrentSession(session)
        console.log("📋 会话信息加载完成:", session)
        // 恢复 Tavily 工具勾选状态和 API Key
        try {
          const selected = session.selected_tools || []
          const isEnabled = selected.includes(TAVILY_TOOL_NAME)
          setTavilyEnabled(isEnabled)
          setEnableWebSearch(isEnabled) // 同步恢复 Search 按钮状态
          
          // 从 tool_configs 中恢复 API Key
          if (session.tool_configs && session.tool_configs.search_use_tavily) {
            const tavilyConfig = session.tool_configs.search_use_tavily
            if (tavilyConfig.api_key) {
              setTavilyApiKey(tavilyConfig.api_key)
              console.log('📋 从会话恢复 Tavily API Key')
            }
          }
        } catch (e) {
          console.warn('恢复Tavily状态失败', e)
        }
        
        const result = await getSessionMessages(sessionIdNum, 1, 50, false) // 获取前50条消息，时间升序

        // 将ChatMessage转换为useChat的UIMessage格式
        // 暂时使用any类型来避免复杂的类型检查
        const convertedMessages: any[] = result.messages
          .map((msg: ApiChatMessage) => {
            // 检查消息是否有有效内容
            const hasValidParts =
              msg.parts &&
              msg.parts.length > 0 &&
              msg.parts.some(
                (part: any) =>
                  part.type === "text" && part.text && part.text.trim()
              )
            const hasValidContent = msg.content && msg.content.trim()

            // 如果既没有有效的parts也没有有效的content，跳过这条消息
            if (!hasValidParts && !hasValidContent) {
              console.warn(`跳过空内容消息: ${msg.message_id}`)
              return null
            }

            // 构建parts数组，优先使用msg.parts，如果为空则使用msg.content
            let parts: any[]
            if (hasValidParts) {
              parts = msg.parts
            } else if (hasValidContent) {
              parts = [{ type: "text", text: msg.content }]
            } else {
              // 这种情况理论上不会到达，但作为保险
              return null
            }

            return {
              id: msg.message_id || msg.id.toString(),
              role: msg.role as "user" | "assistant",
              parts: parts,
              createdAt: new Date(msg.created_at),
            }
          })
          .filter(Boolean) // 过滤掉null值

        setMessages(convertedMessages)
        setEffectiveSessionId(sessionId)
        pendingAssistantIdRef.current = null
        console.log("✅ 聊天记录加载完成，消息数量:", convertedMessages.length)        // 🎯 加载新会话后自动滚动到底部
        // 使用setTimeout确保DOM已更新
        setTimeout(() => {
          // 通过事件通知内部组件执行滚动
          window.dispatchEvent(new CustomEvent('scrollToBottomAfterLoad'))
        }, 100)
      } catch (error) {
        console.error("Failed to load session messages:", error)
        // 加载失败时清空消息
        setMessages([])
      } finally {
        setIsInitializing(false)
      }
    }

    loadSessionMessages()
  }, [sessionId, setMessages, refreshKey])

  // 根据官方文档，需要手动管理输入状态
  const handleFormSubmit = async (_message: any, e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()

    if ((!input.trim() && !selectedImage && !screenshotPreview) || status !== "ready") return

    const userMessage = input.trim()

    // 用于在本次消息发送中临时存储截图信息
    let currentScreenshotForMessage = screenshotPreview

    // 如果是co-reading模式且没有截图预览，先进行截图
    if (currentSession?.scenario_id && !screenshotPreview) {
      try {
        // 从当前会话获取PDF路径
        const pdfPath = currentSession?.metadata?.pdf_path
        if (!pdfPath) {
          console.error('当前会话中没有PDF路径信息，无法进行截图')
          return
        }
        
        const screenshotPath = await handlePdfReaderScreenshot({ pdfPath })
        if (screenshotPath) {
          // 获取文件元数据
          let fileMetadata = null
          try {
            const response = await fetch(`http://127.0.0.1:60315/file-screening/by-path-hash?file_path=${encodeURIComponent(screenshotPath)}`)
            if (response.ok) {
              fileMetadata = await response.json()
            }
          } catch (error) {
            console.warn('获取截图文件元数据失败:', error)
          }
          
          // 创建临时截图对象，用于本次消息发送
          currentScreenshotForMessage = { path: screenshotPath, metadata: fileMetadata }
          // console.log('🔍 [DEBUG] 新截图生成:', currentScreenshotForMessage)
          
          // 设置截图预览状态（用于UI显示）
          setScreenshotPreview(currentScreenshotForMessage)
          // 不返回，继续发送消息
        } else {
          // 截图失败，阻止发送并提示用户
          console.error('截图失败，无法在co-reading模式下发送消息')
          // 这里可以添加用户提示逻辑
          return
        }
      } catch (error) {
        console.error('截图过程出错:', error)
        // 截图失败，阻止发送并提示用户
        return
      }
    }

    // 构建消息内容，使用AI SDK v5的parts格式支持文本和多张图片
    const parts: any[] = []
    
    // 添加文本部分
    if (userMessage.trim()) {
      parts.push({
        type: 'text',
        text: userMessage.trim()
      })
    } else if (selectedImage || currentScreenshotForMessage) {
      // 如果只有图片没有文本，提供默认文本
      parts.push({
        type: 'text', 
        text: 'Please analyze these images'
      })
    }
    
    // 添加用户选择的图片
    if (selectedImage) {
      parts.push({
        type: 'file',
        filename: selectedImage.split('/').pop() || 'selected-image',
        mediaType: 'image/' + (selectedImage.split('.').pop()?.toLowerCase() || 'png'),
        url: `file://${selectedImage}`, // 使用file://协议的本地文件路径
      })
    }
    
    // 添加PDF截图
    if (currentScreenshotForMessage?.path) {
      parts.push({
        type: 'file',
        filename: currentScreenshotForMessage.path.split('/').pop() || 'pdf-screenshot',
        mediaType: 'image/' + (currentScreenshotForMessage.path.split('.').pop()?.toLowerCase() || 'png'),
        url: `file://${currentScreenshotForMessage.path}`, // 使用file://协议的本地文件路径
      })
    }
    
    // 构建AI SDK v5兼容的消息格式
    const messageContent: any = {
      parts: parts
    }

    clearAssistantPlaceholder()

    const assistantPlaceholderId = createTempId()

    const assistantPlaceholderMessage = {
      id: assistantPlaceholderId,
      role: "assistant" as const,
      parts: [
        {
          type: "text",
          text: "AI is thinking..."
        }
      ],
      metadata: { placeholder: true },
      createdAt: new Date()
    }

    pendingAssistantIdRef.current = assistantPlaceholderId

    setMessages((prev: any[]) => [
      ...prev,
      assistantPlaceholderMessage
    ])

    if (typeof window !== "undefined") {
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent("scrollToBottomAfterLoad"))
      }, 0)
    }

    // // 调试日志：输出消息内容
    // console.log('🔍 [DEBUG] 构建的消息内容:', JSON.stringify(messageContent, null, 2))
    // console.log('🔍 [DEBUG] parts数组:', JSON.stringify(parts, null, 2))
    // console.log('🔍 [DEBUG] selectedImage:', selectedImage)
    // console.log('🔍 [DEBUG] screenshotPreview:', screenshotPreview)
    // console.log('🔍 [DEBUG] currentScreenshotForMessage:', currentScreenshotForMessage)
    // console.log('🔍 [DEBUG] userMessage:', userMessage)
    // console.log('🔍 [DEBUG] 共读模式检查:', {
    //   hasScenarioId: !!currentSession?.scenario_id,
    //   screenshotPreviewExists: !!screenshotPreview,
    //   currentScreenshotExists: !!currentScreenshotForMessage,
    //   selectedImageExists: !!selectedImage
    // })

    // 检查是否需要创建会话（延迟创建逻辑）
    let currentSessionId = effectiveSessionId
    const executeSendMessage = async (sessionIdValue?: string | null) => {
      await sendMessage(
        messageContent,
        {
          body: {
            session_id: sessionIdValue ? Number(sessionIdValue) : undefined,
          },
        }
      )
    }

    try {
      if (!effectiveSessionId && onCreateSessionFromMessage) {
        try {
          const newSession = await onCreateSessionFromMessage(
            userMessage || "Image Analysis Request"
          )
          currentSessionId = String(newSession.id)
          setEffectiveSessionId(currentSessionId)
          console.log(
            "[AiSdkChat] Created new session:",
            newSession.id,
            "Name:",
            newSession.name
          )

          // 应用临时选择的工具到新创建的会话
          if (tempSelectedTools && tempSelectedTools.length > 0) {
            try {
              await changeSessionTools(newSession.id, tempSelectedTools, [])
              console.log(
                "[AiSdkChat] Applied temp tools to new session:",
                tempSelectedTools
              )

              // 清空临时工具选择（通过移除所有临时工具）
              if (onRemoveTempSelectedTool) {
                tempSelectedTools.forEach((toolName) => {
                  onRemoveTempSelectedTool(toolName)
                })
              }
            } catch (toolError) {
              console.error("[AiSdkChat] Failed to apply temp tools:", toolError)
            }
          }

          await executeSendMessage(currentSessionId)
        } catch (createError) {
          console.error("[AiSdkChat] Failed to create session:", createError)
          await executeSendMessage(undefined)
        }
      } else {
        await executeSendMessage(currentSessionId)
      }
    } catch (sendError) {
      console.error("[AiSdkChat] Failed to send message:", sendError)
      clearAssistantPlaceholder()
    }

    // 清空输入框和选中的图片/截图
    setInput("")
    setSelectedImage(null)
    setScreenshotPreview(null)
  }

  if (isInitializing) {
    return (
      <div className="flex flex-col flex-auto h-full items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col flex-auto h-full overflow-hidden relative">
      {/* PDF暂停状态Widget */}
      {shouldShowPauseWidget && currentSession && (
        <CoReadingPauseWidget
          session={currentSession}
          onContinueReading={handleContinueReading}
          onExitCoReading={handleExitCoReading}
        />
      )}
      <Conversation className="flex-1 h-[calc(100vh-176px)]">
        <ConversationContent className="p-1">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center text-muted-foreground">
                <h3 className="text-lg font-medium mb-2">
                  Knowledge Focus {t("AISDKCHAT.conversation_placeholder")}
                </h3>
                <p>
                  {t("AISDKCHAT.conversation_placeholder_2")}
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <Message key={message.id} from={message.role}>
                  <MessageContent>
                    {message.parts.map((part: any, index: number) => {
                      switch (part.type) {
                        case "text":
                          return message.role === "assistant" ? (
                            <div key={`${message.id}-${index}`}>
                              <Response key={index} className="pl-2">{part.text}</Response>
                              <Actions className="mt-2">
                                <Action
                                  onClick={() =>
                                    navigator.clipboard.writeText(part.text)
                                  }
                                  label="Copy"
                                >
                                  <CopyIcon className="size-4" />
                                </Action>
                                {error && (
                                  <Action
                                    onClick={handleRefresh}
                                    label="Refresh"
                                  >
                                    <RotateCcwIcon className="size-4" />
                                  </Action>
                                )}
                              </Actions>
                            </div>                            
                          ) : (
                            <div key={index}>{part.text}</div>
                          )
                        case "file":
                          // 处理图片文件
                          if (part.mediaType?.startsWith('image/')) {
                            // 从file://或本地路径中提取实际路径
                            const actualPath = part.url?.startsWith('file://') 
                              ? part.url.replace('file://', '') 
                              : part.url;
                            
                            return (
                              <div key={`${message.id}-${index}`} className="mt-2">
                                <img 
                                  src={`http://127.0.0.1:60315/image/thumbnail?file_path=${encodeURIComponent(actualPath || '')}&width=300&height=200`}
                                  alt={part.filename || 'Attached image'}
                                  className="max-w-xs max-h-48 rounded-lg border cursor-pointer"
                                  onClick={() => {
                                    // 点击时显示全尺寸图片
                                    openUrl(`http://127.0.0.1:60315/image/full?file_path=${encodeURIComponent(actualPath || '')}`);
                                  }}
                                  onError={(e) => {
                                    console.error('Failed to load image:', actualPath);
                                    const target = e.target as HTMLImageElement;
                                    target.alt = 'image load failed';
                                    target.className = 'max-w-xs max-h-48 rounded-lg border bg-muted flex items-center justify-center text-muted-foreground text-sm p-4';
                                  }}
                                />
                                {/* <div className="text-xs text-muted-foreground mt-1">
                                  {part.filename} (Click to view full image)
                                </div> */}
                              </div>
                            )
                          }
                          return null
                        case "reasoning":
                          return (
                            <Reasoning
                              key={`${message.id}-${index}`}
                              className="w-full"
                              isStreaming={status === "streaming"}
                            >
                              <ReasoningTrigger />
                              <ReasoningContent>{part.text}</ReasoningContent>
                            </Reasoning>
                          )
                        default:
                          // 处理工具调用相关的part类型
                          if (part.type.startsWith('tool-')) {
                            // 根据工具状态决定是否默认展开
                            const shouldDefaultOpen = part.state === 'output-available' || part.state === 'output-error'
                            
                            // 调试日志
                            // console.log('🔧 [DEBUG] Tool part detected:', {
                            //   type: part.type,
                            //   state: part.state,
                            //   input: part.input,
                            //   output: part.output,
                            //   errorText: part.errorText,
                            //   shouldDefaultOpen
                            // })
                            
                            return (
                              <Tool key={`${message.id}-${index}`} defaultOpen={shouldDefaultOpen}>
                                <ToolHeader 
                                  type={part.type} 
                                  state={part.state || 'input-available'} 
                                />
                                <ToolContent>
                                  {part.input && (
                                    <ToolInput input={part.input} />
                                  )}
                                  {(part.output || part.errorText) && (
                                    <ToolOutput
                                      output={part.output}
                                      errorText={part.errorText}
                                    />
                                  )}
                                </ToolContent>
                              </Tool>
                            )
                          }
                          return null
                      }
                  })}
                </MessageContent>
                <MessageAvatar 
                  src={message.role === 'user' ? '/user.png' : '/bot.png'}
                  name={message.role === 'user' ? 'User' : 'Assistant'}
                  className="size-6"
                />
              </Message>
            ))}
            
            {/* AI回复占位符 - 当正在等待AI回复时显示 */}
            </>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* 错误状态显示 */}
      {error && (
        <div className="p-4 bg-red-50 border-t border-red-200">
          <div className="text-red-800">Sorry, an error occurred. Please try again later.</div>
          <div className="mt-2">
            <Button onClick={handleRefresh} size="sm" variant="outline">
              Refresh
            </Button>
          </div>
        </div>
      )}

      {/* 输入区域 - 使用AI Elements */}
      <div className="p-1 relative">
        {/* 预览区域容器 - 浮动在输入框上方 */}
        {(selectedImage || screenshotPreview) && (
          <div className="absolute bottom-full left-2 right-2 mb-2 z-10">
            <div className="flex gap-2">
              {/* 图片预览区域 - 第一位 */}
              {selectedImage && (
                <div className="w-[300px] p-2 bg-muted/50 backdrop-blur-sm rounded-lg border shadow-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted-foreground">Selected Image:</span>
                    <Button
                      onClick={() => setSelectedImage(null)}
                      variant="ghost"
                      className="size-6 items-center"
                    >
                      <CircleXIcon className="inline size-4 m-1" />
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <img 
                      src={`http://127.0.0.1:60315/image/thumbnail?file_path=${encodeURIComponent(selectedImage)}&width=48&height=48`}
                      alt="Preview"
                      className="w-12 h-12 object-cover rounded border"
                      onError={(e) => {
                        console.error('Failed to load thumbnail:', selectedImage);
                        // 可以设置一个默认图标
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs truncate" title={selectedImage}>
                        {selectedImage.split('/').pop()}
                      </div>
                      <div className="text-xs text-muted-foreground truncate" title={selectedImage}>
                        {selectedImage}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* PDF共读状态指示器 - 浮动在输入框上方 */}
        {currentSession?.scenario_id && currentSession?.metadata?.pdf_path && (
          <div className="absolute bottom-full right-2 w-[300px] mb-2 p-2 bg-muted/50 backdrop-blur-sm rounded-lg border shadow-lg z-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-primary font-bold">📖 AI is co-reading PDF with you:</span>
              <div className="flex items-center gap-2">
                {!coReadingTimer.isPdfFocused && (
                  <Button
                    onClick={handleContinueReading}
                    variant="ghost"
                    className="size-6 items-center"
                    title="Find PDF window"
                    disabled={coReadingTimer.isPdfFocused === null} // 检测中时禁用按钮
                  >
                    <SearchIcon className="inline size-4 m-1" />
                  </Button>
                )}
                <Button
                onClick={() => handleExitCoReading()}
                variant="ghost"
                className="size-6 items-center"
                title="quit co-reading mode"
                >
                  <CircleXIcon className="inline size-4 m-1" />
                </Button>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-12 h-12 bg-muted-100 rounded border border-muted-200 flex items-center justify-center">
                <span className="text-muted-600 text-lg">📄</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-muted-800 truncate" title={currentSession.metadata.pdf_path}>
                  {currentSession.metadata.pdf_path.split('/').pop()}
                </div>
                <div className="text-xs text-muted-600 truncate" title={currentSession.metadata.pdf_path}>
                  {currentSession.metadata.pdf_path}
                </div>
              </div>
            </div>
          </div>
        )}
        
        <PromptInput onSubmit={handleFormSubmit} className="relative">
          <PromptInputBody className="border-0 m-0 p-0">
            <PromptInputTextarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={selectedImage ? "Describe what you want to know about this image..." : t("AISDKCHAT.input-message")}
            />
          </PromptInputBody>
          <PromptInputToolbar>
            <PromptInputTools>
              <PromptInputActionMenu open={actionMenuOpen} onOpenChange={setActionMenuOpen}>
                <PromptInputActionMenuTrigger variant={enableWebSearch ? "outline" : "ghost"}>
                  <GlobeIcon />
                  <span>Search</span>
                </PromptInputActionMenuTrigger>
                <PromptInputActionMenuContent>
                  <div className="flex flex-row justify-between items-center">
                    <Checkbox id="enable-web-search" className="mr-2"
                      checked={tavilyEnabled}
                      onCheckedChange={async (checked) => {
                        // console.log('🔍 [DEBUG] Tavily checkbox clicked:', {
                        //   checked,
                        //   currentSessionId: currentSession?.id,
                        //   tavilyApiKey: tavilyApiKey.trim(),
                        //   hasOnAddTempSelectedTool: !!onAddTempSelectedTool,
                        //   hasOnRemoveTempSelectedTool: !!onRemoveTempSelectedTool
                        // })
                        
                        const enable = checked === true
                        
                        if (enable) {
                          // 检查是否已有 key
                          if (!tavilyApiKey.trim()) {
                            // 没有 key 时显示提示并关闭菜单
                            // console.log('🔍 [DEBUG] No API key, showing toast')
                            toast.warning('Please configure your Tavily API Key first.')
                            setActionMenuOpen(false)
                            return
                          }
                          
                          // 如果有真实会话，直接更新服务端
                          if (currentSession?.id) {
                            // console.log('🔍 [DEBUG] Updating real session tools')
                            await changeSessionTools(currentSession.id, [TAVILY_TOOL_NAME], [])
                          } else {
                            // 如果是新会话，添加到临时工具列表
                            // console.log('🔍 [DEBUG] Adding to temp tools')
                            if (onAddTempSelectedTool) {
                              onAddTempSelectedTool(TAVILY_TOOL_NAME)
                            }
                          }
                          
                          setTavilyEnabled(true)
                          setEnableWebSearch(true)
                          setActionMenuOpen(false)
                        } else {
                          // 如果有真实会话，直接更新服务端
                          if (currentSession?.id) {
                            // console.log('🔍 [DEBUG] Removing from real session tools')
                            await changeSessionTools(currentSession.id, [], [TAVILY_TOOL_NAME])
                          } else {
                            // 如果是新会话，从临时工具列表中移除
                            // console.log('🔍 [DEBUG] Removing from temp tools')
                            if (onRemoveTempSelectedTool) {
                              onRemoveTempSelectedTool(TAVILY_TOOL_NAME)
                            }
                          }
                          
                          setTavilyEnabled(false)
                          setEnableWebSearch(false)
                          setActionMenuOpen(false)
                        }
                      }}
                    />
                    <img src="https://www.tavily.com/images/logo.svg" className="w-[50px] h-[20px]" />
                    <button type="button" className="text-xs text-muted-foreground underline"
                      onClick={async () => { 
                        setActionMenuOpen(false)
                        // 如果当前没有 API Key，才从服务器获取
                        if (!tavilyApiKey.trim()) {
                          try {
                            const response = await fetch(`http://127.0.0.1:60315/tools/mcp/get_api_key?tool_name=${encodeURIComponent(TAVILY_TOOL_NAME)}`)
                            if (response.ok) {
                              const json = await response.json()
                              if (json?.success && json?.api_key) {
                                setTavilyApiKey(json.api_key)
                              }
                            }
                          } catch (error) {
                            console.log('获取现有 API Key 失败:', error)
                          }
                        }
                        setTavilyDialogOpen(true)
                      }}
                    >config</button>
                </div>
                </PromptInputActionMenuContent>
              </PromptInputActionMenu>
            </PromptInputTools>
            <PromptInputSubmit
              className="absolute right-1 bottom-1"
              disabled={(!input.trim() && !selectedImage) || status !== "ready"}
              status={status}
            />
          </PromptInputToolbar>
        </PromptInput>

        {/* Tavily API Key 配置 Dialog */}
        <Dialog open={tavilyDialogOpen} onOpenChange={(open) => {
          setTavilyDialogOpen(open)
          if (!open) {
            // 关闭时尝试把焦点还给输入框
            setTimeout(() => {
              const el = document.querySelector('textarea[name="message"]') as HTMLTextAreaElement | null
              el?.focus()
            }, 50)
            // 确保下拉关闭
            setActionMenuOpen(false)
          }
        }}>
          <DialogContent className="max-w-2xl p-6">
            <DialogHeader>
              <DialogTitle>Setup Tavily API Key</DialogTitle>
              <DialogDescription>
                Input your Tavily API Key to enable web search capability.
                <a className="underline ml-1" href="#" onClick={() => openUrl('https://app.tavily.com/')}>Go to Tavily</a>
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <input
                className="w-full rounded border px-3 py-2 text-sm"
                placeholder="Tavily API Key"
                value={tavilyApiKey}
                onChange={(e) => setTavilyApiKey(e.target.value)}
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setTavilyDialogOpen(false)}>取消</Button>
                <Button
                  onClick={async () => {
                    if (!currentSession?.id) return
                    const key = tavilyApiKey.trim()
                    if (!key) return
                    const ok = await setMcpToolApiKey(TAVILY_TOOL_NAME, key)
                    if (!ok) return
                    await changeSessionTools(currentSession.id, [TAVILY_TOOL_NAME], [])
                    // 本地也保存一份，便于后续使用
                    setTavilyApiKey(key)
                    setTavilyEnabled(true)
                    setEnableWebSearch(true)
                    setTavilyDialogOpen(false)
                    setActionMenuOpen(false)
                  }}
                >Save and Enable</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
