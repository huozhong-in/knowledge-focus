import { useState, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  ChatSession,
  ChatMessage as ApiChatMessage,
  getSessionMessages,
} from "./lib/chat-session-api"
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
import { GlobeIcon, MicIcon, CopyIcon } from 'lucide-react';

interface AiSdkChatProps {
  sessionId?: string
  onCreateSessionFromMessage?: (
    firstMessageContent: string
  ) => Promise<ChatSession>
  resetTrigger?: number // 用于触发重置的数字，每次改变都会重置组件
}

/**
 * AI SDK v5集成聊天组件
 * 使用useChat和AI Elements组件实现
 */
export function AiSdkChat({
  sessionId,
  onCreateSessionFromMessage,
  resetTrigger,
}: AiSdkChatProps) {
  const [effectiveSessionId, setEffectiveSessionId] = useState<
    string | undefined
  >(sessionId)
  const [isInitializing, setIsInitializing] = useState(true)
  const [input, setInput] = useState("")

  // 使用useChat hook集成AI SDK v5 - 使用DefaultChatTransport配置API
  const { messages, sendMessage, status, error, setMessages } = useChat({
    transport: new DefaultChatTransport({
      api: "http://localhost:60315/chat/agent-stream",
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

    if (!input.trim() || status !== "ready") return

    const userMessage = input.trim()

    // 检查是否需要创建会话（延迟创建逻辑）
    let currentSessionId = effectiveSessionId
    if (!effectiveSessionId && onCreateSessionFromMessage) {
      onCreateSessionFromMessage(userMessage)
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
            { text: userMessage },
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
          sendMessage({ text: userMessage })
        })
    } else {
      // 直接发送消息
      sendMessage(
        { text: userMessage },
        {
          body: {
            session_id: currentSessionId ? Number(currentSessionId) : undefined,
          },
        }
      )
    }

    // 清空输入框
    setInput("")
  }

  if (isInitializing) {
    return (
      <div className="flex flex-col flex-auto h-full items-center justify-center">
        <div className="text-muted-foreground">加载中...</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col flex-auto h-full overflow-hidden">
      <Conversation>
        <ConversationContent className="pr-1">
          <ScrollArea className="flex-1 pr-4 rounded-md h-[calc(100vh-210px)]">
            {messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center text-muted-foreground">
                  <h3 className="text-lg font-medium mb-2">
                    欢迎使用AI数据助手！
                  </h3>
                  <p>
                    您可以在这里创建新的数据任务，我会帮您从文件中提取知识片段。
                  </p>
                </div>
              </div>
            ) : (
              messages.map((message) => (
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
              ))
            )}
          </ScrollArea>
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* 错误状态显示 */}
      {error && (
        <div className="p-4 bg-red-50 border-t border-red-200">
          <div className="text-red-800">抱歉，发生了错误。请稍后重试。</div>
        </div>
      )}

      {/* 输入区域 - 使用AI Elements */}
      <div className="border-t p-2">
        <PromptInput onSubmit={handleFormSubmit} className="relative">
          <PromptInputTextarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入消息..."
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
              disabled={!input.trim() || status !== "ready"}
              status={status}
            />
          </PromptInputToolbar>
        </PromptInput>
      </div>
    </div>
  )
}
