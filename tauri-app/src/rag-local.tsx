import { useState, useRef, useEffect } from 'react';
import { useBridgeEvents } from '@/hooks/useBridgeEvents';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Clock, FileText, Zap, AlertCircle, Search, Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface RagSource {
  file_path: string;
  similarity_score: number;
  content_preview: string;
  chunk_id: string;
  metadata?: Record<string, any>;
}

// 扩展事件类型以支持更多场景
interface LogEvent {
  id: string;
  timestamp: number;
  type: 'rag-retrieval' | 'rag-progress' | 'rag-error' | 'api-log' | 'api-error' | 'model-download';
  query?: string;
  sources?: RagSource[];
  sources_count?: number;
  message?: string;
  stage?: string;
  error_message?: string;
  progress?: number; // 用于模型下载进度
}

interface RagLocalProps {
  mode?: 'full' | 'startup-only' | 'rag-only'; // 显示模式
  showHeader?: boolean; // 是否显示标题栏
  title?: string; // 自定义标题
  subtitle?: string; // 自定义副标题
}

export function RagLocal({ 
  mode = 'full',
  showHeader = true,
  title,
  subtitle
}: RagLocalProps = {}) {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [isAutoScroll, setIsAutoScroll] = useState(true);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const scrollViewportRef = useRef<HTMLDivElement>(null);
  const { t } = useTranslation();

  // 监听所有相关的桥接事件
  useBridgeEvents({
    // RAG 相关事件
    'rag-retrieval-result': (payload: any) => {
      const newEvent: LogEvent = {
        id: `rag-${Date.now()}-${Math.random()}`,
        timestamp: payload.timestamp || Date.now(),
        type: 'rag-retrieval',
        query: payload.query,
        sources: payload.sources || [],
        sources_count: payload.sources_count || 0
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]); // 保持最近20条记录
      // console.log('RagLocal: 收到RAG检索结果', newEvent);
    },
    'rag-progress': (payload: any) => {
      const newEvent: LogEvent = {
        id: `rag-progress-${Date.now()}-${Math.random()}`,
        timestamp: payload.timestamp || Date.now(),
        type: 'rag-progress',
        query: payload.query,
        stage: payload.stage,
        message: payload.message
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]);
      // console.log('RagLocal: 收到RAG进度', newEvent);
    },
    'rag-error': (payload: any) => {
      const newEvent: LogEvent = {
        id: `rag-error-${Date.now()}-${Math.random()}`,
        timestamp: payload.timestamp || Date.now(),
        type: 'rag-error',
        query: payload.query,
        stage: payload.stage,
        error_message: payload.error_message
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]);
      // console.log('RagLocal: 收到RAG错误', newEvent);
    },
    // API 日志事件（用于 Splash 启动日志）
    'api-log': (payload: any) => {
      const logMessage = typeof payload === 'string' ? payload : payload.message || '';
      const newEvent: LogEvent = {
        id: `api-log-${Date.now()}-${Math.random()}`,
        timestamp: Date.now(),
        type: 'api-log',
        message: logMessage.trim()
      };
      
      // console.log('RagLocal: 收到API日志', newEvent);
      setEvents(prev => [...prev.slice(-49), newEvent]); // API日志保留50条
    },
    'api-error': (payload: any) => {
      const errorMessage = typeof payload === 'string' ? payload : payload.error || '';
      const newEvent: LogEvent = {
        id: `api-error-${Date.now()}-${Math.random()}`,
        timestamp: Date.now(),
        type: 'api-error',
        error_message: errorMessage.trim()
      };
      
      // console.log('RagLocal: 收到API错误', newEvent);
      setEvents(prev => [...prev.slice(-49), newEvent]); // API日志保留50条
    },
    // 模型下载进度事件
    'model-download-progress': (payload: any) => {
      const newEvent: LogEvent = {
        id: `model-download-${Date.now()}-${Math.random()}`,
        timestamp: Date.now(),
        type: 'model-download',
        progress: payload.percentage || payload.progress || 0, // 后端发送的是 percentage 字段
        message: payload.message
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]);
    }
  }, { showToasts: false, logEvents: false });

  // 根据 mode 过滤事件
  const filteredEvents = mode === 'startup-only'
    ? events.filter(e => ['api-log', 'api-error', 'model-download'].includes(e.type))
    : mode === 'rag-only'
    ? events.filter(e => e.type.startsWith('rag-'))
    : events; // 'full' 模式显示所有事件

  // 自动滚动到底部
  useEffect(() => {
    if (isAutoScroll && scrollViewportRef.current) {
      scrollViewportRef.current.scrollTop = scrollViewportRef.current.scrollHeight;
    }
  }, [events, isAutoScroll]);

  // 监听滚动事件，判断是否手动滚动
  const handleScroll = () => {
    if (scrollViewportRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollViewportRef.current;
      const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10;
      setIsAutoScroll(isAtBottom);
    }
  };

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'rag-retrieval':
        return <Search className="w-3 h-3" />;
      case 'rag-progress':
        return <Zap className="w-3 h-3" />;
      case 'rag-error':
      case 'api-error':
        return <AlertCircle className="w-3 h-3" />;
      case 'api-log':
        return <FileText className="w-3 h-3" />;
      case 'model-download':
        return <Download className="w-3 h-3" />;
      default:
        return <FileText className="w-3 h-3" />;
    }
  };

  const getEventColor = (type: string) => {
    switch (type) {
      case 'rag-retrieval':
        return 'bg-green-50 border-green-200 text-green-800';
      case 'rag-progress':
      case 'model-download':
        return 'bg-blue-50 border-blue-200 text-blue-800';
      case 'rag-error':
      case 'api-error':
        return 'bg-red-50 border-red-200 text-red-800';
      case 'api-log':
        return 'bg-gray-50 border-gray-200 text-gray-800';
      default:
        return 'bg-gray-50 border-gray-200 text-gray-800';
    }
  };

  const getEventLabel = (type: string) => {
    switch (type) {
      case 'rag-retrieval':
        return '检索完成';
      case 'rag-progress':
        return '处理中';
      case 'rag-error':
        return 'RAG错误';
      case 'api-log':
        return 'API日志';
      case 'api-error':
        return 'API错误';
      case 'model-download':
        return '模型下载';
      default:
        return '事件';
    }
  };

  // 确定使用的标题
  const displayTitle = title || t('RAGLOCAL.file-observation-window');
  const displaySubtitle = subtitle || t('RAGLOCAL.rag-retrieval-monitoring');

  return (
    <div className="flex flex-col h-full bg-accent/10">
      {showHeader && (
        <div className="border-b p-1 bg-gray-50/50">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-gray-900">{displayTitle}</p>
              <p className="text-xs text-gray-500">{displaySubtitle}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                {filteredEvents.length} {mode === 'startup-only' ? '条日志' : t('RAGLOCAL.x-tensor-records')}
              </Badge>
              {!isAutoScroll && (
                <Badge 
                  variant="secondary" 
                  className="text-xs cursor-pointer"
                  onClick={() => setIsAutoScroll(true)}
                >
                  返回底部
                </Badge>
              )}
            </div>
          </div>
        </div>
      )}
      
      <ScrollArea 
        className="flex-1 h-[calc(100%-100px)]" 
        ref={scrollAreaRef}
      >
        <div 
          className="p-3 space-y-3"
          ref={scrollViewportRef}
          onScroll={handleScroll}
        >
          {filteredEvents.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">{t('RAGLOCAL.waiting-rag-retrieval')}</p>
              <p className="text-xs">{t('RAGLOCAL.waiting-rag-retrieval-details')}</p>
            </div>
          ) : (
            filteredEvents.map((event, index) => (
              <div key={event.id}>
                <div className={`p-3 rounded-lg border ${getEventColor(event.type)}`}>
                  <div className="flex items-start gap-2">
                    <div className="flex-shrink-0 mt-0.5">
                      {getEventIcon(event.type)}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium">
                          {getEventLabel(event.type)}
                        </span>
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <Clock className="w-3 h-3" />
                          {formatTime(event.timestamp)}
                        </div>
                      </div>
                      
                      {/* Query 显示（RAG事件） */}
                      {event.query && (
                        <div className="mb-2">
                          <p className="text-xs text-gray-600 mb-1">Query:</p>
                          <p className="text-sm font-mono bg-white/60 px-2 py-1 rounded text-gray-800 border">
                            {event.query}
                          </p>
                        </div>
                      )}
                      
                      {/* RAG 检索结果 */}
                      {event.type === 'rag-retrieval' && event.sources && (
                        <div className="space-y-2">
                          <p className="text-xs text-gray-600">
                            {event.sources_count || event.sources.length} related chunk found:
                          </p>
                          {event.sources.slice(0, 3).map((source: RagSource, idx: number) => (
                            <div key={idx} className="bg-white/80 p-2 rounded border">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-medium text-gray-700 truncate">
                                  {source.file_path.split('/').pop()}
                                </span>
                                <Badge variant="outline" className="text-xs">
                                  {(source.similarity_score * 100).toFixed(1)}%
                                </Badge>
                              </div>
                              <p className="text-xs text-gray-600 line-clamp-2">
                                {source.content_preview}
                              </p>
                            </div>
                          ))}
                          {event.sources.length > 3 && (
                            <p className="text-xs text-gray-500 italic">
                              {event.sources.length - 3} more...
                            </p>
                          )}
                        </div>
                      )}
                      
                      {/* RAG 进度信息 */}
                      {event.type === 'rag-progress' && (
                        <div>
                          {event.stage && (
                            <Badge variant="outline" className="text-xs mb-1">
                              {event.stage}
                            </Badge>
                          )}
                          {event.message && (
                            <p className="text-xs text-gray-600">{event.message}</p>
                          )}
                        </div>
                      )}
                      
                      {/* 错误信息（RAG/API） */}
                      {(event.type === 'rag-error' || event.type === 'api-error') && (
                        <div className="text-xs text-red-700">
                          {event.stage && <span className="font-medium">[{event.stage}] </span>}
                          {event.error_message}
                        </div>
                      )}
                      
                      {/* API 日志 */}
                      {event.type === 'api-log' && event.message && (
                        <p className="text-xs text-gray-700 font-mono whitespace-pre-wrap">
                          {event.message}
                        </p>
                      )}
                      
                      {/* 模型下载进度 */}
                      {event.type === 'model-download' && (
                        <div>
                          {event.progress !== undefined && (
                            <div className="mb-1">
                              <div className="flex justify-between text-xs text-gray-600 mb-1">
                                <span>下载进度</span>
                                <span>{event.progress}%</span>
                              </div>
                              <div className="w-full bg-gray-200 rounded-full h-1.5">
                                <div 
                                  className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                                  style={{ width: `${event.progress}%` }}
                                />
                              </div>
                            </div>
                          )}
                          {event.message && (
                            <p className="text-xs text-gray-600">{event.message}</p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                
                {index < filteredEvents.length - 1 && (
                  <Separator className="my-2" />
                )}
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}