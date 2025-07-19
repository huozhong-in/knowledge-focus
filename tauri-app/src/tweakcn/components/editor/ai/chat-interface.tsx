"use client";

import { toast } from "@/tweakcn/components/ui/use-toast";
import { useAIThemeGeneration } from "@/tweakcn/hooks/use-ai-theme-generation";
import { usePostLoginAction } from "@/tweakcn/hooks/use-post-login-action";
import { buildPrompt } from "@/tweakcn/lib/ai/ai-theme-generator";
import { authClient } from "@/tweakcn/lib/auth-client";
import { cn } from "@/tweakcn/lib/utils";
import { useAIChatStore } from "@/tweakcn/store/ai-chat-store";
import { useAuthStore } from "@/tweakcn/store/auth-store";
import { AIPromptData } from "@/tweakcn/types/ai";
import { attachLastGeneratedThemeMention, mentionsCount } from "@/tweakcn/utils/ai/ai-prompt";
import { ChatInput } from "./chat-input";
import { ClosableSuggestedPillActions } from "./closeable-suggested-pill-actions";



export function ChatInterface() {
  const { generateTheme } = useAIThemeGeneration();
  const { messages, addUserMessage, addAssistantMessage } =
    useAIChatStore();
  const { data: session } = authClient.useSession();
  const { openAuthDialog } = useAuthStore();

  const hasMessages = messages.length > 0;

  const handleThemeGeneration = async (promptData: AIPromptData | null) => {
    if (!session) {
      openAuthDialog("signup", "AI_GENERATE_FROM_CHAT", { promptData });
      return;
    }

    if (!promptData) {
      toast({
        title: "Error",
        description: "Failed to generate theme. Please try again.",
      });
      return;
    }

    let transformedPromptData = promptData;

    if (mentionsCount(promptData) === 0) {
      transformedPromptData = attachLastGeneratedThemeMention(promptData);
    }

    addUserMessage({
      promptData: transformedPromptData,
    });

    const result = await generateTheme(buildPrompt(transformedPromptData));

    if (!result) {
      addAssistantMessage({
        content: "Failed to generate theme.",
      });
      return;
    }

    addAssistantMessage({
      content:
        result?.text ??
        (result?.theme ? "Here's the theme I generated for you." : "Failed to generate theme."),
      themeStyles: result?.theme,
    });
  };


  usePostLoginAction("AI_GENERATE_FROM_CHAT", ({ promptData }) => {
    handleThemeGeneration(promptData);
  });

  return (
    <section className="@container relative isolate z-1 mx-auto flex h-full w-full max-w-[49rem] flex-1 flex-col justify-center">
      {/* Chat form input and suggestions */}
      <div className="relative mx-auto flex w-full flex-col px-4 pb-4">
        <div className="relative isolate z-10 w-full">
          <div
            className={cn(
              "transition-all ease-out",
              hasMessages ? "scale-100 opacity-100" : "h-0 scale-80 opacity-0"
            )}
          >
            <ClosableSuggestedPillActions handleThemeGeneration={handleThemeGeneration} />
          </div>
          <ChatInput handleThemeGeneration={handleThemeGeneration} />
        </div>
      </div>
    </section>
  );
}
