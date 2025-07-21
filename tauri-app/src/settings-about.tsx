import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { VERSION_INFO } from "@/version";

export default function SettingsAbout() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>知识焦点</CardTitle>
          <CardDescription>Knowledge Focus - 智能文档管理与知识发现工具</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">版本:</span>
            <Badge variant="secondary">{VERSION_INFO.version}</Badge>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">关于应用</h4>
            <p className="text-sm text-muted-foreground">
              知识焦点是一个帮助用户发现和利用电脑中各类文档知识的智能工具。
              通过动态标签系统和 AI 技术，让您的文档管理更加智能和高效。
            </p>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">核心功能</h4>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li>• 智能文档扫描与分析</li>
              <li>• 动态标签自动生成</li>
              <li>• AI 驱动的内容理解</li>
              <li>• 知识片段提取与管理</li>
            </ul>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium">技术架构</h4>
            <div className="flex gap-2 flex-wrap">
              <Badge variant="outline">Tauri</Badge>
              <Badge variant="outline">React</Badge>
              <Badge variant="outline">TypeScript</Badge>
              <Badge variant="outline">Rust</Badge>
              <Badge variant="outline">Python</Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
