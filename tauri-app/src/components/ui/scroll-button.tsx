"use client"

import { Button, buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { type VariantProps } from "class-variance-authority"
import { ChevronDown } from "lucide-react"
import { useEffect, useState } from "react"

export type ScrollButtonProps = {
  className?: string
  variant?: VariantProps<typeof buttonVariants>["variant"]
  size?: VariantProps<typeof buttonVariants>["size"]
  containerRef?: React.RefObject<HTMLElement>
} & React.ButtonHTMLAttributes<HTMLButtonElement>

function ScrollButton({
  className,
  variant = "outline",
  size = "sm",
  containerRef,
  ...props
}: ScrollButtonProps) {
  const [isAtBottom, setIsAtBottom] = useState(true)

  useEffect(() => {
    const container = containerRef?.current || document.documentElement

    const checkIfAtBottom = () => {
      if (!container) return

      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
      setIsAtBottom(distanceFromBottom < 50)
    }

    // Initial check
    checkIfAtBottom()

    // Add scroll event listener
    container.addEventListener("scroll", checkIfAtBottom)
    
    // Remove event listener on cleanup
    return () => {
      container.removeEventListener("scroll", checkIfAtBottom)
    }
  }, [containerRef])

  const scrollToBottom = () => {
    if (!containerRef?.current) {
      window.scrollTo({
        top: document.body.scrollHeight,
        behavior: "smooth"
      })
    } else {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "smooth"
      })
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      className={cn(
        "h-10 w-10 rounded-full transition-all duration-150 ease-out",
        !isAtBottom
          ? "translate-y-0 scale-100 opacity-100"
          : "pointer-events-none translate-y-4 scale-95 opacity-0",
        className
      )}
      onClick={() => scrollToBottom()}
      {...props}
    >
      <ChevronDown className="h-5 w-5" />
    </Button>
  )
}

export { ScrollButton }
