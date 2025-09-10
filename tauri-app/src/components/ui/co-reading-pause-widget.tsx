import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertCircle, BookOpen, FileText, X } from 'lucide-react'
import { ChatSession } from '@/lib/chat-session-api'

interface CoReadingPauseWidgetProps {
  session: ChatSession
  onContinueReading?: () => void
  onExitCoReading?: () => void
  className?: string
}

/**
 * PDF共读暂停状态Widget
 * 
 * 当PDF窗口不可见时显示此组件，提供用户操作选项：
 * - 继续阅读：智能处理（检测不到窗口→打开，最小化→激活）
 * - 退出共读模式：调用后端接口+清理前端状态
 */
export function CoReadingPauseWidget({
  session,
  onContinueReading,
  onExitCoReading,
  className = ''
}: CoReadingPauseWidgetProps) {
  const pdfPath = session.metadata?.pdf_path
  const pdfFileName = pdfPath ? pdfPath.split('/').pop() : '未知文件'

  return (
    <div className={`fixed bottom-20 left-4 right-4 z-50 ${className}`}>
      <Card className="border-orange-200 bg-orange-50/95 shadow-xl max-w-lg mx-auto backdrop-blur-md border-2">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-orange-600" />
            <CardTitle className="text-orange-800">PDF阅读已暂停</CardTitle>
          </div>
          <CardDescription className="text-orange-700">
            PDF窗口当前不可见或已最小化，共读功能已暂停
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* PDF文件信息 */}
          <div className="flex items-center gap-2 text-sm text-orange-700 bg-orange-100 rounded p-2">
            <FileText className="h-4 w-4" />
            <span className="truncate" title={pdfPath}>
              {pdfFileName}
            </span>
          </div>

          {/* 操作按钮组 */}
          <div className="flex flex-col sm:flex-row gap-3">
            <Button 
              onClick={onContinueReading}
              className="flex-1 bg-blue-600 hover:bg-blue-700"
              size="sm"
            >
              <BookOpen className="h-4 w-4 mr-2" />
              继续阅读
            </Button>
            
            <Button 
              onClick={onExitCoReading}
              variant="outline"
              className="flex-1 border-orange-300 text-orange-700 hover:bg-orange-100"
              size="sm"
            >
              <X className="h-4 w-4 mr-1" />
              退出共读模式
            </Button>
          </div>

          {/* 提示信息 */}
          <p className="text-xs text-orange-600 text-center">
            💡 你也可以手动打开PDF窗口，系统会自动检测并恢复共读模式
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export default CoReadingPauseWidget
