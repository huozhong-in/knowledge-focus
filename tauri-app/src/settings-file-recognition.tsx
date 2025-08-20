import { useState, useEffect } from "react";
import { fetch } from '@tauri-apps/plugin-http';
import { toast } from "sonner";
import { 
  FileText, 
  Settings, 
  Filter, 
  Package,
  Plus,
  Trash2,
  Edit
} from "lucide-react";

// UI组件
import { 
  Tabs, 
  TabsContent, 
  TabsList, 
  TabsTrigger 
} from "@/components/ui/tabs";
import { 
  Card, 
  CardContent, 
  CardDescription, 
  CardHeader, 
  CardTitle 
} from "@/components/ui/card";
import { 
  Button 
} from "@/components/ui/button";
import { 
  Input 
} from "@/components/ui/input";
import { 
  Label 
} from "@/components/ui/label";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle
} from "@/components/ui/dialog";
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { 
  Badge 
} from "@/components/ui/badge";
import { 
  Switch 
} from "@/components/ui/switch";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// ========== 类型定义 ==========

interface FileCategory {
  id: number;
  name: string;
  description: string | null;
  icon: string | null;
  extension_count: number;
  created_at: string;
  updated_at: string;
}

interface ExtensionMapping {
  id: number;
  extension: string;
  category_id: number;
  category_name: string;
  description: string | null;
  priority: string;
  created_at: string;
  updated_at: string;
}

interface FilterRule {
  id: number;
  name: string;
  description: string | null;
  rule_type: string;
  category_id: number | null;
  priority: string;
  action: string;
  enabled: boolean;
  is_system: boolean;
  pattern: string;
  pattern_type: string;
  extra_data: any;
  created_at: string;
  updated_at: string;
}

interface BundleExtension {
  id: number;
  extension: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ========== 主组件 ==========

export default function SettingsFileRecognition() {
  // ========== 状态管理 ==========
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<string>("categories");

  // 文件分类状态
  const [categories, setCategories] = useState<FileCategory[]>([]);
  const [categoryDialog, setCategoryDialog] = useState({ open: false, mode: 'add' as 'add' | 'edit', editId: null as number | null });
  const [categoryForm, setCategoryForm] = useState({ name: '', description: '', icon: '' });

  // 扩展名映射状态
  const [extensionMappings, setExtensionMappings] = useState<ExtensionMapping[]>([]);
  const [extensionDialog, setExtensionDialog] = useState({ open: false, mode: 'add' as 'add' | 'edit', editId: null as number | null });
  const [extensionForm, setExtensionForm] = useState({ 
    extension: '', 
    category_id: 0, 
    description: '', 
    priority: 'medium' 
  });

  // 过滤规则状态
  const [filterRules, setFilterRules] = useState<FilterRule[]>([]);
  const [filterDialog, setFilterDialog] = useState({ open: false, mode: 'add' as 'add' | 'edit', editId: null as number | null });
  const [filterForm, setFilterForm] = useState({
    name: '',
    description: '',
    rule_type: 'extension',
    pattern: '',
    action: 'exclude',
    priority: 'medium',
    pattern_type: 'regex',
    category_id: 0
  });

  // Bundle扩展名状态
  const [bundleExtensions, setBundleExtensions] = useState<BundleExtension[]>([]);
  const [bundleDialog, setBundleDialog] = useState({ open: false, mode: 'add' as 'add' | 'edit', editId: null as number | null });
  const [bundleForm, setBundleForm] = useState({ extension: '', description: '' });

  // ========== 数据加载函数 ==========

  // 加载文件分类
  const loadCategories = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60315/file-categories", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          setCategories(result.data);
        }
      } else {
        console.error("加载文件分类失败:", response.status);
        toast.error("加载文件分类失败");
      }
    } catch (error) {
      console.error("加载文件分类失败:", error);
      toast.error("加载文件分类失败");
    }
  };

  // 加载扩展名映射
  const loadExtensionMappings = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60315/extension-mappings", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          setExtensionMappings(result.data);
        }
      } else {
        console.error("加载扩展名映射失败:", response.status);
        toast.error("加载扩展名映射失败");
      }
    } catch (error) {
      console.error("加载扩展名映射失败:", error);
      toast.error("加载扩展名映射失败");
    }
  };

  // 加载过滤规则
  const loadFilterRules = async () => {
    try {
      const response = await fetch("http://127.0.0.1:60315/filter-rules", {
        method: "GET",
        headers: { "Content-Type": "application/json" }
      });
      
      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          setFilterRules(result.data);
        }
      } else {
        console.error("加载过滤规则失败:", response.status);
        toast.error("加载过滤规则失败");
      }
    } catch (error) {
      console.error("加载过滤规则失败:", error);
      toast.error("加载过滤规则失败");
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
        const result = await response.json();
        if (result.status === "success") {
          setBundleExtensions(result.data);
        }
      } else {
        console.error("加载Bundle扩展名失败:", response.status);
        toast.error("加载Bundle扩展名失败");
      }
    } catch (error) {
      console.error("加载Bundle扩展名失败:", error);
      toast.error("加载Bundle扩展名失败");
    }
  };

  // 初始化数据加载
  useEffect(() => {
    const initData = async () => {
      setLoading(true);
      try {
        await Promise.all([
          loadCategories(),
          loadExtensionMappings(),
          loadFilterRules(),
          loadBundleExtensions()
        ]);
      } catch (error) {
        console.error("初始化数据失败:", error);
        toast.error("初始化数据失败");
      } finally {
        setLoading(false);
      }
    };

    initData();
  }, []);

  // ========== 文件分类事件处理函数 ==========

  const handleCategorySubmit = async () => {
    if (!categoryForm.name.trim()) {
      toast.error("分类名称不能为空");
      return;
    }

    try {
      const url = categoryDialog.mode === 'add' 
        ? "http://127.0.0.1:60315/file-categories"
        : `http://127.0.0.1:60315/file-categories/${categoryDialog.editId}`;
      
      const method = categoryDialog.mode === 'add' ? "POST" : "PUT";
      
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: categoryForm.name.trim(),
          description: categoryForm.description.trim() || null,
          icon: categoryForm.icon.trim() || null
        })
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success(categoryDialog.mode === 'add' ? "分类添加成功" : "分类更新成功");
          setCategoryDialog({ open: false, mode: 'add', editId: null });
          setCategoryForm({ name: '', description: '', icon: '' });
          await loadCategories();
        } else {
          toast.error(result.message || "操作失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "操作失败");
      }
    } catch (error) {
      console.error("分类操作失败:", error);
      toast.error("操作失败");
    }
  };

  const handleCategoryDelete = async (categoryId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/file-categories/${categoryId}?force=true`, {
        method: "DELETE"
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success("分类删除成功");
          await loadCategories();
          await loadExtensionMappings(); // 重新加载映射以更新显示
        } else {
          toast.error(result.message || "删除失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "删除失败");
      }
    } catch (error) {
      console.error("删除分类失败:", error);
      toast.error("删除失败");
    }
  };

  // ========== 扩展名映射事件处理函数 ==========

  const handleExtensionSubmit = async () => {
    if (!extensionForm.extension.trim()) {
      toast.error("扩展名不能为空");
      return;
    }

    if (!extensionForm.category_id) {
      toast.error("请选择分类");
      return;
    }

    try {
      const url = extensionDialog.mode === 'add' 
        ? "http://127.0.0.1:60315/extension-mappings"
        : `http://127.0.0.1:60315/extension-mappings/${extensionDialog.editId}`;
      
      const method = extensionDialog.mode === 'add' ? "POST" : "PUT";
      
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extension: extensionForm.extension.trim(),
          category_id: extensionForm.category_id,
          description: extensionForm.description.trim() || null,
          priority: extensionForm.priority
        })
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success(extensionDialog.mode === 'add' ? "扩展名映射添加成功" : "扩展名映射更新成功");
          setExtensionDialog({ open: false, mode: 'add', editId: null });
          setExtensionForm({ extension: '', category_id: 0, description: '', priority: 'medium' });
          await loadExtensionMappings();
          await loadCategories(); // 重新加载分类以更新计数
        } else {
          toast.error(result.message || "操作失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "操作失败");
      }
    } catch (error) {
      console.error("扩展名映射操作失败:", error);
      toast.error("操作失败");
    }
  };

  const handleExtensionDelete = async (mappingId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/extension-mappings/${mappingId}`, {
        method: "DELETE"
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success("扩展名映射删除成功");
          await loadExtensionMappings();
          await loadCategories(); // 重新加载分类以更新计数
        } else {
          toast.error(result.message || "删除失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "删除失败");
      }
    } catch (error) {
      console.error("删除扩展名映射失败:", error);
      toast.error("删除失败");
    }
  };

  // ========== 过滤规则事件处理函数 ==========

  const handleFilterRuleToggle = async (ruleId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/filter-rules/${ruleId}/toggle`, {
        method: "PATCH"
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success(result.message);
          await loadFilterRules();
        } else {
          toast.error(result.message || "切换失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "切换失败");
      }
    } catch (error) {
      console.error("切换过滤规则状态失败:", error);
      toast.error("切换失败");
    }
  };

  const handleFilterSubmit = async () => {
    if (!filterForm.name.trim()) {
      toast.error("规则名称不能为空");
      return;
    }

    if (!filterForm.pattern.trim()) {
      toast.error("匹配模式不能为空");
      return;
    }

    try {
      const url = filterDialog.mode === 'add' 
        ? "http://127.0.0.1:60315/filter-rules"
        : `http://127.0.0.1:60315/filter-rules/${filterDialog.editId}`;
      
      const method = filterDialog.mode === 'add' ? "POST" : "PUT";
      
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: filterForm.name.trim(),
          description: filterForm.description.trim() || null,
          rule_type: filterForm.rule_type,
          pattern: filterForm.pattern.trim(),
          action: filterForm.action,
          priority: filterForm.priority,
          pattern_type: filterForm.pattern_type,
          category_id: filterForm.category_id || null
        })
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success(filterDialog.mode === 'add' ? "过滤规则添加成功" : "过滤规则更新成功");
          setFilterDialog({ open: false, mode: 'add', editId: null });
          setFilterForm({
            name: '',
            description: '',
            rule_type: 'extension',
            pattern: '',
            action: 'exclude',
            priority: 'medium',
            pattern_type: 'regex',
            category_id: 0
          });
          await loadFilterRules();
        } else {
          toast.error(result.message || "操作失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "操作失败");
      }
    } catch (error) {
      console.error("过滤规则操作失败:", error);
      toast.error("操作失败");
    }
  };

  const handleFilterDelete = async (ruleId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/filter-rules/${ruleId}`, {
        method: "DELETE"
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success("过滤规则删除成功");
          await loadFilterRules();
        } else {
          toast.error(result.message || "删除失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "删除失败");
      }
    } catch (error) {
      console.error("删除过滤规则失败:", error);
      toast.error("删除失败");
    }
  };

  // ========== Bundle扩展名事件处理函数 ==========

  const handleBundleSubmit = async () => {
    if (!bundleForm.extension.trim()) {
      toast.error("扩展名不能为空");
      return;
    }

    try {
      const url = bundleDialog.mode === 'add' 
        ? "http://127.0.0.1:60315/bundle-extensions"
        : `http://127.0.0.1:60315/bundle-extensions/${bundleDialog.editId}`;
      
      const method = bundleDialog.mode === 'add' ? "POST" : "PUT";
      
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extension: bundleForm.extension.trim(),
          description: bundleForm.description.trim() || null
        })
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success(bundleDialog.mode === 'add' ? "Bundle扩展名添加成功" : "Bundle扩展名更新成功");
          setBundleDialog({ open: false, mode: 'add', editId: null });
          setBundleForm({ extension: '', description: '' });
          await loadBundleExtensions();
        } else {
          toast.error(result.message || "操作失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "操作失败");
      }
    } catch (error) {
      console.error("Bundle扩展名操作失败:", error);
      toast.error("操作失败");
    }
  };

  const handleBundleToggle = async (bundleId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/bundle-extensions/${bundleId}/toggle`, {
        method: "PATCH"
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success("Bundle扩展名状态切换成功");
          await loadBundleExtensions();
        } else {
          toast.error(result.message || "切换失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "切换失败");
      }
    } catch (error) {
      console.error("切换Bundle扩展名状态失败:", error);
      toast.error("切换失败");
    }
  };

  const handleBundleDelete = async (bundleId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:60315/bundle-extensions/${bundleId}`, {
        method: "DELETE"
      });

      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          toast.success("Bundle扩展名删除成功");
          await loadBundleExtensions();
        } else {
          toast.error(result.message || "删除失败");
        }
      } else {
        const error = await response.json();
        toast.error(error.message || "删除失败");
      }
    } catch (error) {
      console.error("删除Bundle扩展名失败:", error);
      toast.error("删除失败");
    }
  };

  // ========== 优先级颜色映射 ==========
  const getPriorityBadgeVariant = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'destructive' as const;
      case 'medium':
        return 'default' as const;
      case 'low':
        return 'secondary' as const;
      default:
        return 'outline' as const;
    }
  };

  // ========== 渲染函数 ==========

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mb-4 mx-auto"></div>
          <p className="text-lg text-gray-600">加载文件识别规则中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 w-full">
      <div className="mb-6 px-6">
        <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
          <FileText className="h-8 w-8" />
          文件识别规则管理
        </h1>
        <p className="text-gray-600 mt-2">
          配置文件分类、扩展名映射、过滤规则和Bundle识别规则，优化文件处理效率
        </p>
      </div>

      <div className="px-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="categories" className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              文件分类
            </TabsTrigger>
            <TabsTrigger value="extensions" className="flex items-center gap-2">
              <Settings className="h-4 w-4" />
              扩展名映射
            </TabsTrigger>
            <TabsTrigger value="filters" className="flex items-center gap-2">
              <Filter className="h-4 w-4" />
              过滤规则
            </TabsTrigger>
            <TabsTrigger value="bundles" className="flex items-center gap-2">
              <Package className="h-4 w-4" />
              Bundle扩展名
            </TabsTrigger>
          </TabsList>

          {/* 文件分类标签页 */}
          <TabsContent value="categories" className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>文件分类管理</CardTitle>
                    <CardDescription>
                      定义文件的分类类型，用于组织和管理不同类型的文件
                    </CardDescription>
                  </div>
                  <Button onClick={() => setCategoryDialog({ open: true, mode: 'add', editId: null })}>
                    <Plus className="h-4 w-4 mr-2" />
                    添加分类
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {categories.map((category) => (
                    <Card key={category.id} className="p-4">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-lg">{category.icon || '📄'}</span>
                            <span className="font-medium">{category.name}</span>
                          </div>
                          <p className="text-sm text-gray-500 mb-2">
                            {category.description || '无描述'}
                          </p>
                          <Badge variant="secondary">
                            {category.extension_count} 个扩展名
                          </Badge>
                        </div>
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setCategoryForm({
                                name: category.name,
                                description: category.description || '',
                                icon: category.icon || ''
                              });
                              setCategoryDialog({ open: true, mode: 'edit', editId: category.id });
                            }}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="outline">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>确认删除</AlertDialogTitle>
                                <AlertDialogDescription>
                                  确定要删除分类 "{category.name}" 吗？这将同时删除所有关联的扩展名映射。
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>取消</AlertDialogCancel>
                                <AlertDialogAction onClick={() => handleCategoryDelete(category.id)}>
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

                {categories.length === 0 && (
                  <div className="text-center py-8 text-gray-500">
                    还没有配置文件分类
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* 扩展名映射标签页 */}
          <TabsContent value="extensions" className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>扩展名映射管理</CardTitle>
                    <CardDescription>
                      将文件扩展名映射到对应的分类，用于自动识别文件类型
                    </CardDescription>
                  </div>
                  <Button onClick={() => setExtensionDialog({ open: true, mode: 'add', editId: null })}>
                    <Plus className="h-4 w-4 mr-2" />
                    添加映射
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>扩展名</TableHead>
                      <TableHead>分类</TableHead>
                      <TableHead>描述</TableHead>
                      <TableHead>优先级</TableHead>
                      <TableHead>操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {extensionMappings.map((mapping) => (
                      <TableRow key={mapping.id}>
                        <TableCell>.{mapping.extension}</TableCell>
                        <TableCell>
                          <Badge>{mapping.category_name}</Badge>
                        </TableCell>
                        <TableCell>{mapping.description || '-'}</TableCell>
                        <TableCell>
                          <Badge variant={getPriorityBadgeVariant(mapping.priority)}>
                            {mapping.priority}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button 
                              size="sm" 
                              variant="outline"
                              onClick={() => {
                                setExtensionForm({
                                  extension: mapping.extension,
                                  category_id: mapping.category_id,
                                  description: mapping.description || '',
                                  priority: mapping.priority
                                });
                                setExtensionDialog({ open: true, mode: 'edit', editId: mapping.id });
                              }}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <Button size="sm" variant="outline">
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>确认删除</AlertDialogTitle>
                                  <AlertDialogDescription>
                                    确定要删除扩展名映射 ".{mapping.extension}" 吗？
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>取消</AlertDialogCancel>
                                  <AlertDialogAction onClick={() => handleExtensionDelete(mapping.id)}>
                                    确认删除
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                {extensionMappings.length === 0 && (
                  <div className="text-center py-8 text-gray-500">
                    还没有配置扩展名映射
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* 过滤规则标签页 */}
          <TabsContent value="filters" className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>文件过滤规则管理</CardTitle>
                    <CardDescription>
                      定义文件过滤规则，控制哪些文件需要包含或排除
                    </CardDescription>
                  </div>
                  <Button onClick={() => setFilterDialog({ open: true, mode: 'add', editId: null })}>
                    <Plus className="h-4 w-4 mr-2" />
                    添加规则
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {filterRules.map((rule) => (
                    <Card key={rule.id} className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <div className="flex items-center gap-2">
                              <Switch 
                                checked={rule.enabled} 
                                onCheckedChange={() => handleFilterRuleToggle(rule.id)}
                              />
                              <span className="font-medium">{rule.name}</span>
                              {rule.is_system && (
                                <Badge variant="outline">系统</Badge>
                              )}
                            </div>
                          </div>
                          <p className="text-sm text-gray-500 mb-2">
                            {rule.description || '无描述'}
                          </p>
                          <div className="flex gap-2 text-xs">
                            <Badge variant="secondary">{rule.rule_type}</Badge>
                            <Badge variant={rule.action === 'exclude' ? 'destructive' : 'default'}>
                              {rule.action}
                            </Badge>
                            <Badge variant={getPriorityBadgeVariant(rule.priority)}>
                              {rule.priority}
                            </Badge>
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <Button 
                            size="sm" 
                            variant="outline"
                            onClick={() => {
                              setFilterForm({
                                name: rule.name,
                                description: rule.description || '',
                                rule_type: rule.rule_type,
                                pattern: rule.pattern,
                                action: rule.action,
                                priority: rule.priority,
                                pattern_type: rule.pattern_type,
                                category_id: rule.category_id || 0
                              });
                              setFilterDialog({ open: true, mode: 'edit', editId: rule.id });
                            }}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          {!rule.is_system && (
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <Button size="sm" variant="outline">
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>确认删除</AlertDialogTitle>
                                  <AlertDialogDescription>
                                    确定要删除过滤规则 "{rule.name}" 吗？
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>取消</AlertDialogCancel>
                                  <AlertDialogAction onClick={() => handleFilterDelete(rule.id)}>
                                    确认删除
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          )}
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>

                {filterRules.length === 0 && (
                  <div className="text-center py-8 text-gray-500">
                    还没有配置过滤规则
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Bundle扩展名标签页 */}
          <TabsContent value="bundles" className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Bundle扩展名管理</CardTitle>
                    <CardDescription>
                      配置macOS Bundle扩展名，这些看起来像文件的文件夹将被跳过扫描
                    </CardDescription>
                  </div>
                  <Button onClick={() => setBundleDialog({ open: true, mode: 'add', editId: null })}>
                    <Plus className="h-4 w-4 mr-2" />
                    添加扩展名
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {bundleExtensions.map((bundle) => (
                    <Card key={bundle.id} className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <Switch 
                              checked={bundle.is_active} 
                              onCheckedChange={() => handleBundleToggle(bundle.id)}
                            />
                            <span className="font-medium">{bundle.extension}</span>
                          </div>
                          <p className="text-sm text-gray-500">
                            {bundle.description || '无描述'}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          <Button 
                            size="sm" 
                            variant="outline"
                            onClick={() => {
                              setBundleForm({
                                extension: bundle.extension,
                                description: bundle.description || ''
                              });
                              setBundleDialog({ open: true, mode: 'edit', editId: bundle.id });
                            }}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="outline">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>确认删除</AlertDialogTitle>
                                <AlertDialogDescription>
                                  确定要删除Bundle扩展名 "{bundle.extension}" 吗？
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>取消</AlertDialogCancel>
                                <AlertDialogAction onClick={() => handleBundleDelete(bundle.id)}>
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
                    还没有配置Bundle扩展名
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      {/* 分类添加/编辑对话框 */}
      <Dialog open={categoryDialog.open} onOpenChange={(open) => setCategoryDialog(prev => ({ ...prev, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {categoryDialog.mode === 'add' ? '添加文件分类' : '编辑文件分类'}
            </DialogTitle>
            <DialogDescription>
              配置文件分类的基本信息
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="category-name">分类名称</Label>
              <Input
                id="category-name"
                value={categoryForm.name}
                onChange={(e) => setCategoryForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="例如：document"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category-description">描述</Label>
              <Input
                id="category-description"
                value={categoryForm.description}
                onChange={(e) => setCategoryForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="例如：文档类文件"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category-icon">图标</Label>
              <Input
                id="category-icon"
                value={categoryForm.icon}
                onChange={(e) => setCategoryForm(prev => ({ ...prev, icon: e.target.value }))}
                placeholder="例如：📄"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCategoryDialog(prev => ({ ...prev, open: false }))}>
              取消
            </Button>
            <Button onClick={handleCategorySubmit}>
              {categoryDialog.mode === 'add' ? '添加' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 扩展名映射添加/编辑对话框 */}
      <Dialog open={extensionDialog.open} onOpenChange={(open) => setExtensionDialog(prev => ({ ...prev, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {extensionDialog.mode === 'add' ? '添加扩展名映射' : '编辑扩展名映射'}
            </DialogTitle>
            <DialogDescription>
              配置文件扩展名到分类的映射关系
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="extension-name">扩展名</Label>
              <Input
                id="extension-name"
                value={extensionForm.extension}
                onChange={(e) => setExtensionForm(prev => ({ ...prev, extension: e.target.value }))}
                placeholder="例如：pdf（不含点）"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extension-category">分类</Label>
              <Select 
                value={extensionForm.category_id.toString()} 
                onValueChange={(value) => setExtensionForm(prev => ({ ...prev, category_id: parseInt(value) }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择分类" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((category) => (
                    <SelectItem key={category.id} value={category.id.toString()}>
                      {category.icon} {category.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="extension-description">描述</Label>
              <Input
                id="extension-description"
                value={extensionForm.description}
                onChange={(e) => setExtensionForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="例如：PDF文档文件"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="extension-priority">优先级</Label>
              <Select 
                value={extensionForm.priority} 
                onValueChange={(value) => setExtensionForm(prev => ({ ...prev, priority: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="high">高</SelectItem>
                  <SelectItem value="medium">中</SelectItem>
                  <SelectItem value="low">低</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExtensionDialog(prev => ({ ...prev, open: false }))}>
              取消
            </Button>
            <Button onClick={handleExtensionSubmit}>
              {extensionDialog.mode === 'add' ? '添加' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 过滤规则添加/编辑对话框 */}
      <Dialog open={filterDialog.open} onOpenChange={(open) => setFilterDialog(prev => ({ ...prev, open }))}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {filterDialog.mode === 'add' ? '添加过滤规则' : '编辑过滤规则'}
            </DialogTitle>
            <DialogDescription>
              配置文件过滤规则，控制文件的包含或排除逻辑
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="filter-name">规则名称</Label>
                <Input
                  id="filter-name"
                  value={filterForm.name}
                  onChange={(e) => setFilterForm(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="例如：排除隐藏文件"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="filter-rule-type">规则类型</Label>
                <Select 
                  value={filterForm.rule_type} 
                  onValueChange={(value) => setFilterForm(prev => ({ ...prev, rule_type: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="extension">扩展名规则</SelectItem>
                    <SelectItem value="filename">文件名规则</SelectItem>
                    <SelectItem value="path">路径规则</SelectItem>
                    <SelectItem value="size">文件大小规则</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="filter-description">描述</Label>
              <Input
                id="filter-description"
                value={filterForm.description}
                onChange={(e) => setFilterForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="规则的详细描述"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="filter-pattern">匹配模式</Label>
              <Input
                id="filter-pattern"
                value={filterForm.pattern}
                onChange={(e) => setFilterForm(prev => ({ ...prev, pattern: e.target.value }))}
                placeholder="例如：^\..*（匹配以点开头的文件）"
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="filter-action">动作</Label>
                <Select 
                  value={filterForm.action} 
                  onValueChange={(value) => setFilterForm(prev => ({ ...prev, action: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="include">包含</SelectItem>
                    <SelectItem value="exclude">排除</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="filter-priority">优先级</Label>
                <Select 
                  value={filterForm.priority} 
                  onValueChange={(value) => setFilterForm(prev => ({ ...prev, priority: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="high">高</SelectItem>
                    <SelectItem value="medium">中</SelectItem>
                    <SelectItem value="low">低</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="filter-pattern-type">模式类型</Label>
                <Select 
                  value={filterForm.pattern_type} 
                  onValueChange={(value) => setFilterForm(prev => ({ ...prev, pattern_type: value }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="regex">正则表达式</SelectItem>
                    <SelectItem value="glob">通配符</SelectItem>
                    <SelectItem value="exact">精确匹配</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="filter-category">关联分类（可选）</Label>
              <Select 
                value={filterForm.category_id.toString()} 
                onValueChange={(value) => setFilterForm(prev => ({ ...prev, category_id: parseInt(value) }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择分类（可选）" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">无关联分类</SelectItem>
                  {categories.map((category) => (
                    <SelectItem key={category.id} value={category.id.toString()}>
                      {category.icon} {category.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFilterDialog(prev => ({ ...prev, open: false }))}>
              取消
            </Button>
            <Button onClick={handleFilterSubmit}>
              {filterDialog.mode === 'add' ? '添加' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bundle扩展名添加/编辑对话框 */}
      <Dialog open={bundleDialog.open} onOpenChange={(open) => setBundleDialog(prev => ({ ...prev, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {bundleDialog.mode === 'add' ? '添加Bundle扩展名' : '编辑Bundle扩展名'}
            </DialogTitle>
            <DialogDescription>
              配置macOS Bundle扩展名，这些扩展名的文件夹会被识别为Bundle
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="bundle-extension">扩展名</Label>
              <Input
                id="bundle-extension"
                value={bundleForm.extension}
                onChange={(e) => setBundleForm(prev => ({ ...prev, extension: e.target.value }))}
                placeholder="例如：.app"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bundle-description">描述</Label>
              <Input
                id="bundle-description"
                value={bundleForm.description}
                onChange={(e) => setBundleForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="例如：应用程序Bundle"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBundleDialog(prev => ({ ...prev, open: false }))}>
              取消
            </Button>
            <Button onClick={handleBundleSubmit}>
              {bundleDialog.mode === 'add' ? '添加' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}