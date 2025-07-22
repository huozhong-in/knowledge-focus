import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/tweakcn/components/ui/dialog";
import CodePanel from "./code-panel";
import { ThemeEditorState } from "@/tweakcn/types/editor";

interface CodePanelDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  themeEditorState: ThemeEditorState;
}

export function CodePanelDialog({
  open,
  onOpenChange,
  themeEditorState,
}: CodePanelDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] p-0 py-6 overflow-hidden rounded-lg border shadow-lg gap-6">
        <DialogHeader className="sr-only">
          <DialogTitle>代码面板</DialogTitle>
        </DialogHeader>
        <div className="h-full overflow-auto px-6">
          <CodePanel themeEditorState={themeEditorState} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
