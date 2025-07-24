import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { toast } from "sonner";
import { open } from '@tauri-apps/plugin-dialog';
import { fetch } from '@tauri-apps/plugin-http';
import { basename } from '@tauri-apps/api/path';

import {
  info
} from '@tauri-apps/plugin-log';
import { FolderTreeSelector } from "@/folder-tree-selector";
import { 
  Folder, 
  FolderPlus, 
  MinusCircle, 
  PlusCircle, 
  Eye, 
  EyeOff, 
  X,
  Shield, 
  Settings } from "lucide-react";
// UI组件
import { 
  Button 
} from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

// 定义文件夹类型接口
interface Directory {
  id: number;
  path: string;
  alias: string | null;
  is_blacklist: boolean;
  parent_id?: number | null; // 支持层级关系
  is_common_folder?: boolean; // 是否为常见文件夹
  created_at: string;
  updated_at: string;
}

// 文件夹层级结构接口
interface FolderHierarchy {
  id: number;
  path: string;
  alias: string | null;
  is_blacklist: boolean;
  is_common_folder: boolean;
  blacklist_children: Directory[]; // 后端返回的是blacklist_children字段
  created_at: string;
  updated_at: string;
}

// Bundle扩展名接口
interface BundleExtension {
  id: number;
  extension: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// 配置摘要接口
interface ConfigurationSummary {
  has_config_cache: boolean;
  config_categories_count: number;
  config_filter_rules_count: number;
  config_extension_maps_count: number;
  full_disk_access: boolean;
  monitored_dirs_count: number;
  blacklist_dirs_count: number;
  bundle_cache_count: number;
  bundle_cache_expired: boolean;
  bundle_cache_timestamp?: number;
}

// 配置变更队列状态接口
interface ConfigQueueStatus {
  initial_scan_completed: boolean;
  pending_changes_count: number;
  has_pending_changes: boolean;
}

// 主组件
function SettingsAuthorization() {
  // 状态定义
  const [loading, setLoading] = useState<boolean>(true);
  
  // 层级文件夹相关状态  
  const [folderHierarchy, setFolderHierarchy] = useState<FolderHierarchy[]>([]);
  const [selectedParentId, setSelectedParentId] = useState<number | null>(null);
  const [isBlacklistDialogOpen, setIsBlacklistDialogOpen] = useState(false);
  const [newBlacklistPath, setNewBlacklistPath] = useState("");
  const [newBlacklistAlias, setNewBlacklistAlias] = useState("");
  
  // Bundle扩展名相关状态
  const [bundleExtensions, setBundleExtensions] = useState<BundleExtension[]>([]);
  const [newBundleExtension, setNewBundleExtension] = useState("");
  const [newBundleDescription, setNewBundleDescription] = useState("");
  const [isBundleDialogOpen, setIsBundleDialogOpen] = useState(false);
  
  // 配置摘要状态
  const [configSummary, setConfigSummary] = useState<ConfigurationSummary | null>(null);
  
  // 界面控制状态
  const [showBundleSection, setShowBundleSection] = useState(false);
  
  // 新文件夹对话框相关状态
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newDirPath, setNewDirPath] = useState("");
  const [newDirAlias, setNewDirAlias] = useState("");
  
  // 配置变更队列状态
  const [queueStatus, setQueueStatus] = useState<ConfigQueueStatus | null>(null);
  
  // 初始化日志系统
  useEffect(() => {
    const initLogger = async () => {
      try {
        info("授权管理界面初始化");
      } catch (e) {
        console.error("初始化日志失败", e);
      }
    };
    
    initLogger();
  }, []);

  // ===== 数据加载函数 =====
  
  // 加载文件夹层级结构
  const loadFolderHierarchy = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60315/folders/hierarchy", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const apiResponse = await response.json();
        if (apiResponse.status === "success" && apiResponse.data) {
          setFolderHierarchy(apiResponse.data);
          // 计算黑名单常用文件夹数量
          const blacklistCommonFolders = apiResponse.data.filter((f: FolderHierarchy) => f.is_blacklist && f.is_common_folder).length;
          info(`已加载文件夹层级结构: ${apiResponse.data.length} 个根文件夹，其中 ${blacklistCommonFolders} 个是黑名单常用文件夹`);
          
          // 调试日志，输出所有一级文件夹的信息
          console.log("层级结构：", apiResponse.data.map((f: FolderHierarchy) => ({
            id: f.id,
            path: f.path,
            alias: f.alias,
            is_blacklist: f.is_blacklist,
            is_common_folder: f.is_common_folder
          })));
        }
      } else {
        console.error("加载文件夹层级结构失败: HTTP", response.status);
        toast.error("加载文件夹层级结构失败");
      }
    } catch (error) {
      console.error("加载文件夹层级结构失败:", error);
      toast.error("加载文件夹层级结构失败");
    }
  };

  // 加载Bundle扩展名
  const loadBundleExtensions = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60315/bundle-extensions", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const apiResponse = await response.json();
        if (apiResponse.status === "success" && apiResponse.data) {
          setBundleExtensions(apiResponse.data);
          info(`已加载Bundle扩展名: ${apiResponse.data.length} 个`);
        }
      } else {
        console.error("加载Bundle扩展名失败: HTTP", response.status);
      }
    } catch (error) {
      console.error("加载Bundle扩展名失败:", error);
    }
  };

  // 加载配置摘要
  const loadConfigSummary = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60315/config/all", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const configData = await response.json();
        // 从配置数据中提取摘要信息
        const summary: ConfigurationSummary = {
          has_config_cache: true,
          config_categories_count: configData.file_categories?.length || 0,
          config_filter_rules_count: configData.file_filter_rules?.length || 0,
          config_extension_maps_count: configData.file_extension_maps?.length || 0,
          full_disk_access: configData.full_disk_access || false,
          monitored_dirs_count: configData.monitored_folders?.filter((f: Directory) => !f.is_blacklist).length || 0,
          blacklist_dirs_count: configData.monitored_folders?.filter((f: Directory) => f.is_blacklist).length || 0,
          bundle_cache_count: 0, // 需要从bundle端点获取
          bundle_cache_expired: false,
          bundle_cache_timestamp: Date.now()
        };
        setConfigSummary(summary);
        
        // 注意：现在使用folderHierarchy，不再需要directories状态
      }
    } catch (error) {
      console.error("加载配置摘要失败:", error);
    }
  };

  // 检查配置变更队列状态
  const checkQueueStatus = async () => {
    try {
      const status = await invoke("queue_get_status") as ConfigQueueStatus;
      setQueueStatus(status);
      
      if (status.initial_scan_completed && status.has_pending_changes) {
        // 如果初始扫描已完成但还有待处理变更，这可能表明有问题
        console.warn("初始扫描已完成但仍有待处理的配置变更:", status);
      }
      
      return status;
    } catch (error) {
      console.error("检查配置队列状态失败:", error);
      return null;
    }
  };

  // 安全刷新监控配置 - 只在初始扫描完成后才执行刷新
  const safeRefreshMonitoringConfig = async () => {
    try {
      const queueStatus = await checkQueueStatus();
      if (queueStatus?.initial_scan_completed) {
        await invoke("refresh_monitoring_config");
        console.log("监控配置刷新成功");
        return true;
      } else {
        console.log("初始扫描未完成，跳过监控配置刷新");
        return false;
      }
    } catch (error) {
      console.warn("刷新监控配置失败:", error);
      return false;
    }
  };

  // 初始化数据加载
  useEffect(() => {
    const initializeData = async () => {
      setLoading(true);
      try {
        // 不再需要在此检查权限，因为进入该页面的先决条件是已获得权限
        await Promise.all([
          loadFolderHierarchy(),
          loadBundleExtensions(),
          loadConfigSummary(),
          checkQueueStatus(),
        ]);
      } catch (error) {
        console.error("初始化数据失败:", error);
        toast.error("加载数据失败");
      } finally {
        setLoading(false);
      }
    };

    initializeData();
    
    // 定期检查队列状态
    const queueStatusInterval = setInterval(async () => {
      await checkQueueStatus();
    }, 5000); // 每5秒检查一次

    return () => {
      clearInterval(queueStatusInterval);
    };
  }, []);

  // ===== 事件处理函数 =====

  // 添加新文件夹 - 只能添加白名单
  const handleAddDirectory = async () => {
    if (!newDirPath.trim()) {
      toast.error("请选择文件夹路径");
      return;
    }

    try {
      const response = await fetch("http://127.0.0.1:60315/directories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: newDirPath,
          alias: newDirAlias || null,
          is_blacklist: false // 只能添加白名单
        })
      });

      if (response.ok) {
        toast.success("白名单文件夹添加成功");
        setIsDialogOpen(false);
        setNewDirPath("");
        setNewDirAlias("");
        // 重新加载数据
        await loadConfigSummary();
        await loadFolderHierarchy();
        
        // 使用新的队列机制处理配置变更
        try {
          const queueResult = await invoke("queue_add_blacklist_folder", {
            folder_path: newDirPath,
            folder_alias: newDirAlias || null
          }) as { status: string; message: string };
          
          console.log("白名单文件夹队列处理结果:", queueResult);
          
          if (queueResult.status === "executed") {
            toast.success("白名单文件夹处理完成");
          } else if (queueResult.status === "queued") {
            toast.info("白名单文件夹已加入处理队列，将在初始扫描完成后自动处理");
          }
        } catch (invokeError) {
          console.warn("Rust队列处理失败，回退到传统方式:", invokeError);
          
          // 回退到原有方式：安全刷新监控配置
          try {
            await safeRefreshMonitoringConfig();
          } catch (configError) {
            console.warn("刷新监控配置失败，可能需要重启应用:", configError);
            toast.info("配置已更新，建议重启应用以确保生效");
          }
        }
      } else {
        const errorData = await response.json();
        toast.error(`添加失败: ${errorData.message || "未知错误"}`);
      }
    } catch (error) {
      console.error("添加文件夹失败:", error);
      toast.error("添加文件夹失败");
    }
  };

  // 删除文件夹
  const handleDeleteDirectory = async (id: number) => {
    try {
      // 先获取文件夹信息，以便后续清理
      const folderInfo = folderHierarchy
        .flatMap(folder => [
          folder,
          ...(folder.blacklist_children || [])
        ])
        .find(dir => dir.id === id);
      
      const folderPath = folderInfo?.path || "";
      const isBlacklist = folderInfo?.is_blacklist || false;
      
      // 第一步：使用队列版本的删除命令，这会将清理粗筛数据的任务加入队列
      const queueResult = await invoke("queue_delete_folder", {
        folder_id: id,
        folder_path: folderPath,
        is_blacklist: isBlacklist
      });
      
      console.log("删除文件夹队列结果:", queueResult);
      
      // 第二步：从数据库中删除文件夹记录
      const response = await fetch(`http://127.0.0.1:60315/directories/${id}`, {
        method: "DELETE"
      });
      
      if (response.ok) {
        // 清理粗筛数据的任务已加入Rust队列，不需要前端处理
        toast.success("文件夹删除成功");
        
        // 重新加载数据
        await loadConfigSummary();
        await loadFolderHierarchy();
        
        // 刷新监控配置
        try {
          await safeRefreshMonitoringConfig();
        } catch (configError) {
          console.warn("刷新监控配置失败:", configError);
        }
      } else {
        const errorData = await response.json();
        toast.error(`删除失败: ${errorData.message || "未知错误"}`);
      }
    } catch (error) {
      console.error("删除文件夹失败:", error);
      toast.error("删除文件夹失败");
    }
  };

  // 选择文件夹路径
  const handleSelectFolder = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "选择要监控的文件夹"
      });

      if (selected && typeof selected === "string") {
        setNewDirPath(selected);
        // 自动生成别名（文件夹名称）
        const folderName = await basename(selected);
        setNewDirAlias(folderName);
      }
    } catch (error) {
      console.error("选择文件夹失败:", error);
      toast.error("选择文件夹失败");
    }
  };

  // 添加Bundle扩展名
  const handleAddBundleExtension = async () => {
    if (!newBundleExtension.trim()) {
      toast.error("请输入扩展名");
      return;
    }

    try {
      const response = await fetch("http://127.0.0.1:60315/bundle-extensions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extension: newBundleExtension,
          description: newBundleDescription || null
        })
      });

      if (response.ok) {
        toast.success("Bundle扩展名添加成功");
        setIsBundleDialogOpen(false);
        setNewBundleExtension("");
        setNewBundleDescription("");
        await loadBundleExtensions();
        // 注意：Bundle扩展名的更改需要重启应用才能生效
        toast.info("Bundle扩展名已更新，重启应用后生效");
      } else {
        const errorData = await response.json();
        toast.error(`添加失败: ${errorData.message || "未知错误"}`);
      }
    } catch (error) {
      console.error("添加Bundle扩展名失败:", error);
      toast.error("添加Bundle扩展名失败");
    }
  };

  // 删除Bundle扩展名
  const handleDeleteBundleExtension = async (id: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/bundle-extensions/${id}`, {
        method: "DELETE"
      });

      if (response.ok) {
        toast.success("Bundle扩展名删除成功");
        await loadBundleExtensions();
        // 注意：Bundle扩展名的更改需要重启应用才能生效
        toast.info("Bundle扩展名已更新，重启应用后生效");
      } else {
        const errorData = await response.json();
        toast.error(`删除失败: ${errorData.message || "未知错误"}`);
      }
    } catch (error) {
      console.error("删除Bundle扩展名失败:", error);
      toast.error("删除Bundle扩展名失败");
    }
  };

  // 处理文件夹树选择器的路径选择
  const handleTreePathSelect = async (path: string) => {
    // 先检查路径是否已在黑名单中
    try {
      const response = await fetch("http://127.0.0.1:60315/folders/hierarchy", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const apiResponse = await response.json();
        if (apiResponse.status === "success" && apiResponse.data) {
          // 检查路径是否已在黑名单中
          const allFolders = apiResponse.data.flatMap((folder: any) => [
            folder,
            ...(folder.blacklist_children || [])
          ]);
          
          const pathExists = allFolders.some((dir: any) => dir.path === path && dir.is_blacklist);
          
          if (pathExists) {
            toast.error(`路径 "${path}" 已在黑名单中`);
            return;
          }
          
          // 路径没有问题，设置路径和默认别名
          setNewBlacklistPath(path);
          const folderName = path.split('/').pop() || path;
          setNewBlacklistAlias(folderName);
        } else {
          console.error("检查黑名单状态失败: 无效响应");
          setNewBlacklistPath(path);
          const folderName = path.split('/').pop() || path;
          setNewBlacklistAlias(folderName);
        }
      } else {
        console.error("检查黑名单状态失败: HTTP", response.status);
        setNewBlacklistPath(path);
        const folderName = path.split('/').pop() || path;
        setNewBlacklistAlias(folderName);
      }
    } catch (error) {
      console.error("检查黑名单状态失败:", error);
      // 出错时仍然设置路径，但记录错误
      setNewBlacklistPath(path);
      const folderName = path.split('/').pop() || path;
      setNewBlacklistAlias(folderName);
    }
  };

  // 确认添加黑名单文件夹（从文件夹树选择器）
  const handleConfirmTreeSelection = async () => {
    await handleAddBlacklistFolder();
  };

  // 添加黑名单子文件夹
  const handleAddBlacklistFolder = async () => {
    if (!selectedParentId) {
      toast.error("需要先选择父文件夹");
      return;
    }

    if (!newBlacklistPath.trim()) {
      toast.error("请选择黑名单文件夹路径");
      return;
    }

    // 验证选择的路径是否为父文件夹的子路径
    const parentFolder = folderHierarchy.find(f => f.id === selectedParentId);
    if (parentFolder && !newBlacklistPath.startsWith(parentFolder.path)) {
      toast.error(`选择的文件夹必须是 "${parentFolder.alias || parentFolder.path}" 的子文件夹`);
      return;
    }
    
    // 再次检查是否已在黑名单中（防止在对话框打开期间其他操作添加了相同路径）
    try {
      // 在当前层级结构中检查
      for (const folder of folderHierarchy) {
        // 检查黑名单子文件夹
        if (folder.blacklist_children) {
          for (const child of folder.blacklist_children) {
            if (child.path === newBlacklistPath || newBlacklistPath.startsWith(child.path + '/')) {
              toast.error("该路径已在黑名单中，不能重复添加");
              return;
            }
          }
        }
        
        // 检查已转为黑名单的父文件夹
        if (folder.is_blacklist && (folder.path === newBlacklistPath || newBlacklistPath.startsWith(folder.path + '/'))) {
          toast.error("该路径已在黑名单中，不能重复添加");
          return;
        }
      }
    } catch (error) {
      console.error("检查黑名单状态失败:", error);
      // 出错时继续执行，后端会再次验证
    }

    try {
      const response = await fetch(`http://127.0.0.1:60315/folders/blacklist/${selectedParentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: newBlacklistPath,
          alias: newBlacklistAlias || null
        })
      });

      if (response.ok) {
        toast.success("黑名单子文件夹添加成功");
        setIsBlacklistDialogOpen(false);
        setNewBlacklistPath("");
        setNewBlacklistAlias("");
        setSelectedParentId(null);
        // 重新加载数据
        await loadConfigSummary();
        await loadFolderHierarchy();
        
        // 使用队列机制处理配置变更，包括清理粗筛结果
        try {
          const queueResult = await invoke("queue_add_whitelist_folder", {
            parent_id: selectedParentId,
            folder_path: newBlacklistPath,
            folder_alias: newBlacklistAlias || null
          }) as { status: string; message: string };
          
          console.log("黑名单文件夹队列处理结果:", queueResult);
          
          if (queueResult.status === "executed") {
            toast.success("黑名单子文件夹处理完成");
          } else if (queueResult.status === "queued") {
            toast.info("黑名单子文件夹已加入处理队列，将在初始扫描完成后自动处理");
          }
          
          // 尝试安全刷新监控配置
          try {
            const refreshed = await safeRefreshMonitoringConfig();
            if (!refreshed) {
              toast.info("黑名单已添加，但初始扫描未完成，配置将在扫描完成后自动刷新");
            }
          } catch (configError) {
            console.warn("刷新监控配置失败:", configError);
          }
        } catch (invokeError) {
          console.error("队列处理失败:", invokeError);
          toast.error("黑名单子文件夹添加成功但队列处理失败，可能需要重启应用");
        }
      } else {
        const errorData = await response.json();
        toast.error(`添加失败: ${errorData.message || "未知错误"}`);
      }
    } catch (error) {
      console.error("添加黑名单子文件夹失败:", error);
      toast.error("添加黑名单子文件夹失败");
    }
  };

  // 获取文件夹类型标识
  const getFolderTypeIcon = (isCommon: boolean, isBlacklist: boolean) => {
    if (isBlacklist) {
      return <EyeOff className="h-4 w-4 text-red-500" />;
    }
    return isCommon ? (
      <Shield className="h-4 w-4 text-blue-500" />
    ) : (
      <Folder className="h-4 w-4 text-gray-500" />
    );
  };

  // 处理常见文件夹转换为黑名单的逻辑
  const handleToggleFolderToBlacklist = async (folderId: number, currentIsBlacklist: boolean) => {
    try {
      // 首先获取文件夹信息，以便在转为黑名单时清理粗筛数据
      const folderInfo = folderHierarchy
        .flatMap(folder => [
          folder,
          ...(folder.blacklist_children || [])
        ])
        .find(dir => dir.id === folderId);

      const folderPath = folderInfo?.path || "";
      const newIsBlacklist = !currentIsBlacklist;
      
      // 第一步：使用队列版本的切换命令，这会将清理粗筛数据的任务加入队列
      const queueResult = await invoke("queue_toggle_folder_status", {
        folder_id: folderId,
        folder_path: folderPath,
        is_blacklist: newIsBlacklist
      });
      
      console.log("切换文件夹状态队列结果:", queueResult);
      
      // 第二步：更新数据库中文件夹记录的状态
      const response = await fetch(`http://127.0.0.1:60315/directories/${folderId}/blacklist`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          is_blacklist: newIsBlacklist
        })
      });

      if (response.ok) {
        const apiResponse = await response.json();
        if (apiResponse.status === "success") {
          toast.success(`文件夹状态已更新为 ${newIsBlacklist ? '黑名单' : '白名单'}`);
          
          // 清理粗筛数据的任务已加入Rust队列，不需要前端处理
          if (newIsBlacklist) {
            toast.info("相关粗筛数据清理任务已加入队列");
          }
          
          // 重新加载文件夹层级结构
          await loadFolderHierarchy();
          
          // 检查配置队列状态
          await checkQueueStatus();
        } else {
          toast.error("更新文件夹状态失败");
          console.error("API返回错误:", apiResponse);
        }
      } else {
        toast.error("更新文件夹状态失败");
        console.error("HTTP请求失败:", response.status);
      }
    } catch (error) {
      console.error("切换文件夹状态失败:", error);
      toast.error("操作失败");
    }
  };

  // ===== 渲染函数 =====

  // 渲染层级文件夹结构 - 直接显示两级层次结构
  const renderFolderHierarchy = () => {
    // 只显示白名单文件夹及其黑名单子文件夹的层次结构
    const whitelistFolders = folderHierarchy.filter(folder => !folder.is_blacklist);

    if (whitelistFolders.length === 0) {
      return (
        <div className="text-center py-8 text-gray-500">
          没有配置文件夹
        </div>
      );
    }

    return (
      <div className="space-y-2">
        {whitelistFolders.map((folder: FolderHierarchy) => (
          <div key={folder.id} className="border rounded-lg">
            {/* 白名单父文件夹 */}
            <div className="p-4 bg-white">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {getFolderTypeIcon(folder.is_common_folder, folder.is_blacklist)}
                  <div>
                    <div className="font-medium">{folder.alias || folder.path}</div>
                    <div className="text-sm text-gray-500">{folder.path}</div>
                    <div className="text-xs text-gray-400">
                      {folder.is_common_folder ? "常见文件夹" : "自定义"}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {/* 添加黑名单子文件夹按钮 */}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setSelectedParentId(folder.id);
                      setIsBlacklistDialogOpen(true);
                    }}
                    title="添加黑名单子文件夹"
                  >
                    <PlusCircle className="h-4 w-4" />
                  </Button>
                  
                  {/* 常见文件夹转黑名单 */}
                  {folder.is_common_folder && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleToggleFolderToBlacklist(folder.id, folder.is_blacklist)}
                      title="转为黑名单"
                    >
                      <EyeOff className="h-4 w-4" />
                    </Button>
                  )}
                  
                  {/* 非常见文件夹可以删除 */}
                  {!folder.is_common_folder && (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button size="sm" variant="outline">
                          <MinusCircle className="h-4 w-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>确认删除</AlertDialogTitle>
                          <AlertDialogDescription>
                            确定要删除文件夹 "{folder.alias || folder.path}" 吗？
                            删除后将停止监控此文件夹。
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction 
                            onClick={() => handleDeleteDirectory(folder.id)}
                          >
                            确认删除
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </div>
              </div>
            </div>
            
            {/* 黑名单子文件夹 */}
            {folder.blacklist_children && folder.blacklist_children.length > 0 && (
              <div className="border-t bg-gray-50">
                {folder.blacklist_children
                  .filter(child => child.is_blacklist)
                  .map((child) => (
                  <div key={child.id} className="p-3 pl-8 border-b last:border-b-0 bg-red-50">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-4 h-px bg-gray-300 mr-2" />
                        <EyeOff className="h-4 w-4 text-red-500" />
                        <div>
                          <div className="font-medium text-sm">{child.alias || child.path}</div>
                          <div className="text-xs text-gray-500">{child.path}</div>
                          <div className="text-xs text-gray-400">黑名单子文件夹</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" variant="outline">
                              <MinusCircle className="h-4 w-4" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>确认删除</AlertDialogTitle>
                              <AlertDialogDescription>
                                确定要删除黑名单子文件夹 "{child.alias || child.path}" 吗？
                                删除后将重新监控此文件夹。
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>取消</AlertDialogCancel>
                              <AlertDialogAction 
                                onClick={() => handleDeleteDirectory(child.id)}
                              >
                                确认删除
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        
        {/* 显示转为黑名单的常见文件夹 */}
        {folderHierarchy.filter(f => f.is_blacklist && f.is_common_folder).map((folder: FolderHierarchy) => (
          <div key={`blacklist-${folder.id}`} className="border rounded-lg p-4 bg-red-50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <EyeOff className="h-4 w-4 text-red-500" />
                <div>
                  <div className="font-medium">{folder.alias || folder.path}</div>
                  <div className="text-sm text-gray-500">{folder.path}</div>
                  <div className="text-xs text-gray-400">已转为黑名单的常见文件夹</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleToggleFolderToBlacklist(folder.id, true)}
                  title="恢复为白名单"
                >
                  <Eye className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  // 渲染权限状态卡片
  const renderPermissionStatusCard = () => (
    <Card className="w-full mb-6">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          系统状态
        </CardTitle>
        <CardDescription>
          文件夹监控和后台处理状态
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* 配置变更队列状态 */}
          {queueStatus && (
            <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${
                    queueStatus.initial_scan_completed ? 'bg-green-500' : 'bg-yellow-500 animate-pulse'
                  }`} />
                  <span className="text-sm font-medium">
                    {queueStatus.initial_scan_completed ? '✅ 初始扫描已完成' : '⏳ 初始扫描进行中'}
                  </span>
                </div>
                {queueStatus.has_pending_changes && (
                  <div className="text-sm text-blue-600 font-medium">
                    📋 队列中有 {queueStatus.pending_changes_count} 个待处理变更
                  </div>
                )}
              </div>
              {!queueStatus.initial_scan_completed && (
                <div className="mt-2 text-xs text-blue-600">
                  扫描完成前的配置变更将自动排队处理
                </div>
              )}
            </div>
          )}
          
          {configSummary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {configSummary.monitored_dirs_count}
                </div>
                <div className="text-gray-500">监控文件夹</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-600">
                  {configSummary.blacklist_dirs_count}
                </div>
                <div className="text-gray-500">黑名单文件夹</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {configSummary.config_categories_count}
                </div>
                <div className="text-gray-500">文件分类</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-purple-600">
                  {bundleExtensions.length}
                </div>
                <div className="text-gray-500">Bundle扩展名</div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );

  // 渲染文件夹管理表格 - 支持层级显示
  const renderFolderManagementTable = () => {
    return (
      <Card className="w-full mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Folder className="h-5 w-5" />
                文件夹管理
              </CardTitle>
              <CardDescription>
                管理白名单和黑名单文件夹，控制监控范围。只能添加白名单文件夹，黑名单在白名单下添加。
              </CardDescription>
            </div>
            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
              <DialogTrigger asChild>
                <Button className="flex items-center gap-2">
                  <FolderPlus className="h-4 w-4" />
                  添加白名单文件夹
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>添加白名单文件夹</DialogTitle>
                  <DialogDescription>
                    添加新的监控文件夹，只能添加为白名单。黑名单需要在白名单文件夹下添加。
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="folder-path">文件夹路径</Label>
                    <div className="flex gap-2">
                      <Input
                        id="folder-path"
                        value={newDirPath}
                        onChange={(e) => setNewDirPath(e.target.value)}
                        placeholder="选择文件夹路径..."
                        readOnly
                      />
                      <Button onClick={handleSelectFolder} variant="outline">
                        选择
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="folder-alias">别名 (可选)</Label>
                    <Input
                      id="folder-alias"
                      value={newDirAlias}
                      onChange={(e) => setNewDirAlias(e.target.value)}
                      placeholder="为文件夹设置一个友好的名称..."
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                    取消
                  </Button>
                  <Button onClick={handleAddDirectory}>添加</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {/* 直接显示层级文件夹结构 */}
          {renderFolderHierarchy()}
        </CardContent>
      </Card>
    );
  };

  // 渲染Bundle扩展名管理区域
  const renderBundleExtensionsSection = () => (
    <Card className="w-full mb-6">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              macOS Bundle 扩展名管理
            </CardTitle>
            <CardDescription>
              macOS Bundle就是那些看起来是文件的文件夹，我们要跳过它们，提高扫描效率
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowBundleSection(!showBundleSection)}
            >
              {showBundleSection ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              {showBundleSection ? "隐藏" : "显示"}
            </Button>
            <Dialog open={isBundleDialogOpen} onOpenChange={setIsBundleDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <PlusCircle className="h-4 w-4 mr-2" />
                  添加扩展名
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>添加 Bundle 扩展名</DialogTitle>
                  <DialogDescription>
                    添加需要跳过扫描的 Bundle 扩展名（如 .app, .bundle）
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="extension">扩展名</Label>
                    <Input
                      id="extension"
                      value={newBundleExtension}
                      onChange={(e) => setNewBundleExtension(e.target.value)}
                      placeholder="例如：.app"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="description">描述 (可选)</Label>
                    <Input
                      id="description"
                      value={newBundleDescription}
                      onChange={(e) => setNewBundleDescription(e.target.value)}
                      placeholder="扩展名的用途描述..."
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setIsBundleDialogOpen(false)}>
                    取消
                  </Button>
                  <Button onClick={handleAddBundleExtension}>添加</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </CardHeader>
      {showBundleSection && (
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {bundleExtensions.map((ext) => (
              <Card key={ext.id} className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="font-medium">{ext.extension}</div>
                    <div className="text-sm text-gray-500">
                      {ext.description || "无描述"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${ext.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button size="sm" variant="outline">
                          <X className="h-4 w-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>确认删除</AlertDialogTitle>
                          <AlertDialogDescription>
                            确定要删除扩展名 "{ext.extension}" 吗？
                            删除后将重新扫描此类型的文件。
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction 
                            onClick={() => handleDeleteBundleExtension(ext.id)}
                          >
                            确认删除
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </Card>
            ))}
          </div>
          
          {bundleExtensions.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              还没有配置 Bundle 扩展名
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );

  // 主渲染
  if (loading) {
    return (
      <div className="w-full">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mb-4 mx-auto"></div>
            <p className="text-lg text-gray-600">加载授权配置中...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 w-full">
      <div className="mb-6 px-6">
        <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
          <Shield className="h-8 w-8" />
          系统授权管理
        </h1>
        <p className="text-gray-600 mt-2">
          管理文件夹访问权限，配置监控白名单和黑名单，优化扫描性能
        </p>
      </div>

      <div className="px-6 space-y-6">
        {renderPermissionStatusCard()}
        {renderFolderManagementTable()}
        {renderBundleExtensionsSection()}
      </div>
      
      {/* 黑名单子文件夹对话框 */}
      <Dialog open={isBlacklistDialogOpen} onOpenChange={setIsBlacklistDialogOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>添加黑名单子文件夹</DialogTitle>
            <DialogDescription>
              在白名单文件夹下选择不需要监控的黑名单子文件夹
            </DialogDescription>
          </DialogHeader>
          
          {selectedParentId ? (
            <FolderTreeSelector
              rootPath={folderHierarchy.find(f => f.id === selectedParentId)?.path || ""}
              rootAlias={folderHierarchy.find(f => f.id === selectedParentId)?.alias || undefined}
              selectedPath={newBlacklistPath}
              onPathSelect={handleTreePathSelect}
              onConfirm={handleConfirmTreeSelection}
              onCancel={() => {
                setIsBlacklistDialogOpen(false);
                setSelectedParentId(null);
                setNewBlacklistPath("");
                setNewBlacklistAlias("");
              }}
            />
          ) : (
            <div className="py-4">
              <p className="text-gray-500">请先选择父文件夹</p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default SettingsAuthorization;
