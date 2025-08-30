import { useState, useRef, useEffect } from 'react';
import { useBridgeEvents } from '@/hooks/useBridgeEvents';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Clock, FileText, Zap, AlertCircle, Search } from 'lucide-react';

interface RagSource {
  file_path: string;
  similarity_score: number;
  content_preview: string;
  chunk_id: string;
  metadata?: Record<string, any>;
}

interface RagEvent {
  id: string;
  timestamp: number;
  type: 'retrieval' | 'progress' | 'error';
  query?: string;
  sources?: RagSource[];
  sources_count?: number;
  message?: string;
  stage?: string;
  error_message?: string;
}

export function RagLocal() {
  const [events, setEvents] = useState<RagEvent[]>([]);
  const [isAutoScroll, setIsAutoScroll] = useState(true);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const scrollViewportRef = useRef<HTMLDivElement>(null);

  // 监听RAG相关的桥接事件
  useBridgeEvents({
    'rag-retrieval-result': (payload: any) => {
      const newEvent: RagEvent = {
        id: `rag-${Date.now()}-${Math.random()}`,
        timestamp: payload.timestamp || Date.now(),
        type: 'retrieval',
        query: payload.query,
        sources: payload.sources || [],
        sources_count: payload.sources_count || 0
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]); // 保持最近20条记录
      console.log('RagLocal: 收到RAG检索结果', newEvent);
    },
    'rag-progress': (payload: any) => {
      const newEvent: RagEvent = {
        id: `rag-progress-${Date.now()}-${Math.random()}`,
        timestamp: payload.timestamp || Date.now(),
        type: 'progress',
        query: payload.query,
        stage: payload.stage,
        message: payload.message
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]);
      console.log('RagLocal: 收到RAG进度', newEvent);
    },
    'rag-error': (payload: any) => {
      const newEvent: RagEvent = {
        id: `rag-error-${Date.now()}-${Math.random()}`,
        timestamp: payload.timestamp || Date.now(),
        type: 'error',
        query: payload.query,
        stage: payload.stage,
        error_message: payload.error_message
      };
      
      setEvents(prev => [...prev.slice(-19), newEvent]);
      console.log('RagLocal: 收到RAG错误', newEvent);
    }
  }, { showToasts: false, logEvents: false });

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
      case 'retrieval':
        return <Search className="w-3 h-3" />;
      case 'progress':
        return <Zap className="w-3 h-3" />;
      case 'error':
        return <AlertCircle className="w-3 h-3" />;
      default:
        return <FileText className="w-3 h-3" />;
    }
  };

  const getEventColor = (type: string) => {
    switch (type) {
      case 'retrieval':
        return 'bg-green-50 border-green-200 text-green-800';
      case 'progress':
        return 'bg-blue-50 border-blue-200 text-blue-800';
      case 'error':
        return 'bg-red-50 border-red-200 text-red-800';
      default:
        return 'bg-gray-50 border-gray-200 text-gray-800';
    }
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="border-b p-3 bg-gray-50/50">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-gray-900">知识观察窗</p>
            <p className="text-xs text-gray-500">RAG检索过程与结果实时监控</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {events.length} 条记录
            </Badge>
            {!isAutoScroll && (
              <Badge 
                variant="secondary" 
                className="text-xs cursor-pointer"
                onClick={() => setIsAutoScroll(true)}
              >
                点击回到底部
              </Badge>
            )}
          </div>
        </div>
      </div>
      
      <ScrollArea 
        className="flex-1 h-[calc(100%-72px)]" 
        ref={scrollAreaRef}
      >
        <div 
          className="p-3 space-y-3"
          ref={scrollViewportRef}
          onScroll={handleScroll}
        >
          {events.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">等待RAG检索活动...</p>
              <p className="text-xs">当您发送消息时，相关知识片段将在这里显示</p>
            </div>
          ) : (
            events.map((event, index) => (
              <div key={event.id}>
                <div className={`p-3 rounded-lg border ${getEventColor(event.type)}`}>
                  <div className="flex items-start gap-2">
                    <div className="flex-shrink-0 mt-0.5">
                      {getEventIcon(event.type)}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium">
                          {event.type === 'retrieval' && '检索完成'}
                          {event.type === 'progress' && '处理中'}
                          {event.type === 'error' && '错误'}
                        </span>
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <Clock className="w-3 h-3" />
                          {formatTime(event.timestamp)}
                        </div>
                      </div>
                      
                      {event.query && (
                        <div className="mb-2">
                          <p className="text-xs text-gray-600 mb-1">查询:</p>
                          <p className="text-sm font-mono bg-white/60 px-2 py-1 rounded text-gray-800 border">
                            {event.query}
                          </p>
                        </div>
                      )}
                      
                      {event.type === 'retrieval' && event.sources && (
                        <div className="space-y-2">
                          <p className="text-xs text-gray-600">
                            找到 {event.sources_count || event.sources.length} 个相关片段:
                          </p>
                          {event.sources.slice(0, 3).map((source, idx) => (
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
                              还有 {event.sources.length - 3} 个片段...
                            </p>
                          )}
                        </div>
                      )}
                      
                      {event.type === 'progress' && (
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
                      
                      {event.type === 'error' && (
                        <div className="text-xs text-red-700">
                          {event.stage && <span className="font-medium">[{event.stage}] </span>}
                          {event.error_message}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                
                {index < events.length - 1 && (
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