import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { VERSION_INFO } from "@/version";

export default function SettingsAbout() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Knowledge Focus </CardTitle>
          <CardDescription>A desktop intelligent agent platform that unlocks the knowledge value of local files</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Version:</span>
            <Badge variant="secondary">{VERSION_INFO.version}</Badge>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">About</h4>
            <p className="text-sm text-muted-foreground">
              Knowledge focus is an intelligent tool for managing and discovering knowledge in various documents on your computer.
            </p>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Core Features</h4>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li>• Rapid Document Directory Scanning</li>
              <li>• Generate Tags Based on File Content</li>
              <li>• Document Content Understanding and Analysis</li>
              <li>• Accumulate Knowledge Through Co-reading and Co-learning with AI</li>
            </ul>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Architecture</h4>
            <div className="flex gap-2 flex-wrap">
              <Badge variant="outline">Tauri/Rust</Badge>
              <Badge variant="outline">React/TypeScript/Vite/Bun</Badge>
              <Badge variant="outline">Python/PydanticAI</Badge>
              <Badge variant="outline">TailwindCSS</Badge>
              <Badge variant="outline">Shadcn/Tweakcn</Badge>
              <Badge variant="outline">Vercel AI SDK v5/AI Elements</Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
