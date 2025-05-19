import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from '@tauri-apps/api/event';
import { toast } from "sonner";
import { open } from '@tauri-apps/plugin-dialog';
import { fetch } from '@tauri-apps/plugin-http';
import { basename } from '@tauri-apps/api/path';
import { checkFullDiskAccessPermission, requestFullDiskAccessPermission } from "tauri-plugin-macos-permissions-api";
import {
  debug,
  info,
  attachConsole
} from '@tauri-apps/plugin-log';
import { 
  Folder, 
  FolderPlus, 
  MinusCircle, 
  PlusCircle, 
  Eye, 
  EyeOff, 
  AlertTriangle, 
  Check, 
  X, 
  Shield, 
  Settings, 
  Upload } from "lucide-react";
// UI组件
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { 
  Alert, 
  AlertDescription, 
  AlertTitle 
} from "@/components/ui/alert";
import { 
  Tabs, 
  TabsContent, 
  TabsList, 
  TabsTrigger 
} from "@/components/ui/tabs";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle, 
  DialogTrigger,
} from "@/components/ui/dialog";
import { 
  Card, 
  CardContent, 
  CardDescription, 
  CardFooter, 
  CardHeader, 
  CardTitle 
} from "@/components/ui/card";
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
function HomeAuthorization() {
  // 状态定义
  const [directories, setDirectories] = useState<Directory[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [permissionsHint, setPermissionsHint] = useState<PermissionsHint | null>(null);
  const [isPermissionDialogOpen, setIsPermissionDialogOpen] = useState(false);
  const [hasFullDiskAccess, setHasFullDiskAccess] = useState<boolean>(false);
  const [_, setCheckingPermissions] = useState<boolean>(false);
  
  // 初始化日志系统
  useEffect(() => {
    const initLogger = async () => {
      try {
        await attachConsole();
        info("日志系统初始化成功");
      } catch (e) {
        console.error("初始化日志系统失败", e);
      }
    };
    
    initLogger();
  }, []);
  
  // 新文件夹对话框相关状态
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newDirPath, setNewDirPath] = useState("");
  const [newDirAlias, setNewDirAlias] = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [isDraggingOver, setIsDraggingOver] = useState(false); // 新增：用于跟踪拖拽状态

  // 尝试获取所有文件夹的函数
  const fetchDirectories = async () => {
    try {
      setLoading(true);
      
      // 调用API获取文件夹列表
      const response = await fetch("http://127.0.0.1:60000/directories");
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success" && result.data) {
        const dirs = result.data as Directory[];
        setDirectories(dirs);
        
        // 检查是否需要进行完全磁盘访问权限检查
        // 如果有非默认常用文件夹，则检查完全磁盘访问权限
        const hasNonStandardDirs = dirs.some(dir => 
          dir.auth_status === "authorized" && !dir.path.includes("/Users") && 
          !dir.path.includes("/Documents") && !dir.path.includes("/Desktop") && 
          !dir.path.includes("/Downloads"));
          
        if (hasNonStandardDirs) {
          info("检测到非常用文件夹，需要检查完全磁盘访问权限");
          const hasAccess = await checkFullDiskAccess();
          if (!hasAccess) {
            info("未获得完全磁盘访问权限，需要向用户提示");
            toast.warning("检测到您正在监控系统文件夹，建议开启完全磁盘访问权限", {
              action: {
                label: "授权",
                onClick: requestFullDiskAccess
              }
            });
          }
        }
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
      // 如果有完全磁盘访问权限，传递此信息给后端
      const url = hasFullDiskAccess 
        ? "http://127.0.0.1:60000/directories/default?has_full_disk_access=true" 
        : "http://127.0.0.1:60000/directories/default";
      
      const response = await fetch(url);
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        toast.success("默认文件夹初始化成功");
        fetchDirectories(); // 重新获取文件夹列表
        
        // 如果没有完全磁盘访问权限，提示用户
        if (!hasFullDiskAccess) {
          toast.info("为了获得最佳体验，建议开启完全磁盘访问权限", {
            action: {
              label: "了解更多",
              onClick: showPermissionsGuide
            },
            duration: 8000,
          });
        }
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
      // 如果有完全磁盘访问权限，直接设置为已授权状态
      const initialAuthStatus = hasFullDiskAccess ? "authorized" : "pending";
      
      const response = await fetch("http://127.0.0.1:60000/directories", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: newDirPath,
          alias: newDirAlias || null,
          auth_status: initialAuthStatus, // 添加初始授权状态
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
        
        // 如果没有完全磁盘访问权限且是系统路径，提示用户
        if (!hasFullDiskAccess && 
            !newDirPath.includes("/Users") && 
            !newDirPath.includes("/Documents") && 
            !newDirPath.includes("/Desktop") && 
            !newDirPath.includes("/Downloads")) {
          toast.warning("检测到您添加了系统文件夹，建议开启完全磁盘访问权限", {
            action: {
              label: "授权",
              onClick: requestFullDiskAccess
            },
            duration: 8000,
          });
        }
      } else {
        toast.error(result.message || "添加文件夹失败");
      }
    } catch (err) {
      console.error("添加文件夹失败", err);
      toast.error("添加文件夹失败，请检查API服务是否启动");
    }
  };

  // 通过路径添加文件夹（用于拖放操作）
  const handleAddDirectoryWithPath = async (dirPath: string, dirAlias?: string) => {
    if (!dirPath) {
      toast.error("文件夹路径不能为空");
      return null;
    }

    try {
      // 如果有完全磁盘访问权限，直接设置为已授权状态
      const initialAuthStatus = hasFullDiskAccess ? "authorized" : "pending";
      
      const response = await fetch("http://127.0.0.1:60000/directories", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          path: dirPath,
          alias: dirAlias || null,
          auth_status: initialAuthStatus, // 添加初始授权状态
        }),
      });
      
      const responseJson = await response.json();
      const result = responseJson as ApiResponse;
      
      if (result.status === "success") {
        toast.success(result.message || `成功添加文件夹 "${dirAlias || dirPath}"`);
        fetchDirectories(); // 刷新列表
        
        // 如果没有完全磁盘访问权限且是系统路径，提示用户
        if (!hasFullDiskAccess && 
            !dirPath.includes("/Users") && 
            !dirPath.includes("/Documents") && 
            !dirPath.includes("/Desktop") && 
            !dirPath.includes("/Downloads")) {
          toast.warning("检测到您添加了系统文件夹，建议开启完全磁盘访问权限", {
            action: {
              label: "授权",
              onClick: requestFullDiskAccess
            },
            duration: 8000,
          });
        }
        
        // 返回添加的目录ID（如果后端提供）
        if (result.data && typeof result.data === 'object' && 'id' in result.data) {
          return { directoryId: result.data.id };
        }
        return { success: true };
      } else {
        toast.error(result.message || "添加文件夹失败");
        return null;
      }
    } catch (err) {
      console.error("添加文件夹失败", err);
      toast.error("添加文件夹失败，请检查API服务是否启动");
      return null;
    }
  };

  // 更新文件夹授权状态
  const updateAuthStatus = async (directory: Directory, newStatus: string) => {
    try {
      // 如果是要授权，先尝试读取该目录，以触发macOS授权弹窗
      if (newStatus === "authorized") {
        info(`尝试读取文件夹以触发系统授权对话框: ${directory.path}`);
        // 显示加载状态
        toast.loading(`正在请求访问权限: ${directory.alias || directory.path}...`, {id: `auth-${directory.id}`});
        
        try {
          // 调用后端API尝试读取目录，这将触发系统授权对话框
          const testResponse = await fetch(`http://127.0.0.1:60000/directories/${directory.id}/test-access`, {
            method: "GET",
          });
          const testResult = await testResponse.json() as ApiResponse;
          
          if (testResult.status === "success") {
            info(`成功读取目录 ${directory.path}: ${JSON.stringify(testResult)}`);
            toast.success(`成功获取"${directory.alias || directory.path}"的访问权限`, {id: `auth-${directory.id}`});
          } else {
            // 如果读取失败但不是权限问题，可能是其他错误
            info(`读取目录失败 ${directory.path}: ${testResult.message}`);
            toast.error(`无法访问"${directory.alias || directory.path}": ${testResult.message}`, {id: `auth-${directory.id}`});
            return; // 如果读取失败，不继续更新状态
          }
        } catch (readErr) {
          // 捕获网络错误或其他异常
          info(`读取目录异常 ${directory.path}: ${readErr}`);
          toast.error(`尝试访问文件夹时出错`, {id: `auth-${directory.id}`});
          console.error("测试文件夹访问权限失败:", readErr);
          return; // 如果读取出错，不继续更新状态
        }
      }
      
      // 更新后端状态
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
        const message = newStatus === "authorized" 
          ? `成功授权"${directory.alias || directory.path}"`
          : `已取消"${directory.alias || directory.path}"的授权`;
        toast.success(message);
        fetchDirectories();
      } else {
        toast.error(result.message || "更新授权状态失败");
      }
    } catch (err) {
      console.error("更新授权状态失败", err);
      toast.error("更新授权状态失败，请检查API服务是否启动");
    }
  };

  // 请求目录访问权限 - 触发系统权限对话框并启动检查循环
  const requestDirectoryAccess = async (directory: Directory) => {
    try {
      info(`请求访问目录权限: ${directory.path}`);
      toast.loading(`请求访问"${directory.alias || directory.path}"权限...`, {id: `auth-req-${directory.id}`});
      
      // 调用后端API尝试读取目录，这将触发系统授权对话框
      const response = await fetch(`http://127.0.0.1:60000/directories/${directory.id}/request-access`, {
        method: "POST",
      });
      
      const result = await response.json() as ApiResponse;
      
      if (result.status === "success") {
        info(`已发送访问请求: ${JSON.stringify(result)}`);
        toast.success(`请查看系统弹出的权限请求对话框`, {id: `auth-req-${directory.id}`});
        
        // 开始循环检查访问状态
        checkDirectoryAccessStatus(directory);
      } else {
        toast.error(`无法请求访问"${directory.alias || directory.path}": ${result.message}`, {id: `auth-req-${directory.id}`});
      }
    } catch (err) {
      console.error("请求目录访问权限失败:", err);
      toast.error(`请求权限失败，请检查API服务是否启动`, {id: `auth-req-${directory.id}`});
    }
  };

  // 检查指定文件夹的访问权限状态
  const checkDirectoryAccessStatus = async (directory: Directory) => {
    info(`开始检查文件夹访问权限状态: ${directory.path}`);
    let attempts = 0;
    const maxAttempts = 10;
    const checkInterval = 1500; // 1.5秒检查一次
    
    // 显示加载状态
    toast.loading(`正在检查访问权限状态...`, {id: `check-auth-${directory.id}`});
    
    // 创建一个循环检查函数
    const checkAccess = async (): Promise<boolean> => {
      try {
        const response = await fetch(`http://127.0.0.1:60000/directories/${directory.id}/access-status`);
        const result = await response.json() as ApiResponse;
        
        if (result.status === "success") {
          const accessGranted = result.data?.access_granted === true;
          info(`文件夹 ${directory.path} 访问权限状态: ${accessGranted ? '已授权' : '未授权'}`);
          return accessGranted;
        }
        return false;
      } catch (err) {
        info(`检查文件夹访问权限状态出错: ${err}`);
        console.error("检查访问权限状态出错:", err);
        return false;
      }
    };
    
    // 使用Promise和setInterval实现周期性检查
    return new Promise<boolean>(async (resolve) => {
      const intervalId = setInterval(async () => {
        attempts++;
        info(`检查文件夹访问权限，第 ${attempts}/${maxAttempts} 次尝试`);
        
        const hasAccess = await checkAccess();
        if (hasAccess || attempts >= maxAttempts) {
          clearInterval(intervalId);
          if (hasAccess) {
            toast.success(`成功获得"${directory.alias || directory.path}"的访问权限`, {id: `check-auth-${directory.id}`});
            // 更新授权状态到后端
            await updateDirectoryAuthStatus(directory, "authorized");
          } else if (attempts >= maxAttempts) {
            toast.error(`无法获得"${directory.alias || directory.path}"的访问权限，用户可能拒绝了请求`, {id: `check-auth-${directory.id}`});
            // 更新授权状态到后端
            await updateDirectoryAuthStatus(directory, "unauthorized");
          }
          resolve(hasAccess);
        }
      }, checkInterval);
    });
  };

  // 仅更新目录授权状态到数据库而不触发读取操作
  const updateDirectoryAuthStatus = async (directory: Directory, newStatus: string) => {
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
        info(`成功更新文件夹 ${directory.path} 的授权状态为 ${newStatus}`);
        fetchDirectories(); // 刷新列表
      } else {
        info(`更新授权状态失败: ${result.message}`);
      }
    } catch (err) {
      console.error("更新授权状态失败", err);
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

  // 检查完全磁盘访问权限
  const checkFullDiskAccess = async () => {
    try {
      setCheckingPermissions(true);
      info("检查完全磁盘访问权限...");
      
      // 检查是否在开发环境
      const isDev = process.env.NODE_ENV === 'development' || window.location.hostname === 'localhost';
      if (isDev) {
        info("检测到开发环境，将向后端查询磁盘访问状态");
        // 在开发环境中，通过API查询权限状态
        try {
          const response = await fetch("http://127.0.0.1:60000/system/full-disk-access-status");
          const result = await response.json() as ApiResponse;
          
          if (result.status === "success" && result.data) {
            const hasAccess = result.data.has_full_disk_access === true;
            info(`从后端API获取完全磁盘访问权限状态: ${hasAccess}`);
            setHasFullDiskAccess(hasAccess);
            return hasAccess;
          }
        } catch (apiErr) {
          info(`无法从API获取磁盘访问状态: ${apiErr}`);
        }
      }
      
      // 如果不在开发环境或API查询失败，则使用插件检查
      const hasAccess = await checkFullDiskAccessPermission();
      info(`通过插件获取完全磁盘访问权限状态: ${hasAccess}`);
      setHasFullDiskAccess(hasAccess);
      return hasAccess;
    } catch (err) {
      console.error("检查完全磁盘访问权限失败", err);
      info(`检查完全磁盘访问权限失败: ${err}`);
      return false;
    } finally {
      setCheckingPermissions(false);
    }
  };

  // 请求完全磁盘访问权限
  const requestFullDiskAccess = async () => {
    try {
      info("请求完全磁盘访问权限...");
      await requestFullDiskAccessPermission();
      toast.info("已打开系统偏好设置，请授予完全磁盘访问权限");
      // 权限请求后，我们不立即检查权限状态，因为用户可能需要时间去授权
      // 当用户返回应用时，我们会再次检查权限状态
    } catch (err) {
      console.error("请求完全磁盘访问权限失败", err);
      info(`请求完全磁盘访问权限失败: ${err}`);
      toast.error("请求完全磁盘访问权限失败");
    }
  };

  // 在组件加载时获取文件夹列表并设置拖拽事件监听
  useEffect(() => {
    // 初始化日志控制台
    const initLogs = async () => {
      try {
        await attachConsole();
        info("日志系统初始化成功");
        // 输出一些调试信息
        debug("系统平台信息:");
        debug(`User-Agent: ${navigator.userAgent}`);
        debug(`窗口尺寸: ${window.innerWidth}x${window.innerHeight}`);
        debug(`拖拽overlay状态: ${isDraggingOver}`);
        
        // 检查操作系统类型
        const isMacOS = navigator.userAgent.toLowerCase().includes('mac');
        if (isMacOS) {
          info("检测到macOS系统，将检查完全磁盘访问权限");
          // 在macOS上，初始化时检查完全磁盘访问权限
          await checkFullDiskAccess();
        } else {
          info("非macOS系统，跳过完全磁盘访问权限检查");
        }
      } catch (e) {
        console.error("初始化日志系统失败", e);
      }
    };
    initLogs();

    // 获取文件夹列表和权限提示信息
    fetchDirectories();
    fetchMacOSPermissionsHint();
    
    // 设置拖拽事件监听器
    const setupDragDropListeners = async () => {
      // info("正在设置拖拽事件监听器...");
      
      try {
        // 尝试检测 Tauri 事件 API
        // info("尝试监听 Tauri 拖拽事件...");
        
        // 进入拖拽区域
        const unlistenDragEnter = await listen('tauri://drag-enter', (event) => {
          info(`拖拽进入事件触发: ${JSON.stringify(event)}`);
          setIsDraggingOver(true);
          debug(`isDraggingOver 状态已设置为: ${true}`);
        });
        // info("成功设置 drag-enter 监听器");

        // 使用 dragover 事件 (有些平台可能需要这个)
        const unlistenDragOver = await listen('tauri://drag-over', (event) => {
          info(`拖拽悬停事件触发: ${JSON.stringify(event)}`);
          setIsDraggingOver(true);
          debug(`isDraggingOver 状态已设置为: ${true}`);
        });
        // info("成功设置 drag-over 监听器");

        // 离开拖拽区域
        const unlistenDragLeave = await listen('tauri://drag-leave', (event) => {
          info(`拖拽离开事件触发: ${JSON.stringify(event)}`);
          setIsDraggingOver(false);
          debug(`isDraggingOver 状态已设置为: ${false}`);
        });
        // info("成功设置 drag-leave 监听器");

        // 放置文件/文件夹
        const unlistenDragDrop = await listen('tauri://drag-drop', async (event) => {
          info(`拖拽放置事件触发: ${JSON.stringify(event)}`);
          setIsDraggingOver(false);
          
          try {
            // 为Tauri拖放事件的payload定义一个接口，增强类型安全
            interface TauriDragDropPayload {
              paths: string[];
              position: { x: number; y: number }; // 根据日志，payload还包含position
            }

            // 解析拖放的路径
            const dropPayload = event.payload as TauriDragDropPayload;
            const paths = dropPayload.paths; // 从payload对象中获取paths数组
            info(`拖拽事件载荷类型: ${typeof event.payload}, 是数组: ${Array.isArray(event.payload)}`);
            info(`拖拽事件完整载荷: ${JSON.stringify(event.payload)}`);
            if (paths && paths.length > 0) {
              info(`检测到 ${paths.length} 个拖入项目: ${JSON.stringify(paths)}`);
              toast.info(`检测到 ${paths.length} 个拖入项目，正在处理...`);
              
              // 处理每个拖入的路径
              for (const droppedPath of paths) {
                try {
                  debug(`正在处理路径: ${droppedPath}`);
                  info(`路径类型: ${typeof droppedPath}, 长度: ${droppedPath.length}`);
                  // 输出一些特殊字符，以检查路径中是否有不可见字符
                  info(`路径前10个字符: "${droppedPath.substring(0, 10)}"`);
                  info(`路径最后10个字符: "${droppedPath.substring(droppedPath.length - 10)}"`);
                  
                  // 处理可能的文件URL格式路径
                  let processedPath = droppedPath;
                  if (typeof processedPath === 'string' && processedPath.startsWith('file://')) {
                    info(`检测到文件URL格式，尝试解码: ${processedPath}`);
                    // 移除 file:// 前缀并解码URL
                    processedPath = decodeURIComponent(processedPath.replace(/^file:\/\//, ''));
                    info(`解码后的路径: ${processedPath}`);
                  }
                  // 调用Rust命令解析目录路径
                  const resolvedDir = await invoke<string>("resolve_directory_from_path", { path_str: processedPath });
                  info(`路径 ${processedPath} 解析结果: ${resolvedDir}`);
                  
                  if (resolvedDir) {
                    try {
                      // 获取文件夹名称作为默认别名
                      const dirName = await basename(resolvedDir);
                      info(`将添加目录: ${resolvedDir}，别名: ${dirName}`);
                      
                      // 添加目录并获取结果
                      const addResult = await handleAddDirectoryWithPath(resolvedDir, dirName);
                      
                      // 如果没有完全磁盘访问权限，并且添加成功并返回了目录ID，则尝试请求访问权限
                      if (!hasFullDiskAccess && addResult && addResult.directoryId) {
                        info(`成功添加目录，ID: ${addResult.directoryId}，将请求访问权限`);
                        
                        // 创建一个临时的Directory对象用于授权检查
                        const tempDir: Directory = {
                          id: addResult.directoryId,
                          path: resolvedDir,
                          alias: dirName,
                          auth_status: "pending",
                          is_blacklist: false,
                          created_at: new Date().toISOString(),
                          updated_at: new Date().toISOString()
                        };
                        
                        // 延迟一点请求权限，让UI有时间更新
                        setTimeout(() => {
                          requestDirectoryAccess(tempDir);
                        }, 500);
                      }
                    } catch (processErr) {
                      info(`处理目录 ${resolvedDir} 时出错: ${processErr}`);
                      toast.error(`处理文件夹时出错: ${processErr}`);
                    }
                  } else {
                    info(`无法解析路径: ${droppedPath}`);
                    toast.error(`无法解析路径: ${droppedPath}`);
                  }
                } catch (err) {
                  info(`处理拖拽路径 ${droppedPath} 出错: ${err}`);
                  console.error(`处理拖拽路径 ${droppedPath} 出错:`, err);
                  const pathName = await basename(droppedPath).catch(() => droppedPath);
                  const errorMessage = typeof err === 'string' ? err : (err as Error)?.message || "未知错误";
                  toast.error(`处理 ${pathName} 出错: ${errorMessage}`);
                }
              }
            } else {
              info("拖入项目为空或格式不正确");
              toast.error("无法识别拖放的文件或文件夹");
            }
          } catch (err) {
            info(`解析拖放事件出错: ${err}`);
            console.error("解析拖放事件出错:", err);
            toast.error("处理拖放文件时出错");
          }
        });
        // info("成功设置 drag-drop 监听器");
        
        // 返回清理函数
        return () => {
          // info("清理拖拽事件监听器");
          unlistenDragEnter();
          unlistenDragOver();
          unlistenDragLeave();
          unlistenDragDrop();
        };
      } catch (err) {
        info(`设置拖拽事件监听器失败: ${err}`);
        console.error("设置拖拽事件监听器失败:", err);
        toast.error("初始化拖拽事件失败");
        return () => {}; // 返回空函数
      }
    };
    
    // 设置监听器并在组件卸载时清理
    const cleanupPromise = setupDragDropListeners();
    return () => {
      cleanupPromise.then(cleanup => cleanup && cleanup());
    };
  }, []);

  // 监听窗口焦点事件，当用户从系统设置返回应用时，重新检查权限状态
  useEffect(() => {
    const setupFocusListener = async () => {
      try {
        // info("正在设置窗口焦点监听器...");
        
        // 监听窗口获得焦点事件
        const unlistenFocus = await listen('tauri://focus', async () => {
          info("应用获得焦点，重新检查完全磁盘访问权限...");
          await checkFullDiskAccess();
        });
        
        // info("成功设置窗口焦点监听器");
        
        // 返回清理函数
        return () => {
          // info("清理窗口焦点监听器");
          unlistenFocus();
        };
      } catch (err) {
        info(`设置窗口焦点监听器失败: ${err}`);
        console.error("设置窗口焦点监听器失败:", err);
        return () => {}; // 返回空函数
      }
    };
    
    const cleanupPromise = setupFocusListener();
    return () => {
      cleanupPromise.then(cleanup => cleanup && cleanup());
    };
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
                {hasFullDiskAccess ? (
                  <span className="flex items-center text-green-600">
                    <Shield size={16} className="mr-1" />通过完全磁盘访问权限授权
                  </span>
                ) : dir.is_blacklist ? (
                  <span className="flex items-center text-gray-400">
                    <MinusCircle size={16} className="mr-1" />已加入黑名单
                  </span>
                ) : dir.auth_status === "authorized" ? (
                  <span className="flex items-center text-whiskey-600">
                    <Check size={16} className="mr-1" />已授权
                  </span>
                ) : dir.auth_status === "unauthorized" ? (
                  <span className="flex items-center text-red-400">
                    <X size={16} className="mr-1" />未授权
                  </span>
                ) : (
                  <span className="flex items-center text-whiskey-500">
                    <AlertTriangle size={16} className="mr-1" />待授权
                  </span>
                )}
              </TableCell>
              <TableCell className="text-right flex justify-end gap-2">
                {/* 授权/取消授权按钮 */}
                {hasFullDiskAccess ? (
                  <Button variant="outline" size="sm" disabled className="opacity-50 cursor-not-allowed" title="已获得完全磁盘访问权限，无需单独授权">
                    <Shield size={16} className="mr-1" />已授权
                  </Button>
                ) : dir.is_blacklist ? (
                  <Button variant="outline" size="sm" disabled className="opacity-50 cursor-not-allowed">
                    <Eye size={16} className="mr-1" />授权
                  </Button>
                ) : dir.auth_status === "authorized" ? (
                  <Button variant="outline" size="sm" onClick={() => updateAuthStatus(dir, "pending")}>
                    <EyeOff size={16} className="mr-1" />取消授权
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => requestDirectoryAccess(dir)}>
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
                    <Button 
                      variant="destructive" 
                      size="sm"
                      disabled={hasFullDiskAccess} 
                      className={hasFullDiskAccess ? "opacity-50 cursor-not-allowed" : ""}
                      title={hasFullDiskAccess ? "已获得完全磁盘访问权限，无需移除文件夹" : ""}
                    >
                      删除
                    </Button>
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

  // 添加React中DOM标准拖拽处理函数
  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    info("DOM 标准拖拽进入事件触发");
    setIsDraggingOver(true);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    // 不要在每次drag over时都设置state和打印日志，会导致性能问题
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    info("DOM 标准拖拽离开事件触发");
    // 检查是否真的离开了容器，而不是进入了子元素
    // 使用relatedTarget来检查是否离开了容器
    const relatedTarget = e.relatedTarget as Node;
    if (!e.currentTarget.contains(relatedTarget)) {
      setIsDraggingOver(false);
    }
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    info("DOM 标准拖拽放置事件触发");
    setIsDraggingOver(false);

    // 只是记录，但不作实际处理，因为Tauri的事件系统应该会处理
    const files = Array.from(e.dataTransfer.files);
    info(`标准DOM拖放检测到 ${files.length} 个文件:`);
    files.forEach((file, i) => {
      info(`文件 ${i+1}: ${file.name}, 类型: ${file.type}`);
    });
    
    // 这里我们不再直接处理，因为应该由Tauri的事件系统接管
    toast.info("拖放事件已触发，等待Tauri处理...");
  };
  
  return (
    <main 
      className="container mx-auto p-3 relative"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* 拖拽覆盖层，确保z-index足够高且覆盖整个界面 */}
      {isDraggingOver && (
        <div className="fixed inset-0 bg-whiskey-200/90 flex flex-col items-center justify-center z-[9999] border-4 border-dashed border-whiskey-500 rounded-lg pointer-events-none backdrop-blur-sm transition-all duration-200">
          <div className="bg-whiskey-50 p-8 rounded-xl shadow-lg border-2 border-whiskey-400">
            <Upload size={72} className="text-whiskey-600 mb-4 mx-auto" />
            <p className="text-2xl font-bold text-whiskey-900 text-center">将文件或文件夹拖放到此处</p>
            <p className="text-sm text-whiskey-700 mt-2 text-center">文件将自动添加其所在的父文件夹</p>
          </div>
        </div>
      )}      
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">授权监控文件变化</h1>
          <p className="text-muted-foreground">当文件发生变化，系统将自动解析其中的知识</p>
        </div>
        
        <div className="flex gap-2">
          {/* macOS权限按钮 */}
          <Button variant="outline" onClick={showPermissionsGuide} className="border-whiskey-200 hover:bg-whiskey-50 text-whiskey-700">
            <Shield className="mr-2 h-4 w-4" /> macOS权限指南
          </Button>          
          {/* 完全磁盘访问按钮 */}
          {!hasFullDiskAccess && (
            <Button variant="outline" onClick={requestFullDiskAccess} className="border-green-200 hover:bg-green-50 text-green-700">
              <Shield className="mr-2 h-4 w-4" /> 请求完全磁盘访问
            </Button>
          )}
          {/* 添加文件夹按钮 */}
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-whiskey-200 hover:bg-whiskey-300 text-whiskey-900">
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
                      placeholder="/Users/tom/Documents"
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
      
      <Card className="border-whiskey-100">
        <CardHeader className="bg-whiskey-50/50">
          <CardTitle className="text-whiskey-900">文件夹管理</CardTitle>
          <CardDescription className="text-whiskey-700">
            查看和管理所有需要监控的文件夹，授权或取消授权读取权限。
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* 完全磁盘访问权限提示 */}
          {hasFullDiskAccess && (
            <Alert className="mb-6 bg-green-50 border-green-200">
              <Shield className="h-4 w-4 text-green-600" />
              <AlertTitle className="text-green-700">已获得完全磁盘访问权限</AlertTitle>
              <AlertDescription className="text-green-600">
                您的应用已获得macOS完全磁盘访问权限，可以访问所有文件夹，无需单独授权每个文件夹。
              </AlertDescription>
            </Alert>
          )}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-4 bg-whiskey-100">
              <TabsTrigger value="all" className="data-[state=active]:bg-whiskey-200 data-[state=active]:text-whiskey-900">全部</TabsTrigger>
              <TabsTrigger value="authorized" className="data-[state=active]:bg-whiskey-200 data-[state=active]:text-whiskey-900">已授权</TabsTrigger>
              <TabsTrigger value="pending" className="data-[state=active]:bg-whiskey-200 data-[state=active]:text-whiskey-900">待授权</TabsTrigger>
              <TabsTrigger value="blacklist" className="data-[state=active]:bg-whiskey-200 data-[state=active]:text-whiskey-900">黑名单</TabsTrigger>
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
            Tips: 如果你误删了常见文件夹，可以点击右侧恢复默认文件夹。
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
                  <h3 className="font-bold flex items-center">
                    完全磁盘访问
                    {hasFullDiskAccess && (
                      <span className="ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">已授权</span>
                    )}
                  </h3>
                  <p className="text-sm">{permissionsHint.full_disk_access}</p>
                  {!hasFullDiskAccess && (
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={requestFullDiskAccess} 
                      className="mt-2 border-green-200 hover:bg-green-50 text-green-700"
                    >
                      <Shield className="mr-2 h-4 w-4" /> 请求完全磁盘访问权限
                    </Button>
                  )}
                  <p className="text-xs text-muted-foreground mt-2">
                    注意：在macOS系统中，一旦本应用获得了"完全磁盘访问权限"，将自动获得对所有"文件与文件夹"的访问权限，无需单独授权每个文件夹。
                  </p>
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

export default HomeAuthorization;
