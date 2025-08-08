/**
 * 支持打字机效果的会话标题组件
 * 当会话标题是从AI生成的时候，显示打字机动画效果
 */

import { useState, useEffect } from 'react'

interface AnimatedSessionTitleProps {
  title: string
  isNewlyGenerated?: boolean
  className?: string
  onAnimationComplete?: () => void
}

export function AnimatedSessionTitle({ 
  title, 
  isNewlyGenerated = false, 
  className = "",
  onAnimationComplete 
}: AnimatedSessionTitleProps) {
  const [displayedText, setDisplayedText] = useState(isNewlyGenerated ? "" : title)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAnimating, setIsAnimating] = useState(isNewlyGenerated)

  // 初始化效果：处理isNewlyGenerated状态变化
  useEffect(() => {
    if (isNewlyGenerated) {
      setDisplayedText("")
      setCurrentIndex(0)
      setIsAnimating(true)
    } else {
      setDisplayedText(title)
      setIsAnimating(false)
    }
  }, [isNewlyGenerated, title])

  // 打字机动画效果
  useEffect(() => {
    if (!isAnimating) {
      return
    }

    const timer = setTimeout(() => {
      if (currentIndex < title.length) {
        setDisplayedText(title.substring(0, currentIndex + 1))
        setCurrentIndex(prev => prev + 1)
      } else {
        // 动画完成
        setIsAnimating(false)
        onAnimationComplete?.()
      }
    }, 80) // 每80ms显示一个字符，稍微慢一点更自然

    return () => clearTimeout(timer)
  }, [currentIndex, isAnimating, title, onAnimationComplete])

  return (
    <span className={`${className} ${isAnimating ? 'animate-pulse' : ''}`}>
      {displayedText}
      {isAnimating && (
        <span className="inline-block w-0.5 h-4 bg-current ml-0.5 animate-pulse opacity-75" />
      )}
    </span>
  )
}
