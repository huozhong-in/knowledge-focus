import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { CheckCircle, Clock, AlertCircle, RotateCcw, ExternalLink } from 'lucide-react';

// 使用useVectorizationStore中的状态结构
type VectorizationFileState = {
  status: 'idle' | 'processing' | 'completed' | 'failed'
  progress: number // 0-100
  taskId?: string
  stage?: string // parsing, chunking, vectorizing, completed, failed
  message?: string
  error?: {
    message: string
    helpLink?: string
    errorCode?: string
  }
  createdAt: number // 用于排队顺序
  lastUpdated: number
  parentChunksCount?: number
  childChunksCount?: number
}

interface VectorizationProgressProps {
  filePath: string;
  state?: VectorizationFileState;
  onRetry?: () => void;
  className?: string;
}

export function VectorizationProgress({ 
  state, 
  onRetry,
  className 
}: VectorizationProgressProps) {
  if (!state) {
    return null;
  }

  const { status, progress, stage, message, error } = state;

  // 状态图标和颜色
  const getStatusConfig = () => {
    switch (status) {
      case 'idle':
        return {
          icon: <Clock className="h-3 w-3" />,
          color: 'text-muted-foreground',
          bgColor: 'bg-muted',
          borderColor: 'border-muted'
        };
      case 'processing':
        return {
          icon: <div className="h-3 w-3 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />,
          color: 'text-blue-600',
          bgColor: 'bg-blue-50',
          borderColor: 'border-blue-200'
        };
      case 'completed':
        return {
          icon: <CheckCircle className="h-3 w-3" />,
          color: 'text-green-600',
          bgColor: 'bg-green-50',
          borderColor: 'border-green-200'
        };
      case 'failed':
        return {
          icon: <AlertCircle className="h-3 w-3" />,
          color: 'text-red-600',
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200'
        };
    }
  };

  const config = getStatusConfig();
  const progressValue = Math.max(0, Math.min(100, progress));

  // 状态文本
  const getStatusText = () => {
    switch (status) {
      case 'idle':
        return '排队中...';
      case 'processing':
        return stage ? `${stage}...` : '处理中...';
      case 'completed':
        return '向量化完成';
      case 'failed':
        return '向量化失败';
    }
  };

  return (
    <div className={`${config.bgColor} ${config.borderColor} border rounded-md p-2 transition-all duration-200 ${className}`}>
      <div className="flex items-center gap-2 mb-1">
        <div className={config.color}>
          {config.icon}
        </div>
        <span className={`text-xs font-medium ${config.color}`}>
          {getStatusText()}
        </span>
        {status === 'processing' && (
          <span className="text-xs text-muted-foreground ml-auto">
            {progressValue}%
          </span>
        )}
      </div>

      {/* 进度条 */}
      {status === 'processing' && (
        <Progress 
          value={progressValue} 
          className="h-1.5 mb-1"
        />
      )}

      {/* 成功装饰条 */}
      {status === 'completed' && (
        <div className="h-1 bg-green-500 rounded-full mb-1" />
      )}

      {/* 消息文本 */}
      {message && (
        <p className="text-xs text-muted-foreground truncate" title={message}>
          {message}
        </p>
      )}

      {/* 错误处理 */}
      {status === 'failed' && error && (
        <div className="mt-1 space-y-1">
          <p className="text-xs text-red-600 truncate" title={error.message}>
            {error.message}
          </p>
          <div className="flex gap-1">
            {onRetry && (
              <Button
                variant="outline"
                size="sm"
                onClick={onRetry}
                className="h-5 px-2 text-xs"
              >
                <RotateCcw className="h-2.5 w-2.5 mr-1" />
                重试
              </Button>
            )}
            {error.helpLink && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open(error.helpLink, '_blank')}
                className="h-5 px-2 text-xs"
              >
                <ExternalLink className="h-2.5 w-2.5 mr-1" />
                帮助
              </Button>
            )}
          </div>
        </div>
      )}

      {/* 完成状态的统计信息 */}
      {status === 'completed' && (state.parentChunksCount || state.childChunksCount) && (
        <p className="text-xs text-muted-foreground mt-1">
          已生成 {state.parentChunksCount || 0} 个父块，{state.childChunksCount || 0} 个子块
        </p>
      )}
    </div>
  );
}
