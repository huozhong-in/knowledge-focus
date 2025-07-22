import React, { useState, useEffect } from 'react';
import { ChevronRight, ChevronDown, Folder, FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetch } from '@tauri-apps/plugin-http';

interface FolderNode {
  name: string;
  path: string;
  children?: FolderNode[];
  expanded?: boolean;
  loading?: boolean;
  isBlacklisted?: boolean; // 标识该文件夹是否已在黑名单中
}

interface FolderTreeSelectorProps {
  rootPath: string;
  rootAlias?: string;
  selectedPath: string | null;
  onPathSelect: (path: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function FolderTreeSelector({
  rootPath,
  rootAlias,
  selectedPath,
  onPathSelect,
  onConfirm,
  onCancel
}: FolderTreeSelectorProps) {
  const [rootNode, setRootNode] = useState<FolderNode>({
    name: rootAlias || rootPath.split('/').pop() || rootPath,
    path: rootPath,
    children: [],
    expanded: true,
    loading: true
  });

  const [bundlePatterns, setBundlePatterns] = useState<string[]>([]);
  // const [bundlePatternsLoaded, setBundlePatternsLoaded] = useState<boolean>(false);

  // 加载bundle扩展名配置
  const loadBundlePatterns = async (): Promise<string[]> => {
    try {
      const response = await fetch("http://127.0.0.1:60315/config/all", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const configData = await response.json();
        // 从file_filter_rules中提取bundle相关的配置
        const bundlePatterns = configData.file_filter_rules
          ?.filter((rule: any) => rule.rule_type === "os_bundle" && rule.enabled)
          ?.map((rule: any) => rule.pattern) || [];
        
        console.log('已加载Bundle过滤模式:', bundlePatterns);
        return bundlePatterns;
      }
    } catch (error) {
      console.error("加载Bundle配置失败:", error);
    }
    return [];
  };

  // 检查文件夹是否为bundle类型
  const isBundleFolder = (folderName: string, patterns: string[]): boolean => {
    // 确保模式数组有效
    if (!patterns || patterns.length === 0) {
      console.log('Bundle配置为空或未完成加载，跳过过滤:', folderName);
      return false;
    }
    
    // 特定的系统bundle文件夹检查（无需正则表达式的快速检查）
    if (folderName.endsWith('.app') || 
        folderName.endsWith('.bundle') || 
        folderName.endsWith('.framework')) {
      console.log(`文件夹 "${folderName}" 是典型的bundle文件夹`);
      return true;
    }
    
    const isBundle = patterns.some((pattern: string) => {
      if (!pattern) return false;
      
      try {
        // 构造正则表达式并测试文件夹名
        const regex = new RegExp(pattern, 'i');
        const matches = regex.test(folderName);
        if (matches) {
          console.log(`文件夹 "${folderName}" 匹配bundle模式 "${pattern}"`);
        }
        return matches;
      } catch (error) {
        console.warn("无效的正则表达式:", pattern, error);
        return false;
      }
    });
    
    return isBundle;
  };

  // 检查路径是否已经在黑名单中
  const isPathInBlacklist = async (folderPath: string): Promise<boolean> => {
    try {
      // 调用API检查该路径是否已经存在于黑名单中
      const response = await fetch("http://127.0.0.1:60315/folders/hierarchy", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const apiResponse = await response.json();
        if (apiResponse.status === "success" && apiResponse.data) {
          // 遍历所有白名单文件夹
          for (const folder of apiResponse.data) {
            // 检查黑名单子文件夹
            if (folder.blacklist_children && folder.blacklist_children.length > 0) {
              for (const blacklistChild of folder.blacklist_children) {
                if (folderPath === blacklistChild.path || folderPath.startsWith(blacklistChild.path + '/')) {
                  console.log(`路径 "${folderPath}" 已存在于黑名单中或是黑名单的子文件夹`);
                  return true;
                }
              }
            }
            // 检查已转为黑名单的常见文件夹
            if (folder.is_blacklist && folder.is_common_folder) {
              if (folderPath === folder.path || folderPath.startsWith(folder.path + '/')) {
                console.log(`路径 "${folderPath}" 已存在于黑名单中或是黑名单的子文件夹`);
                return true;
              }
            }
          }
        }
      }
      return false;
    } catch (error) {
      console.error('检查黑名单状态失败:', error);
      return false;
    }
  };

  // 加载文件夹子目录
  const loadFolderChildren = async (folderPath: string, patterns: string[]): Promise<FolderNode[]> => {
    try {
      // 调用 Tauri API 读取文件夹内容
      const { invoke } = await import('@tauri-apps/api/core');
      const children = await invoke('read_directory', { path: folderPath }) as Array<{
        name: string;
        path: string;
        is_directory: boolean;
      }>;
      
      // 获取目录中的文件夹
      let filteredFolders = children.filter(child => child.is_directory);
      
      // 如果模式数组有效，执行Bundle文件夹过滤
      if (patterns && patterns.length > 0) {
        console.log(`使用 ${patterns.length} 条Bundle规则过滤 ${folderPath} 内的文件夹`);
        filteredFolders = filteredFolders.filter(child => {
          const isBundle = isBundleFolder(child.name, patterns);
          if (isBundle) {
            console.log(`过滤掉bundle文件夹: ${child.name}`);
          }
          return !isBundle; // 过滤掉bundle文件夹
        });
      } else {
        console.log(`Bundle模式尚未加载完成，仅执行基本过滤: ${folderPath}`);
        // 即使没有模式，也过滤基本的bundle类型
        filteredFolders = filteredFolders.filter(child => {
          const isCommonBundle = child.name.endsWith('.app') || 
                                child.name.endsWith('.bundle') || 
                                child.name.endsWith('.framework');
          if (isCommonBundle) {
            console.log(`过滤掉常见bundle类型: ${child.name}`);
          }
          return !isCommonBundle;
        });
      }
      
      // 创建文件夹节点的基本数组
      const folderNodes = filteredFolders.map(child => ({
        name: child.name,
        path: child.path,
        children: [],
        expanded: false,
        loading: false,
        isBlacklisted: false // 添加黑名单标志
      }));
      
      // 检查和标记黑名单状态（异步处理，不阻塞返回）
      folderNodes.forEach(async (node) => {
        const blacklisted = await isPathInBlacklist(node.path);
        if (blacklisted) {
          console.log(`标记为黑名单: ${node.path}`);
          node.isBlacklisted = true;
        }
      });
      
      return folderNodes.sort((a, b) => a.name.localeCompare(b.name));
    } catch (error) {
      console.error('加载文件夹失败:', error);
      return [];
    }
  };

  // 初始化根节点和bundle配置
  useEffect(() => {
    const initializeComponent = async () => {
      // 先加载bundle扩展名配置
      const patterns = await loadBundlePatterns();
      setBundlePatterns(patterns);
      // setBundlePatternsLoaded(true);
      console.log('Bundle模式加载完成，共 ' + patterns.length + ' 条规则');
      
      // 然后加载根文件夹的子目录，直接传入加载的模式
      const children = await loadFolderChildren(rootPath, patterns);
      setRootNode(prev => ({
        ...prev,
        children,
        loading: false
      }));
    };
    
    initializeComponent();
  }, [rootPath]);

  // 切换文件夹展开/收起
  const toggleFolder = async (updatePath: string) => {
    const updateNode = (current: FolderNode): FolderNode => {
      if (current.path === updatePath) {
        if (!current.expanded && (!current.children || current.children.length === 0)) {
          // 需要加载子文件夹
          return {
            ...current,
            expanded: true,
            loading: true
          };
        } else {
          return {
            ...current,
            expanded: !current.expanded
          };
        }
      }
      
      if (current.children) {
        return {
          ...current,
          children: current.children.map(updateNode)
        };
      }
      
      return current;
    };

    const newRootNode = updateNode(rootNode);
    setRootNode(newRootNode);

    // 如果需要加载子文件夹
    const targetNode = findNodeByPath(newRootNode, updatePath);
    if (targetNode && targetNode.loading) {
      const children = await loadFolderChildren(updatePath, bundlePatterns);
      
      const updateWithChildren = (current: FolderNode): FolderNode => {
        if (current.path === updatePath) {
          return {
            ...current,
            children,
            loading: false
          };
        }
        
        if (current.children) {
          return {
            ...current,
            children: current.children.map(updateWithChildren)
          };
        }
        
        return current;
      };

      setRootNode(updateWithChildren(newRootNode));
    }
  };

  // 根据路径查找节点
  const findNodeByPath = (node: FolderNode, targetPath: string): FolderNode | null => {
    if (node.path === targetPath) {
      return node;
    }
    
    if (node.children) {
      for (const child of node.children) {
        const found = findNodeByPath(child, targetPath);
        if (found) return found;
      }
    }
    
    return null;
  };

  // 渲染文件夹节点
  const renderNode = (node: FolderNode, depth: number = 0): React.ReactNode => {
    const isSelected = selectedPath === node.path;
    const hasChildren = node.children && node.children.length > 0;
    const canExpand = hasChildren || node.loading;
    const isBlacklisted = node.isBlacklisted === true;

    return (
      <div key={node.path}>
        <div
          className={`flex items-center py-1 px-2 hover:bg-gray-100 rounded cursor-pointer ${
            isSelected ? 'bg-blue-100 border border-blue-300' : ''
          } ${isBlacklisted ? 'opacity-50 bg-red-50' : ''}`}
          style={{ paddingLeft: `${depth * 20 + 8}px` }}
          onClick={() => {
            // 如果节点已经在黑名单中，就不能再选择它
            if (!isBlacklisted) {
              onPathSelect(node.path);
            }
          }}
          title={isBlacklisted ? '此文件夹已在黑名单中' : ''}
        >
          <div className="flex items-center flex-1">
            {canExpand ? (
              <Button
                variant="ghost"
                size="sm"
                className="p-0 h-6 w-6 mr-1"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleFolder(node.path);
                }}
                disabled={isBlacklisted}
              >
                {node.loading ? (
                  <div className="animate-spin rounded-full h-3 w-3 border-t border-gray-400" />
                ) : node.expanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </Button>
            ) : (
              <div className="w-7" />
            )}
            
            {node.expanded ? (
              <FolderOpen className={`h-4 w-4 mr-2 ${isBlacklisted ? 'text-red-400' : 'text-blue-500'}`} />
            ) : (
              <Folder className={`h-4 w-4 mr-2 ${isBlacklisted ? 'text-red-400' : 'text-gray-500'}`} />
            )}
            
            <span className={`text-sm ${isBlacklisted ? 'line-through text-red-500' : ''}`}>{node.name}</span>
            {isBlacklisted && <span className="ml-2 text-xs text-red-500">(已在黑名单)</span>}
          </div>
        </div>
        
        {node.expanded && node.children && (
          <div>
            {node.children.map(child => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  // 查找当前选择的节点
  const selectedNode = selectedPath ? findNodeByPath(rootNode, selectedPath) : null;
  const isSelectedPathBlacklisted = selectedNode?.isBlacklisted === true;
  
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-medium mb-2">
          选择要添加到黑名单的子文件夹：
        </h4>
        <div className="text-xs text-gray-500 mb-1">
          父文件夹：{rootAlias || rootPath}
        </div>
        <div className="text-xs text-amber-600 mb-1">
          注意：Bundle类型文件夹（如.app等）已自动过滤，不会显示在列表中
        </div>
        <div className="text-xs text-red-500 mb-3">
          已在黑名单中的文件夹会被标记为红色且不可选择
        </div>
      </div>
      
      <div className="h-64 border rounded-md p-2 overflow-y-auto">
        {renderNode(rootNode)}
      </div>
      
      {selectedPath && (
        <div className={`text-sm ${isSelectedPathBlacklisted ? 'text-red-600' : 'text-gray-600'}`}>
          <strong>已选择:</strong> {selectedPath}
          {isSelectedPathBlacklisted && <span className="ml-2 text-red-500 font-medium">(已在黑名单中，不能重复添加)</span>}
        </div>
      )}
      
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          取消
        </Button>
        <Button 
          onClick={onConfirm}
          disabled={!selectedPath || selectedPath === rootPath || isSelectedPathBlacklisted}
        >
          确认添加到黑名单
        </Button>
      </div>
    </div>
  );
}
