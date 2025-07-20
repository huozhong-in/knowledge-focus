import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsBusinessApis() {
  return (
      <Card className="w-full">
        <CardHeader>
          <CardTitle>在线 AI 服务</CardTitle>
          <CardDescription>配置第三方 AI 服务 API</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground">
            在线模型 API 配置功能即将推出...
          </div>
        </CardContent>
      </Card>
  );
}
