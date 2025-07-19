"use client";

import { useTheme } from "@/tweakcn/components/theme-provider";
import { Button } from "@/components/ui/button";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Tabs, TabsList } from "@/components/ui/tabs";
import { TabsContent as TabsContentPrimitive } from "@radix-ui/react-tabs";
import { useFullscreen } from "@/tweakcn/hooks/use-fullscreen";
import { cn } from "@/tweakcn/lib/utils";
import { ThemeEditorPreviewProps } from "@/tweakcn/types/theme";
import { Maximize, Minimize, Moon, Sun, Inspect } from "lucide-react";
import React, { useState } from "react";
import { HorizontalScrollArea } from "../horizontal-scroll-area";
import { TooltipWrapper } from "../tooltip-wrapper";
import ColorPreview from "./theme-preview/color-preview";
import ExamplesPreviewContainer from "./theme-preview/examples-preview-container";
import TabsTriggerPill from "./theme-preview/tabs-trigger-pill";
import { useThemeInspector } from "@/tweakcn/hooks/use-theme-inspector";
import InspectorOverlay from "./inspector-overlay";

const ThemePreviewPanel = ({ styles, currentMode }: ThemeEditorPreviewProps) => {
  const { isFullscreen, toggleFullscreen } = useFullscreen();
  const { theme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = useState("preview");

  const {
    rootRef,
    inspector,
    inspectorEnabled,
    handleMouseMove,
    handleMouseLeave,
    toggleInspector,
  } = useThemeInspector();

  if (!styles || !styles[currentMode]) {
    return null;
  }

  const handleThemeToggle = (event: React.MouseEvent<HTMLButtonElement>) => {
    const { clientX: x, clientY: y } = event;
    toggleTheme({ x, y });
  };

  return (
    <>
      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col",
          isFullscreen && "bg-background fixed inset-0 z-50"
        )}
      >
        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex flex-1 flex-col overflow-hidden"
        >
          <HorizontalScrollArea className="mt-2 mb-1 flex w-full items-center justify-between px-4">
            <TabsList className="bg-background text-muted-foreground inline-flex w-fit items-center justify-center rounded-full px-0">
              <TabsTriggerPill value="preview">Preview</TabsTriggerPill>
              <TabsTriggerPill value="colors">Color Palette</TabsTriggerPill>
            </TabsList>

            <div className="flex items-center gap-0.5">
              {isFullscreen && (
                <TooltipWrapper label="Toggle Theme" asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleThemeToggle}
                    className="group size-8"
                  >
                    {theme === "light" ? (
                      <Sun className="transition-all group-hover:scale-120" />
                    ) : (
                      <Moon className="transition-all group-hover:scale-120" />
                    )}
                  </Button>
                </TooltipWrapper>
              )}
              {/* Inspector toggle button */}
              <TooltipWrapper label="Toggle Inspector" asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={toggleInspector}
                  className={cn(
                    "group h-8 w-8",
                    inspectorEnabled && "bg-accent text-accent-foreground w-auto"
                  )}
                >
                  <Inspect className="transition-all group-hover:scale-120" />
                  {inspectorEnabled && <span className="text-xs tracking-wide uppercase">on</span>}
                </Button>
              </TooltipWrapper>
              <TooltipWrapper
                label={isFullscreen ? "Exit full screen" : "Full screen"}
                className="hidden md:inline-flex"
                asChild
              >
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={toggleFullscreen}
                  className="group size-8"
                >
                  {isFullscreen ? (
                    <Minimize className="transition-all group-hover:scale-120" />
                  ) : (
                    <Maximize className="transition-all group-hover:scale-120" />
                  )}
                </Button>
              </TooltipWrapper>
            </div>
          </HorizontalScrollArea>

          <ScrollArea
            className="relative m-4 mt-1 flex flex-1 flex-col overflow-hidden rounded-lg border"
            ref={rootRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          >
            <div className="flex h-full flex-1 flex-col">
              <TabsContentPrimitive value="preview" className="m-0 h-full">
                <ExamplesPreviewContainer>
                  <div className="p-8 space-y-4">
                    <h1 className="text-2xl font-bold">Theme Preview</h1>
                    <p className="text-muted-foreground">
                      This is a preview of the selected theme.
                    </p>
                    <div className="flex flex-wrap gap-4">
                        <Button>Primary Button</Button>
                        <Button variant="secondary">Secondary Button</Button>
                        <Button variant="destructive">Destructive Button</Button>
                        <Button variant="outline">Outline Button</Button>
                        <Button variant="ghost">Ghost Button</Button>
                        <Button variant="link">Link Button</Button>
                    </div>
                  </div>
                </ExamplesPreviewContainer>
              </TabsContentPrimitive>

              <TabsContentPrimitive value="colors" className="space-y-6 p-4">
                <ColorPreview styles={styles} currentMode={currentMode} />
              </TabsContentPrimitive>

              <ScrollBar orientation="horizontal" />
            </div>
          </ScrollArea>
        </Tabs>
      </div>

      <InspectorOverlay inspector={inspector} enabled={inspectorEnabled} rootRef={rootRef} />
    </>
  );
};

export default ThemePreviewPanel;
