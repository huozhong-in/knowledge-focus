"use client"

import * as React from "react"
import { useEffect, useRef, useState, useCallback } from "react"
import { cn } from "@/lib/utils"

// 定义组件的Props类型
export type ChatContainerRootProps = {
  children: React.ReactNode
  className?: string
  stickToBottom?: boolean
} & React.HTMLAttributes<HTMLDivElement>

export type ChatContainerContentProps = {
  children: React.ReactNode
  className?: string
} & React.HTMLAttributes<HTMLDivElement>

export type ChatContainerScrollAnchorProps = {
  className?: string
} & React.HTMLAttributes<HTMLDivElement>

// 实现一个类似StickToBottom的容器组件
function ChatContainerRoot({
  children,
  className,
  stickToBottom = true,
  ...props
}: ChatContainerRootProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true)
  const prevScrollHeightRef = useRef<number>(0)
  
  // 处理滚动事件，判断用户是否手动滚动远离底部
  const handleScroll = useCallback(() => {
    if (!containerRef.current || !stickToBottom) return
    
    const { scrollHeight, scrollTop, clientHeight } = containerRef.current
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    
    // 如果用户滚动超过100px，停止自动滚动
    setShouldAutoScroll(distanceFromBottom < 100)
  }, [stickToBottom])
  
  // 初始化时及内容变化时滚动到底部
  useEffect(() => {
    const container = containerRef.current
    if (!container || !stickToBottom) return
    
    const observer = new MutationObserver(() => {
      // 只有当用户未手动滚动时才自动滚动
      if (shouldAutoScroll) {
        const currentScrollHeight = container.scrollHeight
        
        // 平滑滚动至底部
        if (currentScrollHeight !== prevScrollHeightRef.current) {
          container.scrollTo({ 
            top: container.scrollHeight, 
            behavior: "smooth" 
          })
          prevScrollHeightRef.current = currentScrollHeight
        }
      }
    })
    
    observer.observe(container, { 
      childList: true, 
      subtree: true, 
      characterData: true 
    })
    
    // 初始滚动到底部（立即滚动，不使用动画）
    container.scrollTo({ 
      top: container.scrollHeight, 
      behavior: "instant" as ScrollBehavior 
    })
    
    container.addEventListener('scroll', handleScroll)
    
    return () => {
      observer.disconnect()
      container.removeEventListener('scroll', handleScroll)
    }
  }, [stickToBottom, shouldAutoScroll, handleScroll])

  return (
    <div
      ref={containerRef}
      className={cn("flex overflow-y-auto", className)}
      role="log"
      {...props}
    >
      {children}
    </div>
  )
}

function ChatContainerContent({
  children,
  className,
  ...props
}: ChatContainerContentProps) {
  return (
    <div
      className={cn("flex w-full flex-col", className)}
      {...props}
    >
      {children}
    </div>
  )
}

function ChatContainerScrollAnchor({
  className,
  ...props
}: ChatContainerScrollAnchorProps) {
  return (
    <div
      className={cn("h-px w-full shrink-0 scroll-mt-4", className)}
      aria-hidden="true"
      {...props}
    />
  )
}

export { 
  ChatContainerRoot, 
  ChatContainerContent, 
  ChatContainerScrollAnchor 
}
