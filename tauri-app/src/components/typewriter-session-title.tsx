import { useState, useEffect } from 'react';

interface TypewriterSessionTitleProps {
  text: string;
  isAnimating: boolean;
  onAnimationComplete?: () => void;
  className?: string;
  speed?: number; // milliseconds per character
}

export function TypewriterSessionTitle({
  text,
  isAnimating,
  onAnimationComplete,
  className = "",
  speed = 80
}: TypewriterSessionTitleProps) {
  const [displayedText, setDisplayedText] = useState(isAnimating ? "" : text);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (!isAnimating) {
      setDisplayedText(text);
      return;
    }

    // Reset when starting animation
    setDisplayedText("");
    setCurrentIndex(0);
  }, [isAnimating, text]);

  useEffect(() => {
    if (!isAnimating || currentIndex >= text.length) {
      if (currentIndex >= text.length && onAnimationComplete) {
        onAnimationComplete();
      }
      return;
    }

    const timer = setTimeout(() => {
      setDisplayedText(text.substring(0, currentIndex + 1));
      setCurrentIndex(currentIndex + 1);
    }, speed);

    return () => clearTimeout(timer);
  }, [currentIndex, text, isAnimating, speed, onAnimationComplete]);

  return (
    <span className={`inline-block ${className}`}>
      {displayedText}
      {isAnimating && currentIndex < text.length && (
        <span className="animate-pulse">|</span>
      )}
    </span>
  );
}
