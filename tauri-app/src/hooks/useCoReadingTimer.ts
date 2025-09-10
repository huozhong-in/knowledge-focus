import { useEffect, useRef, useCallback, useState } from 'react'
import { ChatSession } from '@/lib/chat-session-api'
import { isPdfReaderFocused } from '@/lib/pdfCoReadingTools'

interface WindowStatus {
  exists: boolean
  isFrontmost: boolean
  isOccluded: boolean
  isMiniaturized: boolean
  message: string
}

interface UseCoReadingTimerProps {
  session: ChatSession | null
  onPdfWindowLost?: () => void
  onPdfWindowRegained?: () => void
  checkInterval?: number // 检查间隔，默认 2000ms
}

interface CoReadingTimerState {
  isActive: boolean
  isPdfFocused: boolean | null
  isPdfTrulyInvisible: boolean | null // 真正不可见（不存在或最小化）
  windowStatus: WindowStatus | null
  startTimer: () => void
  stopTimer: () => void
  checkNow: () => Promise<void>
  restorePdfWindow: () => Promise<boolean> // 手动恢复PDF窗口
}

/**
 * PDF共读模式定时器hook
 * 
 * 功能：
 * - 监控会话的scenario_id状态
 * - 在共读模式下定时检查PDF窗口焦点状态
 * - 当PDF窗口失去焦点时触发回调
 * - 自动清理定时器
 */
export function useCoReadingTimer({
  session,
  onPdfWindowLost,
  onPdfWindowRegained,
  checkInterval = 2000
}: UseCoReadingTimerProps): CoReadingTimerState {
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastFocusStateRef = useRef<boolean | null>(null)
  
  // 使用 useState 来存储需要触发重新渲染的状态
  const [isActive, setIsActive] = useState<boolean>(false)
  const [isPdfFocused, setIsPdfFocused] = useState<boolean | null>(null)
  const [isPdfTrulyInvisible, setIsPdfTrulyInvisible] = useState<boolean | null>(null)
  const [windowStatus, setWindowStatus] = useState<WindowStatus | null>(null)

  // 检查PDF窗口焦点状态
  const checkPdfFocus = useCallback(async (): Promise<boolean | null> => {
    try {
      // 获取PDF路径
      const pdfPath = session?.metadata?.pdf_path
      if (!pdfPath) {
        console.warn('⚠️ 缺少PDF路径，无法检查窗口状态')
        return null
      }

    //   console.log('🔍 [定时器检查] 检查PDF窗口状态:', pdfPath.split('/').pop())
      
      const currentWindowStatus = await isPdfReaderFocused(pdfPath)
      setWindowStatus(currentWindowStatus)
      
    //   console.log('📊 [定时器检查] 窗口状态详情:', currentWindowStatus)
      
      // 判断窗口是否对用户可见
      // 真正不可见：不存在或被最小化 (应该显示Widget)
      const isTrulyInvisible = !currentWindowStatus.exists || currentWindowStatus.isMiniaturized
      
      // 完全可见：存在且未最小化且在前台且无遮挡
      const isFocused = currentWindowStatus.exists && !currentWindowStatus.isMiniaturized && currentWindowStatus.isFrontmost && !currentWindowStatus.isOccluded
      
    //   console.log('📈 [定时器检查] 计算结果:', {
    //     exists: currentWindowStatus.exists,
    //     miniaturized: currentWindowStatus.isMiniaturized,
    //     frontmost: currentWindowStatus.isFrontmost,
    //     occluded: currentWindowStatus.isOccluded,
    //     isFocused,
    //     isTrulyInvisible,
    //     lastFocusState: lastFocusStateRef.current
    //   })
      
      // 更新状态
      setIsPdfFocused(isFocused)
      setIsPdfTrulyInvisible(isTrulyInvisible)
      
      // 状态变化时触发回调
      if (lastFocusStateRef.current !== null && lastFocusStateRef.current !== isFocused) {
        if (!isFocused && onPdfWindowLost) {
        //   console.log('🔴 PDF窗口失去焦点，触发回调', currentWindowStatus)
          onPdfWindowLost()
        } else if (isFocused && onPdfWindowRegained) {
        //   console.log('🟢 PDF窗口重新获得焦点，触发回调', currentWindowStatus)
          onPdfWindowRegained()
        }
      }
      
      lastFocusStateRef.current = isFocused
      return isFocused
    } catch (error) {
      console.error('❌ 检查PDF窗口焦点状态失败:', error)
      return null
    }
  }, [session?.metadata?.pdf_path, onPdfWindowLost, onPdfWindowRegained])

  // 启动定时器
  const startTimer = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }
    
    setIsActive(true)
    // console.log('🚀 启动PDF焦点检查定时器，间隔:', checkInterval + 'ms')
    
    intervalRef.current = setInterval(() => {
      checkPdfFocus()
    }, checkInterval)
    
    // 立即执行一次检查
    checkPdfFocus()
  }, [checkPdfFocus, checkInterval])

  // 停止定时器
  const stopTimer = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setIsActive(false)
    setIsPdfFocused(null)
    setIsPdfTrulyInvisible(null)
    setWindowStatus(null)
    lastFocusStateRef.current = null
    // console.log('🛑 停止PDF焦点检查定时器')
  }, [])

  // 立即检查一次
  const checkNow = useCallback(async () => {
    await checkPdfFocus()
  }, [checkPdfFocus])

  // 手动恢复PDF窗口
  const restorePdfWindow = useCallback(async () => {
    if (!session?.metadata?.pdf_path) {
      console.warn('⚠️ 无法恢复PDF窗口：缺少PDF路径')
      return false
    }

    const pdfPath = session.metadata.pdf_path
    // console.log('🔄 手动恢复PDF窗口:', pdfPath)
    
    try {
      const { isPdfReaderFocused } = await import('@/lib/pdfCoReadingTools')
      const { reactivatePdfWindow } = await import('@/lib/chat-session-api')
      
      const windowStatus = await isPdfReaderFocused(pdfPath)
      
      if (!windowStatus.exists) {
        // console.log('📂 PDF窗口不存在，尝试重新打开PDF文件...')
        const { handlePdfReading } = await import('@/lib/pdfCoReadingTools')
        const result = await handlePdfReading({ pdfPath })
        return !!result
      } else {
        // console.log('🔄 PDF窗口存在，尝试激活...')
        const success = await reactivatePdfWindow(pdfPath)
        return success
      }
    } catch (error) {
      console.error('❌ 恢复PDF窗口时发生错误:', error)
      return false
    }
  }, [session?.metadata?.pdf_path])

  // 监控会话状态变化
  useEffect(() => {
    // console.log('⏰ [DEBUG] useCoReadingTimer状态检查:', {
    //   hasSession: !!session,
    //   sessionId: session?.id,
    //   scenarioId: session?.scenario_id,
    //   pdfPath: session?.metadata?.pdf_path,
    //   currentlyActive: isActive
    // })

    // 检查数据完整性
    if (!session) {
      // 会话数据不完整，停止定时器
      if (isActive) {
        // console.log('❌ 会话数据缺失，停止定时器')
        stopTimer()
      }
      return
    }

    // 检查是否为共读模式
    const isCoReadingMode = session.scenario_id !== null && session.scenario_id !== undefined

    // console.log('🔄 [DEBUG] 共读模式检查:', {
    //   scenarioId: session.scenario_id,
    //   isCoReadingMode,
    //   currentlyActive: isActive
    // })

    if (isCoReadingMode) {
      // 检查是否有PDF路径
      const pdfPath = session.metadata?.pdf_path
      if (!pdfPath) {
        console.warn('⚠️ 共读模式下缺少PDF路径，无法启动定时器')
        return
      }

    //   console.log(`✅ 会话 ${session.id} 进入共读模式，PDF路径: ${pdfPath}`)
      
      // 启动定时器（如果还未启动）
      if (!isActive) {
        // console.log('🚀 启动PDF监控定时器')
        startTimer()
        
        // 🎯 用户体验优化：不自动打开PDF，让用户通过Widget主动控制
        // 这样可以避免界面的剧烈变动，提供更好的控制感和安全感
        // console.log('� 共读模式已激活，等待用户通过界面选择是否打开PDF...')
      } else {
        // console.log('⏸️ 定时器已在运行中')
      }
    } else {
      // 非共读模式，停止定时器
      if (isActive) {
        // console.log(`🛑 会话 ${session.id} 退出共读模式，停止定时器`)
        stopTimer()
      }
    }
  }, [session, startTimer, stopTimer, isActive])

  // 清理效果
  useEffect(() => {
    return () => {
      stopTimer()
    }
  }, [stopTimer])

  return {
    isActive,
    isPdfFocused,
    isPdfTrulyInvisible,
    windowStatus,
    startTimer,
    stopTimer,
    checkNow,
    restorePdfWindow
  }
}
