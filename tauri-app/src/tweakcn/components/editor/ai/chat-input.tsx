"use client";

import { TooltipWrapper } from "@/tweakcn/components/tooltip-wrapper";
import { Button } from "@/tweakcn/components/ui/button";
import { useAIThemeGeneration } from "@/tweakcn/hooks/use-ai-theme-generation";
import { cn } from "@/tweakcn/lib/utils";
import { useAIChatStore } from "@/tweakcn/store/ai-chat-store";
import { AIPromptData } from "@/tweakcn/types/ai";
import { ArrowUp, Loader, Plus, StopCircle } from "lucide-react";
import { useState } from "react";


export function ChatInput({
  handleThemeGeneration,
}: {
  handleThemeGeneration: (promptData: AIPromptData | null) => void;
}) {
  const [promptData] = useState<AIPromptData | null>(null);
  const { loading: aiGenerateLoading, cancelThemeGeneration } = useAIThemeGeneration();

  const { messages, clearMessages } = useAIChatStore();

  const handleGenerate = async () => {
    if (!promptData?.content) return;

    handleThemeGeneration(promptData);
  };

  return (
    <div className="@container/form relative transition-all">
      <div className="bg-background relative z-10 flex size-full min-h-[100px] flex-1 flex-col gap-2 overflow-hidden rounded-lg border shadow-xs">
        <label className="sr-only">Chat Input</label>

        <div className="flex items-center justify-between gap-2 px-2 pb-2">
          <TooltipWrapper label="Create new chat" asChild>
            <Button
              variant="outline"
              size="sm"
              onClick={clearMessages}
              disabled={aiGenerateLoading || messages.length === 0}
              className="shadow-none"
            >
              <Plus />
              <span>New chat</span>
            </Button>
          </TooltipWrapper>
          <div className="flex items-center gap-2">
            {/* TODO: Add image upload */}
            {aiGenerateLoading ? (
              <TooltipWrapper label="Cancel generation" asChild>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={cancelThemeGeneration}
                  className={cn("flex items-center gap-1 shadow-none", "@max-[350px]/form:w-8")}
                >
                  <StopCircle />
                  <span className="hidden @[350px]/form:inline-flex">Stop</span>
                </Button>
              </TooltipWrapper>
            ) : (
              <TooltipWrapper label="Send message" asChild>
                <Button
                  size="icon"
                  className="size-8 shadow-none"
                  onClick={handleGenerate}
                  disabled={!promptData?.content || aiGenerateLoading}
                >
                  {aiGenerateLoading ? <Loader className="animate-spin" /> : <ArrowUp />}
                </Button>
              </TooltipWrapper>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
