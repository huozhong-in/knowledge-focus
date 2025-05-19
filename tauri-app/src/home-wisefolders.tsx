import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer"
import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { FileIcon, FolderIcon, MoreHorizontal, ExternalLink, EyeIcon, FileSearch } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { openPath } from "@tauri-apps/plugin-opener";

// 定义洞察类型对应的展示名称
const insightTypeLabels: Record<string, string> = {
  "file_activity": "文件活动",
  "project_update": "项目更新",
  "cleanup": "清理建议",
  "content_highlight": "内容亮点",
  "usage_pattern": "使用模式",
  "custom": "自定义洞察"
};

// 定义优先级对应的样式和名称
const priorityStyles: Record<string, {color: string, label: string}> = {
  "low": { color: "bg-gray-200 text-gray-800", label: "低" },
  "medium": { color: "bg-blue-200 text-blue-800", label: "中" },
  "high": { color: "bg-orange-200 text-orange-800", label: "高" },
  "critical": { color: "bg-red-200 text-red-800", label: "紧急" },
};

// 洞察数据接口定义
interface Insight {
  id: number;
  title: string;
  description: string;
  insight_type: string;
  priority: string;
  related_files: string[];
  score?: number;
  is_read: boolean;
  created_at: string;
}

// 文件项接口定义
interface FileItem {
  path: string;
  name: string;
  extension: string | null;
  size: number;
  modified: string;
}

// 文件操作菜单
function FileActionMenu({ file }: { file: FileItem }) {
  const openContainingFolder = async () => {
    try {
      // 获取文件所在的目录
      const folderPath = file.path.substring(0, file.path.lastIndexOf('/'));
      await openPath(folderPath);
    } catch (error) {
      console.error("打开文件夹失败:", error);
    }
  };

  const openFileDirectly = async () => {
    try {
      await openPath(file.path);
    } catch (error) {
      console.error("打开文件失败:", error);
    }
  };

  const copyFilePath = () => {
    navigator.clipboard.writeText(file.path)
      .then(() => {
        console.log("文件路径已复制");
      })
      .catch(err => {
        console.error("复制失败:", err);
      });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>文件操作</DropdownMenuLabel>
        <DropdownMenuItem onClick={openFileDirectly}>
          <FileSearch className="mr-2 h-4 w-4" /> 打开文件
        </DropdownMenuItem>
        <DropdownMenuItem onClick={openContainingFolder}>
          <FolderIcon className="mr-2 h-4 w-4" /> 打开所在文件夹
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={copyFilePath}>
          <ExternalLink className="mr-2 h-4 w-4" /> 复制文件路径
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}


function HomeWiseFolders() {
  const [insights, setInsights] = useState<Insight[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeInsightId, setActiveInsightId] = useState<number | null>(null);
    const [relatedFiles, setRelatedFiles] = useState<FileItem[]>([]);
  
    // 模拟获取洞察数据
    useEffect(() => {
      // 实际项目中，这里应该调用API获取真实数据
      const fetchInsights = async () => {
        try {
          // 调用Tauri API获取洞察数据
          // const data = await invoke("get_insights");
          // setInsights(data as Insight[]);
  
          // 临时使用模拟数据
          setInsights(mockInsights);
          if (mockInsights.length > 0) {
            setActiveInsightId(mockInsights[0].id);
            setRelatedFiles(getRelatedFilesByInsightId(mockInsights[0].id));
          }
        } catch (error) {
          console.error("获取洞察数据失败:", error);
        } finally {
          setLoading(false);
        }
      };
  
      fetchInsights();
    }, []);
  
    // 处理洞察项点击事件
    const handleInsightClick = (insight: Insight) => {
      setActiveInsightId(insight.id);
      // 在实际项目中，这里应该调用API获取关联的文件数据
      setRelatedFiles(getRelatedFilesByInsightId(insight.id));
    };
  
    // 根据洞察ID获取关联文件（模拟函数）
    const getRelatedFilesByInsightId = (insightId: number): FileItem[] => {
      const insight = mockInsights.find(item => item.id === insightId);
      if (!insight || !insight.related_files) return [];
      
      // 模拟根据文件路径生成文件项
      return insight.related_files.map(filePath => {
        const pathParts = filePath.split('/');
        const fileName = pathParts[pathParts.length - 1];
        const extensionMatch = fileName.match(/\.([^.]+)$/);
        
        return {
          path: filePath,
          name: fileName,
          extension: extensionMatch ? extensionMatch[1] : null,
          size: Math.floor(Math.random() * 1000000), // 随机文件大小
          modified: new Date().toISOString().split('T')[0], // 当前日期作为修改日期
        };
      });
    };
  
    // 格式化文件大小
    const formatFileSize = (size: number): string => {
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let unitIndex = 0;
      let formattedSize = size;
  
      while (formattedSize >= 1024 && unitIndex < units.length - 1) {
        formattedSize /= 1024;
        unitIndex++;
      }
  
      return `${formattedSize.toFixed(1)} ${units[unitIndex]}`;
    };
  
    // 获取文件图标（简单版）
    const getFileIcon = (extension: string | null) => {
      return <FileIcon className="h-4 w-4 text-gray-500" />;
    };
  
    // 渲染洞察列表项
    const renderInsightItem = (insight: Insight) => {
      const priorityStyle = priorityStyles[insight.priority] || priorityStyles.medium;
      
      return (
        <Card 
          key={insight.id} 
          className={`mb-4 cursor-pointer hover:border-blue-300 transition-all ${activeInsightId === insight.id ? 'border-blue-500 shadow-md' : ''}`}
          onClick={() => handleInsightClick(insight)}
        >
          <CardHeader className="pb-2">
            <div className="flex justify-between items-center">
              <Badge className={`${priorityStyle.color}`}>{priorityStyle.label}</Badge>
              <Badge variant="outline">{insightTypeLabels[insight.insight_type] || insight.insight_type}</Badge>
            </div>
            <CardTitle className="text-lg font-semibold">{insight.title}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-600">{insight.description}</p>
            <p className="text-xs text-gray-500 mt-2">相关文件: {insight.related_files?.length || 0} 个</p>
          </CardContent>
          <CardFooter className="pt-0 text-xs text-gray-400">
            创建于 {insight.created_at}
          </CardFooter>
        </Card>
      );
    };
  
    return (
      <div className="container mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold mb-6">智能视图</h1>
        <p className="text-gray-600 mb-6">
          智能视图通过分析文件关系和使用模式，提供不同于传统文件夹组织的文件聚类方式，而不改变硬盘上的实际文件位置。
        </p>
  
        <Tabs defaultValue="insights" className="w-full">
          <TabsList className="mb-4">
            <TabsTrigger value="insights">洞察视图</TabsTrigger>
            <TabsTrigger value="projects">项目视图</TabsTrigger>
            <TabsTrigger value="categories">分类视图</TabsTrigger>
            <TabsTrigger value="timeline">时间线视图</TabsTrigger>
          </TabsList>
          
          <TabsContent value="insights">
            <div className="flex flex-col lg:flex-row gap-6">
              {/* 左侧洞察列表 */}
              <div className="lg:w-1/3 space-y-4">
                <h2 className="text-xl font-semibold mb-4">洞察列表</h2>
                {loading ? (
                  <p>加载中...</p>
                ) : insights.length > 0 ? (
                  insights.map(renderInsightItem)
                ) : (
                  <p>暂无洞察</p>
                )}
              </div>
  
              {/* 右侧文件列表 */}
              <div className="lg:w-2/3 border rounded-lg p-4">
                <h2 className="text-xl font-semibold mb-4">
                  {activeInsightId ? (
                    <>相关文件 <span className="text-gray-500 font-normal">({relatedFiles.length}个)</span></>
                  ) : (
                    '请选择一个洞察查看相关文件'
                  )}
                </h2>
                
                {activeInsightId && (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[300px]">文件名</TableHead>
                          <TableHead>类型</TableHead>
                          <TableHead>大小</TableHead>
                          <TableHead>修改日期</TableHead>
                          <TableHead className="text-right">操作</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {relatedFiles.length > 0 ? (
                          relatedFiles.map((file, index) => (
                            <TableRow key={index}>
                              <TableCell className="font-medium">
                                <div className="flex items-center gap-2">
                                  {getFileIcon(file.extension)}
                                  <span className="truncate max-w-[240px]" title={file.name}>{file.name}</span>
                                </div>
                              </TableCell>
                              <TableCell>{file.extension || 'Unknown'}</TableCell>
                              <TableCell>{formatFileSize(file.size)}</TableCell>
                              <TableCell>{file.modified}</TableCell>
                              <TableCell className="text-right">
                                <FileActionMenu file={file} />
                              </TableCell>
                            </TableRow>
                          ))
                        ) : (
                          <TableRow>
                            <TableCell colSpan={5} className="text-center">暂无相关文件</TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </div>
          </TabsContent>
          
          <TabsContent value="projects">
            <div className="p-4 border rounded-lg">
              <p>项目视图内容（待开发）</p>
            </div>
          </TabsContent>
          
          <TabsContent value="categories">
            <div className="p-4 border rounded-lg">
              <p>分类视图内容（待开发）</p>
            </div>
          </TabsContent>
          
          <TabsContent value="timeline">
            <div className="p-4 border rounded-lg">
              <p>时间线视图内容（待开发）</p>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    );
  }

// 模拟的洞察数据
const mockInsights: Insight[] = [
  {
    id: 1,
    title: "最近项目动态",
    description: "[项目A] 上周有 5 个文档更新",
    insight_type: "project_update",
    priority: "medium",
    related_files: [
      "/Users/dio/项目A/文档1.docx", 
      "/Users/dio/项目A/文档2.docx", 
      "/Users/dio/项目A/笔记.md",
      "/Users/dio/项目A/数据分析.xlsx",
      "/Users/dio/项目A/报告.pdf"
    ],
    is_read: false,
    created_at: "2025-05-10"
  },
  {
    id: 2,
    title: "本周截图盘点",
    description: "新增 15 张来自 CleanShot 的截图",
    insight_type: "file_activity",
    priority: "low",
    related_files: [
      "/Users/dio/Screenshots/CleanShot 2025-05-11.png",
      "/Users/dio/Screenshots/CleanShot 2025-05-12.png",
      "/Users/dio/Screenshots/CleanShot 2025-05-13.png",
      "/Users/dio/Desktop/CleanShot 2025-05-14.png",
      "/Users/dio/Desktop/CleanShot 2025-05-15.png"
    ],
    is_read: false,
    created_at: "2025-05-14"
  },
  {
    id: 3,
    title: "文件待办提醒",
    description: "发现 3 份文件名含'草稿'的文件超过一个月未修改",
    insight_type: "cleanup",
    priority: "high",
    related_files: [
      "/Users/dio/Documents/报告草稿.docx",
      "/Users/dio/Projects/proposal草稿.md",
      "/Users/dio/Desktop/设计方案草稿.pptx"
    ],
    is_read: false,
    created_at: "2025-05-12"
  },
  {
    id: 4,
    title: "清理建议",
    description: "检测到 4 组文件可能为重复或旧版本",
    insight_type: "cleanup",
    priority: "medium",
    related_files: [
      "/Users/dio/Documents/报告v1.docx",
      "/Users/dio/Documents/报告v2.docx",
      "/Users/dio/Documents/报告final.docx",
      "/Users/dio/Documents/报告final-revised.docx"
    ],
    is_read: false,
    created_at: "2025-05-11"
  },
  {
    id: 5,
    title: "常用应用文件",
    description: "本月收到 20 个来自'微信下载'的文件",
    insight_type: "usage_pattern",
    priority: "low",
    related_files: [
      "/Users/dio/Downloads/微信文件/文档1.pdf",
      "/Users/dio/Downloads/微信文件/照片2.jpg",
      "/Users/dio/Downloads/微信文件/音频3.mp3"
    ],
    is_read: false,
    created_at: "2025-05-13"
  },
];
  
export default HomeWiseFolders;