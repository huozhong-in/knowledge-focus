import React, { useEffect, useState, useRef } from 'react';
import { Scrollbars } from 'react-custom-scrollbars-2';

interface CustomScrollbarProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export const CustomScrollbar: React.FC<CustomScrollbarProps> = ({ 
  children, 
  className = '', 
  style = {} 
}) => {
  const [colors, setColors] = useState({
    border: '#d1d5db',
    mutedForeground: '#9ca3af',
  });
  const [needsScrolling, setNeedsScrolling] = useState(false);
  const scrollbarsRef = useRef<Scrollbars>(null);

  useEffect(() => {
    const updateColors = () => {
      const root = document.documentElement;
      const style = getComputedStyle(root);
      
      // 获取CSS变量值
      const borderValue = style.getPropertyValue('--border').trim();
      const mutedForegroundValue = style.getPropertyValue('--muted-foreground').trim();
      
      // 如果获取到CSS变量，转换为hsl颜色
      if (borderValue) {
        const borderColor = borderValue.includes('hsl') ? borderValue : `hsl(${borderValue})`;
        const mutedColor = mutedForegroundValue ? 
          (mutedForegroundValue.includes('hsl') ? mutedForegroundValue : `hsl(${mutedForegroundValue})`) : 
          borderColor;
        
        setColors({
          border: borderColor,
          mutedForeground: mutedColor,
        });
      }
    };

    // 延迟更新，确保CSS变量已经被应用
    setTimeout(updateColors, 100);
    
    // 监听主题变化
    const observer = new MutationObserver(() => {
      setTimeout(updateColors, 50);
    });
    
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'style'],
    });

    // 也监听style标签的变化
    const styleObserver = new MutationObserver(() => {
      setTimeout(updateColors, 50);
    });
    
    styleObserver.observe(document.head, {
      childList: true,
      subtree: true,
    });

    return () => {
      observer.disconnect();
      styleObserver.disconnect();
    };
  }, []);

  // 检查是否需要滚动条
  const checkScrollNeeded = () => {
    if (scrollbarsRef.current) {
      const scrollHeight = scrollbarsRef.current.getScrollHeight();
      const clientHeight = scrollbarsRef.current.getClientHeight();
      
      const needsScroll = scrollHeight > clientHeight;
      if (needsScroll !== needsScrolling) {
        setNeedsScrolling(needsScroll);
      }
    }
  };

  // 监听内容变化 - 降低检查频率
  useEffect(() => {
    const timer = setInterval(checkScrollNeeded, 200);
    return () => clearInterval(timer);
  }, [needsScrolling]);

  // 监听内容更新
  useEffect(() => {
    setTimeout(checkScrollNeeded, 50);
  }, [children]);

  // 监听容器大小变化
  useEffect(() => {
    if (!scrollbarsRef.current) return;
    
    const containerElement = scrollbarsRef.current.container;
    if (!containerElement) return;

    const resizeObserver = new ResizeObserver(() => {
      checkScrollNeeded();
    });

    resizeObserver.observe(containerElement);

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // 监听内容变化
  useEffect(() => {
    if (!scrollbarsRef.current) return;
    
    const containerElement = scrollbarsRef.current.container;
    if (!containerElement) return;

    const mutationObserver = new MutationObserver(() => {
      setTimeout(checkScrollNeeded, 50);
    });

    mutationObserver.observe(containerElement, {
      childList: true,
      subtree: true,
      attributes: true,
    });

    return () => {
      mutationObserver.disconnect();
    };
  }, []);

  return (
    <div className="custom-scrollbar-container">
      <Scrollbars
        ref={scrollbarsRef}
        style={style}
        className={className}
        onUpdate={checkScrollNeeded}
        renderThumbVertical={({ style, ...props }) => (
          <div
            {...props}
            className="custom-scrollbar-thumb"
            data-hidden={!needsScrolling}
            style={{
              ...style,
              backgroundColor: colors.border,
              borderRadius: '4px',
              cursor: 'pointer',
              minHeight: '20px',
              transition: 'all 0.2s ease',
              opacity: 0,
              display: needsScrolling ? 'block' : 'none',
            }}
            onMouseEnter={(e) => {
              if (needsScrolling) {
                e.currentTarget.style.backgroundColor = colors.mutedForeground;
              }
            }}
            onMouseLeave={(e) => {
              if (needsScrolling) {
                e.currentTarget.style.backgroundColor = colors.border;
              }
            }}
          />
        )}
        renderTrackVertical={({ style, ...props }) => (
          <div
            {...props}
            className="custom-scrollbar-track"
            data-hidden={!needsScrolling}
            style={{
              ...style,
              backgroundColor: 'transparent',
              right: '2px',
              bottom: '2px',
              top: '2px',
              borderRadius: '4px',
              width: '8px',
              display: needsScrolling ? 'block' : 'none',
            }}
          />
        )}
        renderThumbHorizontal={() => <div style={{ display: 'none' }} />}
        renderTrackHorizontal={() => <div style={{ display: 'none' }} />}
      >
        {children}
      </Scrollbars>
    </div>
  );
};
