import { useState, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { openUrl } from "@tauri-apps/plugin-opener";
import { Button } from "./components/ui/button";
import {
  ChatSession,
  ChatMessage as ApiChatMessage,
  getSessionMessages,
  getSession,
} from "./lib/chat-session-api"
import { useCoReadingTimer } from "./hooks/useCoReadingTimer"
import { CoReadingPauseWidget } from "./components/ui/co-reading-pause-widget"
import { exitCoReadingMode } from "./lib/chat-session-api"
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
  PromptInputButton,
  // PromptInputModelSelect,
  // PromptInputModelSelectContent,
  // PromptInputModelSelectItem,
  // PromptInputModelSelectTrigger,
  // PromptInputModelSelectValue,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input"
// import {
//   Tool,
//   ToolContent,
//   ToolHeader,
//   ToolInput,
//   ToolOutput,
// } from '@/components/ai-elements/tool';
import { useChat } from "@ai-sdk/react"
import { Response } from "@/components/ai-elements/response"
import { DefaultChatTransport } from "ai"
import { Actions, Action } from '@/components/ai-elements/actions'
import { GlobeIcon, MicIcon, CopyIcon, CircleXIcon, SearchIcon } from 'lucide-react'
import { useTranslation } from "react-i18next"


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
}: AiSdkChatProps) {
  const [effectiveSessionId, setEffectiveSessionId] = useState<
    string | undefined
  >(sessionId)
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null)
  const [isInitializing, setIsInitializing] = useState(true)
  const [input, setInput] = useState("")
  const [selectedImage, setSelectedImage] = useState<string | null>(null) // 存储选中的图片路径

  const { t } = useTranslation()

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

  // // 调试日志：追踪状态变化
  // useEffect(() => {
  //   console.log('🔍 [DEBUG] AiSdkChat状态更新:', {
  //     sessionId: currentSession?.id,
  //     scenarioId: currentSession?.scenario_id,
  //     pdfPath: currentSession?.metadata?.pdf_path,
  //     timerActive: coReadingTimer.isActive,
  //     pdfFocused: coReadingTimer.isPdfFocused,
  //     pdfTrulyInvisible: coReadingTimer.isPdfTrulyInvisible,
  //     windowStatus: coReadingTimer.windowStatus
  //   })
  // }, [
  //   currentSession?.id,
  //   currentSession?.scenario_id, 
  //   currentSession?.metadata?.pdf_path,
  //   coReadingTimer.isActive,
  //   coReadingTimer.isPdfFocused,
  //   coReadingTimer.isPdfTrulyInvisible
  // ])

  // 判断是否应该显示暂停Widget (只在PDF真正不可见时显示)
  const shouldShowPauseWidget = currentSession?.scenario_id && 
                               coReadingTimer.isActive && 
                               coReadingTimer.isPdfTrulyInvisible === true

  // 调试日志：追踪Widget显示条件
  useEffect(() => {
    console.log('🎯 [DEBUG] Widget显示条件检查:', {
      hasScenarioId: !!currentSession?.scenario_id,
      timerActive: coReadingTimer.isActive,
      pdfTrulyInvisible: coReadingTimer.isPdfTrulyInvisible,
      shouldShowPauseWidget,
      '条件1-有scenarioId': !!currentSession?.scenario_id,
      '条件2-定时器激活': coReadingTimer.isActive,
      '条件3-PDF不可见': coReadingTimer.isPdfTrulyInvisible === true
    })
  }, [currentSession?.scenario_id, coReadingTimer.isActive, coReadingTimer.isPdfTrulyInvisible, shouldShowPauseWidget])

  // 调试日志：追踪PDF状态指示器显示条件
  const shouldShowPdfIndicator = currentSession?.scenario_id && currentSession?.metadata?.pdf_path
  useEffect(() => {
    console.log('📱 [DEBUG] PDF状态指示器显示条件:', {
      hasScenarioId: !!currentSession?.scenario_id,
      hasPdfPath: !!currentSession?.metadata?.pdf_path,
      shouldShowPdfIndicator,
      pdfPath: currentSession?.metadata?.pdf_path
    })
  }, [currentSession?.scenario_id, currentSession?.metadata?.pdf_path, shouldShowPdfIndicator])

  // 定时日志：让用户感受到定时器的存在
  useEffect(() => {
    if (coReadingTimer.isActive) {
      const logInterval = setInterval(() => {
        console.log('⏰ [定时心跳] PDF共读监控运行中...', {
          活跃状态: coReadingTimer.isActive,
          PDF聚焦: coReadingTimer.isPdfFocused,
          PDF隐藏: coReadingTimer.isPdfTrulyInvisible,
          时间戳: new Date().toLocaleTimeString()
        })
      }, 5000) // 每5秒打印一次心跳日志

      return () => {
        clearInterval(logInterval)
      }
    }
  }, [coReadingTimer.isActive, coReadingTimer.isPdfFocused, coReadingTimer.isPdfTrulyInvisible])

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
        console.log('已退出共读模式')
      } catch (error) {
        console.error('退出共读模式失败:', error)
      }
    }
  }



  // 处理外部传入的会话数据更新
  useEffect(() => {
    if (externalCurrentSession && externalCurrentSession.id === parseInt(sessionId || '0')) {
      console.log('📥 [DEBUG] 接收到外部会话更新, 更新内部状态:', externalCurrentSession)
      console.log('📥 [DEBUG] 会话详细信息:', {
        id: externalCurrentSession.id,
        scenario_id: externalCurrentSession.scenario_id,
        metadata: externalCurrentSession.metadata,
        'metadata.pdf_path': externalCurrentSession.metadata?.pdf_path,
        'metadata全部内容': JSON.stringify(externalCurrentSession.metadata, null, 2)
      })
      setCurrentSession(externalCurrentSession)
    }
  }, [externalCurrentSession, sessionId])

  // 处理外部会话更新（比如从FileList组件进入共读模式）
  useEffect(() => {
    console.log('🔗 [DEBUG] 会话更新回调已准备就绪, 当前会话:', currentSession?.id)
  }, [onSessionUpdate, currentSession?.id])

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
        console.log("✅ 聊天记录加载完成，消息数量:", convertedMessages.length)
        
        // 🎯 加载新会话后自动滚动到底部
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
  }, [sessionId, setMessages])

  // 根据官方文档，需要手动管理输入状态
  const handleFormSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()

    if ((!input.trim() && !selectedImage) || status !== "ready") return

    const userMessage = input.trim()

    // 构建消息内容，支持文本和图片
    const messageContent: any = {
      text: userMessage || "Please analyze this image", // 如果只有图片没有文本，提供默认文本
    }

    // 如果有选中的图片，添加到消息中
    if (selectedImage) {
      messageContent.files = [{
        type: 'file',
        filename: selectedImage.split('/').pop() || 'image',
        mediaType: 'image/' + (selectedImage.split('.').pop()?.toLowerCase() || 'png'),
        url: `file://${selectedImage}`, // 使用file://协议的本地文件路径
      }]
    }

    // 检查是否需要创建会话（延迟创建逻辑）
    let currentSessionId = effectiveSessionId
    if (!effectiveSessionId && onCreateSessionFromMessage) {
      onCreateSessionFromMessage(userMessage || "图片分析")
        .then((newSession) => {
          currentSessionId = String(newSession.id)
          setEffectiveSessionId(currentSessionId)
          console.log(
            "[AiSdkChat] Created new session:",
            newSession.id,
            "Name:",
            newSession.name
          )

          // 创建会话后发送消息
          sendMessage(
            messageContent,
            {
              body: {
                session_id: currentSessionId
                  ? Number(currentSessionId)
                  : undefined,
              },
            }
          )
        })
        .catch((error) => {
          console.error("[AiSdkChat] Failed to create session:", error)
          // 如果会话创建失败，继续使用无会话ID的方式发送消息
          sendMessage(messageContent)
        })
    } else {
      // 直接发送消息
      sendMessage(
        messageContent,
        {
          body: {
            session_id: currentSessionId ? Number(currentSessionId) : undefined,
          },
        }
      )
    }

    // 清空输入框和选中的图片
    setInput("")
    setSelectedImage(null)
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
      {/* PDF共读状态指示器 */}
      {/* {currentSession?.scenario_id && coReadingTimer.isActive && (
        <div className="px-3 py-2 bg-blue-50 border-b border-blue-200 text-blue-800 text-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span>📖 PDF共读模式已激活</span>
              <span className="text-xs">
                PDF可见: {coReadingTimer.isPdfFocused === null ? "检测中..." : coReadingTimer.isPdfFocused ? "✅" : "❌"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {!coReadingTimer.isPdfFocused && (
                <button
                  onClick={handleContinueReading}
                  className="text-xs px-2 py-1 bg-blue-100 hover:bg-blue-200 text-blue-700 rounded border border-blue-300 transition-colors"
                  title="恢复PDF窗口"
                >
                  恢复PDF
                </button>
              )}
              <button
                onClick={handleExitCoReading}
                className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded border border-gray-300 transition-colors"
                title="退出共读模式"
              >
                退出
              </button>
            </div>
          </div>
        </div>
      )} */}

      {/* PDF暂停状态Widget */}
      {shouldShowPauseWidget && currentSession && (
        <CoReadingPauseWidget
          session={currentSession}
          onContinueReading={handleContinueReading}
          onExitCoReading={handleExitCoReading}
        />
      )}
      <Conversation>
        <ConversationContent className="p-1">
          <ScrollArea className="flex-1 pr-4 rounded-md h-[calc(100vh-176px)]">
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
              {status === "streaming" && messages.length > 0 && messages[messages.length - 1]?.role === "user" && (
                <Message from="assistant">
                  <MessageContent>
                    <div className="pl-2">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <div className="flex space-x-1">
                          <div className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                          <div className="w-2 h-2 bg-current rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                          <div className="w-2 h-2 bg-current rounded-full animate-bounce"></div>
                        </div>
                        <span className="text-sm">AI is thinking...</span>
                      </div>
                    </div>
                  </MessageContent>
                  <MessageAvatar 
                    src="/bot.png"
                    name="Assistant"
                    className="size-6"
                  />
                </Message>
              )}
              </>
            )}
          </ScrollArea>
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* 错误状态显示 */}
      {error && (
        <div className="p-4 bg-red-50 border-t border-red-200">
          <div className="text-red-800">Sorry, an error occurred. Please try again later.</div>
        </div>
      )}

      {/* 输入区域 - 使用AI Elements */}
      <div className="p-1 relative">
        {/* 图片预览区域 - 浮动在输入框上方 */}
        {selectedImage && (
          <div className="absolute bottom-full left-2 w-[300px] mb-2 p-2 bg-muted/50 backdrop-blur-sm rounded-lg border shadow-lg z-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">选中的图片:</span>
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

        {/* PDF共读状态指示器 - 浮动在输入框上方 */}
        {currentSession?.scenario_id && currentSession?.metadata?.pdf_path && (
          <div className="absolute bottom-full right-2 w-[300px] mb-2 p-2 bg-muted/50 backdrop-blur-sm rounded-lg border shadow-lg z-10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-primary font-bold">📖 AI在与你共读PDF:</span>
              <div className="flex items-center gap-2">
                {!coReadingTimer.isPdfFocused && (
                  <Button
                    onClick={handleContinueReading}
                    variant="ghost"
                    className="size-6 items-center"
                    title="寻找PDF窗口"
                    disabled={coReadingTimer.isPdfFocused === null} // 检测中时禁用按钮
                  >
                    <SearchIcon className="inline size-4 m-1" />
                  </Button>
                )}
                <Button
                onClick={() => handleExitCoReading()}
                variant="ghost"
                className="size-6 items-center"
                title="退出共读模式"
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
          <PromptInputTextarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={selectedImage ? "描述你想了解关于这张图片的什么..." : t("AISDKCHAT.input-message")}
          />
          <PromptInputToolbar>
            <PromptInputTools>
              <PromptInputButton>
                <MicIcon size={16} />
              </PromptInputButton>
              <PromptInputButton>
                <GlobeIcon size={16} />
                <span>Search</span>
              </PromptInputButton>
            </PromptInputTools>
            <PromptInputSubmit
              className="absolute right-1 bottom-1"
              disabled={(!input.trim() && !selectedImage) || status !== "ready"}
              status={status}
            />
          </PromptInputToolbar>
        </PromptInput>
      </div>
    </div>
  )
}
