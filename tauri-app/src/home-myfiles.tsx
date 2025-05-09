// filepath: /Users/dio/workspace/knowledge-focus/tauri-app/src/home-myfiles.tsx
import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from '@tauri-apps/api/event';
import { toast } from "sonner";
import { open } from '@tauri-apps/plugin-dialog';
import { fetch } from '@tauri-apps/plugin-http';
import { Folder, FolderPlus, MinusCircle, PlusCircle, Eye, EyeOff, AlertTriangle, Check, X, Shield, Settings } from "lucide-react";

// UI组件
import { Button } from "@/components/ui/button";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle, 
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

// 定义文件夹类型接口
interface Directory {
  id: number;
  path: string;
  alias: string | null;
  auth_status: string; // "pending", "authorized", "unauthorized"
  is_blacklist: boolean;
  created_at: string;
  updated_at: string;
}

// 定义API响应接口
interface ApiResponse {
  status: string;
  message?: string;
  data?: any;
}

// 定义权限提示接口
interface PermissionsHint {
  full_disk_access: string;
  docs_desktop_downloads: string;
  removable_volumes: string;
  network_volumes: string;
}

// 主组件
function HomeMyFiles() {
  // 状态定义
  const [directories, setDirectories] = useState<Directory[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [permissionsHint, setPermissionsHint] = useState<PermissionsHint | null>(null);
  const [isPermissionDialogOpen, setIsPermissionDialogOpen] = useState(false);
  
  // 新文件夹对话框相关状态
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newDirPath, setNewDirPath] = useState("");
  const [newDirAlias, setNewDirAlias] = useState("");
  const [activeTab, setActiveTab] = useState("all");

  // 尝试获取所有文件夹的函数
  const fetchDirectories = async () => {
    try {
      setLoading(true);
      
      // 调用API获取文件夹列表
      const response = await fetch("http://127.0.0.1:60000/directories");
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success" && result.data) {
        setDirectories(result.data);
      } else {
        toast.error(result.message || "获取文件夹列表失败");
      }
    } catch (err) {
      console.error("获取文件夹失败", err);
      toast.error("获取文件夹列表失败，请检查API服务是否启动");
    } finally {
      setLoading(false);
    }
  };

  // 获取macOS权限提示信息
  const fetchMacOSPermissionsHint = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60000/macos-permissions-hint");
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success" && result.data) {
        setPermissionsHint(result.data);
      }
    } catch (err) {
      console.error("获取权限提示信息失败", err);
    }
  };

  // 显示权限指南对话框
  const showPermissionsGuide = () => {
    fetchMacOSPermissionsHint();
    setIsPermissionDialogOpen(true);
  };

  // 初始化默认文件夹
  const initializeDefaultDirectories = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60000/directories/default");
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        toast.success("默认文件夹初始化成功");
        fetchDirectories(); // 重新获取文件夹列表
      } else {
        toast.error(result.message || "初始化默认文件夹失败");
      }
    } catch (err) {
      console.error("初始化默认文件夹失败", err);
      toast.error("初始化默认文件夹失败，请检查API服务是否启动");
    }
  };

  // 添加新文件夹
  const addDirectory = async () => {
    if (!newDirPath) {
      toast.error("文件夹路径不能为空");
      return;
    }

    try {
      const response = await fetch("http://127.0.0.1:60000/directories", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: newDirPath,
          alias: newDirAlias || null,
        }),
      });
      
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        toast.success(result.message || "添加文件夹成功");
        setIsDialogOpen(false);
        setNewDirPath("");
        setNewDirAlias("");
        fetchDirectories();
      } else {
        toast.error(result.message || "添加文件夹失败");
      }
    } catch (err) {
      console.error("添加文件夹失败", err);
      toast.error("添加文件夹失败，请检查API服务是否启动");
    }
  };

  // 更新文件夹授权状态
  const updateAuthStatus = async (directory: Directory, newStatus: string) => {
    try {
      const response = await fetch(`http://127.0.0.1:60000/directories/${directory.id}/auth_status`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          auth_status: newStatus,
        }),
      });
      
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        toast.success(result.message || `成功更新"${directory.alias || directory.path}"的授权状态`);
        fetchDirectories();
      } else {
        toast.error(result.message || "更新授权状态失败");
      }
    } catch (err) {
      console.error("更新授权状态失败", err);
      toast.error("更新授权状态失败，请检查API服务是否启动");
    }
  };

  // 切换黑名单状态
  const toggleBlacklist = async (directory: Directory, isBlacklist: boolean) => {
    try {
      const response = await fetch(`http://127.0.0.1:60000/directories/${directory.id}/blacklist`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          is_blacklist: isBlacklist,
        }),
      });
      
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        const action = isBlacklist ? "加入" : "移出";
        toast.success(result.message || `成功${action}"${directory.alias || directory.path}"到黑名单`);
        fetchDirectories();
      } else {
        toast.error(result.message || "更新黑名单状态失败");
      }
    } catch (err) {
      console.error("更新黑名单状态失败", err);
      toast.error("更新黑名单状态失败，请检查API服务是否启动");
    }
  };

  // 删除文件夹
  const removeDirectory = async (directory: Directory) => {
    try {
      const response = await fetch(`http://127.0.0.1:60000/directories/${directory.id}`, {
        method: "DELETE",
      });
      
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        toast.success(result.message || `成功删除"${directory.alias || directory.path}"`);
        fetchDirectories();
      } else {
        toast.error(result.message || "删除文件夹失败");
      }
    } catch (err) {
      console.error("删除文件夹失败", err);
      toast.error("删除文件夹失败，请检查API服务是否启动");
    }
  };

  // 选择文件夹对话框
  const openFolderPicker = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "选择要监控的文件夹",
      });
      
      if (selected && !Array.isArray(selected)) {
        setNewDirPath(selected);
      }
    } catch (err) {
      console.error("选择文件夹失败", err);
      toast.error("选择文件夹失败");
    }
  };

  // 在组件加载时获取文件夹列表
  useEffect(() => {
    // 只获取文件夹列表，不自动初始化默认文件夹
    fetchDirectories();
    
    // 获取权限提示信息
    fetchMacOSPermissionsHint();
  }, []);

  // 筛选文件夹
  const filteredDirectories = directories.filter(dir => {
    if (activeTab === "all") return true;
    if (activeTab === "authorized") return dir.auth_status === "authorized" && !dir.is_blacklist;
    if (activeTab === "pending") return dir.auth_status === "pending";
    if (activeTab === "blacklist") return dir.is_blacklist;
    return true;
  });

  // 渲染文件夹表格
  const renderDirectoryTable = () => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>名称/别名</TableHead>
          <TableHead>路径</TableHead>
          <TableHead>状态</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {filteredDirectories.length === 0 ? (
          activeTab === "all" ? (
            <TableRow>
              <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                <div>当前没有监控任何文件夹。</div>
                <Button onClick={initializeDefaultDirectories} className="mt-4">
                  导入macOS常用文件夹
                </Button>
              </TableCell>
            </TableRow>
          ) : (
            <TableRow>
              <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                {activeTab === "blacklist" 
                  ? "黑名单列表为空" 
                  : activeTab === "pending" 
                  ? "没有等待授权的文件夹"
                  : activeTab === "authorized"
                  ? "没有已授权的文件夹"
                  : "没有找到任何文件夹"}
              </TableCell>
            </TableRow>
          )
        ) : (
          filteredDirectories.map((dir) => (
            <TableRow key={dir.id}>
              <TableCell className="font-medium">
                {dir.alias || "未命名"}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {dir.path}
              </TableCell>
              <TableCell>
                {dir.auth_status === "authorized" ? (
                  <span className="flex items-center text-green-500">
                    <Check size={16} className="mr-1" />已授权
                  </span>
                ) : dir.auth_status === "unauthorized" ? (
                  <span className="flex items-center text-red-500">
                    <X size={16} className="mr-1" />未授权
                  </span>
                ) : (
                  <span className="flex items-center text-yellow-500">
                    <AlertTriangle size={16} className="mr-1" />待授权
                  </span>
                )}
              </TableCell>
              <TableCell className="text-right flex justify-end gap-2">
                {/* 授权/取消授权按钮 */}
                {dir.auth_status === "authorized" ? (
                  <Button variant="outline" size="sm" onClick={() => updateAuthStatus(dir, "pending")}>
                    <EyeOff size={16} className="mr-1" />取消授权
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => updateAuthStatus(dir, "authorized")}>
                    <Eye size={16} className="mr-1" />授权
                  </Button>
                )}
                
                {/* 黑名单/取消黑名单按钮 */}
                {dir.is_blacklist ? (
                  <Button variant="outline" size="sm" onClick={() => toggleBlacklist(dir, false)}>
                    <PlusCircle size={16} className="mr-1" />移出黑名单
                  </Button>
                ) : (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="outline" size="sm">
                        <MinusCircle size={16} className="mr-1" />加入黑名单
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>确认加入黑名单?</AlertDialogTitle>
                        <AlertDialogDescription>
                          加入黑名单后，此文件夹将不会被监控。您可以随时将其移出黑名单。
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>取消</AlertDialogCancel>
                        <AlertDialogAction onClick={() => toggleBlacklist(dir, true)}>确认</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}

                {/* 删除按钮 */}
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" size="sm">删除</Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>确认删除?</AlertDialogTitle>
                      <AlertDialogDescription>
                        删除后将不再监控此文件夹，但不会删除实际文件。
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>取消</AlertDialogCancel>
                      <AlertDialogAction onClick={() => removeDirectory(dir)}>确认删除</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );

  return (
    <main className="container mx-auto p-3">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">我的文件夹</h1>
          <p className="text-muted-foreground">管理需要监控的文件夹</p>
        </div>
        
        <div className="flex gap-2">
          {/* macOS权限指南按钮 */}
          <Button variant="outline" onClick={showPermissionsGuide}>
            <Shield className="mr-2 h-4 w-4" /> macOS权限指南
          </Button>
          
          {/* 添加文件夹按钮 */}
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <FolderPlus className="mr-2 h-4 w-4" /> 添加文件夹
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>添加新文件夹</DialogTitle>
                <DialogDescription>
                  选择要监控的文件夹，并可以为其添加别名便于识别。
                </DialogDescription>
              </DialogHeader>
              
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="path" className="text-right">
                    路径
                  </Label>
                  <div className="col-span-3 flex gap-2">
                    <Input id="path" 
                      value={newDirPath} 
                      onChange={(e) => setNewDirPath(e.target.value)} 
                      placeholder="/Users/example/Documents"
                      className="flex-1"
                    />
                    <Button type="button" variant="outline" onClick={openFolderPicker}>
                      <Folder className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label htmlFor="alias" className="text-right">
                    别名
                  </Label>
                  <Input id="alias" 
                    value={newDirAlias} 
                    onChange={(e) => setNewDirAlias(e.target.value)} 
                    placeholder="我的文档"
                    className="col-span-3" 
                  />
                </div>
              </div>
              
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>取消</Button>
                <Button type="button" onClick={addDirectory}>添加</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle>文件夹管理</CardTitle>
          <CardDescription>
            查看和管理所有需要监控的文件夹，授权或取消授权访问权限。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-4">
              <TabsTrigger value="all">全部</TabsTrigger>
              <TabsTrigger value="authorized">已授权</TabsTrigger>
              <TabsTrigger value="pending">待授权</TabsTrigger>
              <TabsTrigger value="blacklist">黑名单</TabsTrigger>
            </TabsList>
            
            <TabsContent value="all">{renderDirectoryTable()}</TabsContent>
            <TabsContent value="authorized">{renderDirectoryTable()}</TabsContent>
            <TabsContent value="pending">{renderDirectoryTable()}</TabsContent>
            <TabsContent value="blacklist">{renderDirectoryTable()}</TabsContent>
          </Tabs>
          
          {/* 加载中状态 */}
          {loading && <div className="flex justify-center py-8">加载中...</div>}
        </CardContent>
        <CardFooter className="flex justify-between items-center"> {/* Added items-center */}
          <p className="text-xs text-muted-foreground">
            注意：授权文件夹后，应用将能够监控这些文件夹中的变化，以提供文件洞察功能。
          </p>
          {directories.length > 0 && (
            <Button variant="outline" size="sm" onClick={initializeDefaultDirectories}>
              恢复默认文件夹
            </Button>
          )}
        </CardFooter>
      </Card>

      {/* 权限指南对话框 */}
      <Dialog open={isPermissionDialogOpen} onOpenChange={setIsPermissionDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>macOS权限指南</DialogTitle>
            <DialogDescription>
              请按照以下步骤授予应用所需的权限，以便正常监控文件夹。
            </DialogDescription>
          </DialogHeader>
          
          <div className="grid gap-4 py-4">
            {permissionsHint && (
              <>
                <div>
                  <h3 className="font-bold">完全磁盘访问</h3>
                  <p className="text-sm">{permissionsHint.full_disk_access}</p>
                </div>
                <div>
                  <h3 className="font-bold">文档、桌面和下载文件夹</h3>
                  <p className="text-sm">{permissionsHint.docs_desktop_downloads}</p>
                </div>
                <div>
                  <h3 className="font-bold">可移动卷</h3>
                  <p className="text-sm">{permissionsHint.removable_volumes}</p>
                </div>
                <div>
                  <h3 className="font-bold">网络卷</h3>
                  <p className="text-sm">{permissionsHint.network_volumes}</p>
                </div>
              </>
            )}
            
            <Alert>
              <Settings className="h-4 w-4" />
              <AlertTitle>权限设置提示</AlertTitle>
              <AlertDescription>
                您可以通过系统偏好设置 &gt; 安全性与隐私 &gt; 隐私 手动授予应用必要的权限。
              </AlertDescription>
            </Alert>
          </div>
          
          <DialogFooter>
            <Button type="button" onClick={() => setIsPermissionDialogOpen(false)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

export default HomeMyFiles;
