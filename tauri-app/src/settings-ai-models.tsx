import { useState, useEffect, useCallback } from "react"
import { useTranslation } from 'react-i18next';
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { toast } from "sonner"
import { 
  Loader2, 
  Plus, 
  Settings, 
  Trash2, 
  RefreshCw, 
  CheckCircle, 
  XCircle,
  AlertCircle,
  Zap,
  BadgeCheckIcon,
  // DatabaseBackup,
  SearchCheck,
} from "lucide-react"
import {
  openUrl,
} from "@tauri-apps/plugin-opener"

const API_BASE_URL = "http://127.0.0.1:60315"

// 类型定义
interface Provider {
  id: number | string
  key: string
  provider_type: string
  name: string
  description?: string
  config: Record<string, any>
  is_enabled: boolean
  is_user_added?: boolean  // 是否为用户添加的提供商
  // 添加预置提供商的字段
  base_url?: string
  api_key?: string
  get_key_url?: string
  use_proxy?: boolean
}

interface ModelCapabilities {
  text: boolean
  vision: boolean
  tool_use: boolean
  embedding: boolean
}

interface Model {
  id: string
  name: string
  provider: string
  capabilities: ModelCapabilities
  is_available: boolean
}

interface GlobalCapability {
  capability: string
  provider_key: string
  model_id: string
}

interface BusinessScene {
  key: string
  name: string
  description: string
  required_capabilities: string[]
  icon?: React.ReactNode
}

// 业务场景定义
const BUSINESS_SCENES: BusinessScene[] = [
  {
    key: "SCENE_FILE_TAGGING",
    name: "文件自动打标签",
    description: "基于文件内容自动生成相关标签，帮助快速分类和检索文件",
    required_capabilities: ["text", "embedding"],
    icon: <Settings className="w-4 h-4" />
  },
  {
    key: "SCENE_MULTIVECTOR", 
    name: "多模态检索",
    description: "支持文本、图像等多种模态内容的智能检索和对话关联",
    required_capabilities: ["text", "embedding", "vision"],
    icon: <Zap className="w-4 h-4" />
  }
]

// API 服务函数
class ModelSettingsAPI {
  // 将后端返回的能力数据转换为标准格式
  private static normalizeCapabilities(capabilitiesData: any): ModelCapabilities {
    // 如果是数组格式（旧格式），转换为键值对
    if (Array.isArray(capabilitiesData)) {
      return {
        text: capabilitiesData.includes('text') || capabilitiesData.includes('TEXT'),
        vision: capabilitiesData.includes('vision') || capabilitiesData.includes('VISION'),
        tool_use: capabilitiesData.includes('tool_use') || capabilitiesData.includes('TOOL_USE'),
        embedding: capabilitiesData.includes('embedding') || capabilitiesData.includes('EMBEDDING')
      }
    }
    
    // 如果是键值对格式（新格式），直接使用并提供默认值
    return {
      text: capabilitiesData?.text ?? false,
      vision: capabilitiesData?.vision ?? false,
      tool_use: capabilitiesData?.tool_use ?? false,
      embedding: capabilitiesData?.embedding ?? false
    }
  }
  // 获取所有提供商配置
  static async getProviders(): Promise<Provider[]> {
    const response = await fetch(`${API_BASE_URL}/models/providers`)
    const result = await response.json()
    if (result.success) {
      return result.data.map((config: any, index: number) => ({
        id: config.id || index,
        key: `${config.provider_type}-${config.id || index}`,
        provider_type: config.provider_type,
        name: config.display_name,
        description: config.source_type,
        config: {
          base_url: config.base_url,
          api_key: config.api_key,
          ...config.extra_data_json
        },
        is_enabled: config.is_active,
        is_user_added: config.is_user_added !== undefined ? config.is_user_added : true,
        // 添加预置提供商的直接字段
        base_url: config.base_url,
        api_key: config.api_key,
        get_key_url: config.get_key_url,
        use_proxy: config.use_proxy
      }))
    }
    throw new Error(result.message || 'Failed to fetch providers')
  }

  // 更新提供商配置
  static async updateProvider(id: number, provider: Partial<Provider>): Promise<Provider> {
    const response = await fetch(`${API_BASE_URL}/models/provider/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id,
        display_name: provider.name || provider.config?.display_name,
        base_url: provider.base_url || provider.config?.base_url,
        api_key: provider.api_key || provider.config?.api_key,
        extra_data_json: provider.config || {},
        is_active: provider.is_enabled,
        use_proxy: provider.use_proxy || false
      })
    })
    const result = await response.json()
    if (result.success) {
      const config = result.data
      return {
        id: config.id,
        key: `${config.provider_type}-${config.id}`,
        provider_type: config.provider_type,
        name: config.display_name || config.provider_type,
        description: config.provider_type,
        config: {
          base_url: config.base_url,
          api_key: config.api_key,
          ...config.extra_data_json
        },
        is_enabled: config.is_active,
        is_user_added: config.is_user_added !== undefined ? config.is_user_added : true,
        base_url: config.base_url,
        api_key: config.api_key,
        get_key_url: config.get_key_url,
        use_proxy: config.use_proxy
      }
    }
    throw new Error(result.message || 'Failed to update provider')
  }

  // 创建提供商
  static async createProvider(providerData: {
    provider_type: string
    display_name: string
    base_url?: string
    api_key?: string
    extra_data_json?: Record<string, any>
    is_active?: boolean
    use_proxy?: boolean
  }): Promise<Provider> {
    const response = await fetch(`${API_BASE_URL}/models/providers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(providerData)
    })
    const result = await response.json()
    if (result.success) {
      const config = result.data
      return {
        id: config.id,
        key: `${config.provider_type}-${config.id}`,
        provider_type: config.provider_type,
        name: config.display_name || config.provider_type,
        description: config.provider_type,
        config: {
          base_url: config.base_url,
          api_key: config.api_key,
          ...config.extra_data
        },
        is_enabled: config.is_active
      }
    }
    throw new Error(result.message || 'Failed to create provider')
  }

  // 删除提供商
  static async deleteProvider(providerId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/models/provider/${providerId}`, {
      method: 'DELETE'
    })
    const result = await response.json()
    if (!result.success) {
      throw new Error(result.message || 'Failed to delete provider')
    }
  }

  // 发现提供商模型
  static async discoverModels(providerId: number, providerKey: string): Promise<Model[]> {
    const response = await fetch(`${API_BASE_URL}/models/provider/${providerId}/discover`, {
      method: 'POST'
    })
    const result = await response.json()
    
    if (result.success) {
      // API 返回的是 ModelConfiguration 对象数组
      return result.data.filter((model: any) => model && model.id).map((model: any) => ({
        id: model.id.toString(),
        name: model.display_name || model.model_identifier,
        provider: providerKey, // 使用传入的 providerKey
        capabilities: this.normalizeCapabilities(model.capabilities_json),
        is_available: model.is_enabled !== undefined ? model.is_enabled : true
      }))
    }
    throw new Error(result.message || 'Failed to discover models')
  }

  // 获取提供商的所有模型
  static async getProviderModels(providerId: number, providerKey: string): Promise<Model[]> {
    const response = await fetch(`${API_BASE_URL}/models/provider/${providerId}`)
    const result = await response.json()
    
    if (result.success) {
      // API 返回的是 ModelConfiguration 对象数组
      return result.data.filter((model: any) => model && model.id).map((model: any) => ({
        id: model.id.toString(),
        name: model.display_name || model.model_identifier,
        provider: providerKey,
        capabilities: this.normalizeCapabilities(model.capabilities_json),
        is_available: model.is_enabled !== undefined ? model.is_enabled : true
      }))
    }
    throw new Error(result.message || 'Failed to get provider models')
  }

  // 确认指定模型所有能力
  static async confirmModelCapability(modelId: number): Promise<ModelCapabilities> {
    const response = await fetch(`${API_BASE_URL}/models/confirm_capability/${modelId}`)
    const result = await response.json()
    if (result.success) {
      return result.data as ModelCapabilities
    }
    throw new Error(result.message || 'Failed to test model capability')
  }

  // 获取全局能力分配
  static async getGlobalCapability(capability: string): Promise<GlobalCapability | null> {
    const response = await fetch(`${API_BASE_URL}/models/global_capability/${capability}`)
    const result = await response.json()
    if (result.success) {
      return result.data as GlobalCapability
    }
    return null
  }

  // 分配全局能力
  static async assignGlobalCapability(capability: string, modelId: number): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/models/global_capability/${capability}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId })
    })
    const result = await response.json()
    if (!result.success) {
      throw new Error(result.message || 'Failed to assign global capability')
    }
  }

  // 获取所有能力类型
  static async getAvailableCapabilities(): Promise<string[]> {
    const response = await fetch(`${API_BASE_URL}/models/capabilities`)
    const result = await response.json()
    if (result.success) {
      return result.data
    }
    throw new Error(result.message || 'Failed to get capabilities')
  }

  // 切换模型启用/禁用状态
  static async toggleModelEnabled(modelId: number, isEnabled: boolean): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/models/model/${modelId}/toggle`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ is_enabled: isEnabled })
    })
    const result = await response.json()
    if (!result.success) {
      throw new Error(result.message || 'Failed to toggle model status')
    }
  }
}


// 全局能力分配组件
function GlobalCapabilitySection({ 
  providers, 
  models, 
  globalCapabilities,
  onUpdateGlobalCapability 
}: {
  providers: Provider[]
  models: Model[]
  globalCapabilities: GlobalCapability[]
  onUpdateGlobalCapability: (capability: string, provider_key: string, model_id: string) => void
}) {
  // 检查模型是否具有特定能力
  const hasCapability = useCallback((model: Model, capability: string): boolean => {
    const capKey = capability.toLowerCase() as keyof ModelCapabilities
    return model.capabilities[capKey] || false
  }, [])

  // 获取某个能力的当前分配
  const getCapabilityAssignment = useCallback((capability: string) => {
    return globalCapabilities.find(gc => gc.capability === capability)
  }, [globalCapabilities])

  // 获取某个能力的可用模型
  const getAvailableModelsForCapability = useCallback((capability: string) => {
    return models.filter(model => 
      hasCapability(model, capability) && model.is_available
    )
  }, [models, hasCapability])

  // 获取提供商显示名称
  const getProviderDisplayName = useCallback((providerKey: string): string => {
    const provider = providers.find(p => p.key === providerKey)
    return provider ? provider.name : providerKey
  }, [providers])

  // 检查是否有可用的提供商
  const hasConfiguredProviders = providers.length > 0
  
  // 检查某个场景的完整度（已分配能力数 / 所需能力数）
  const getSceneCompleteness = useCallback((scene: BusinessScene) => {
    const assignedCount = scene.required_capabilities.filter(capability => 
      getCapabilityAssignment(capability) !== undefined
    ).length
    return {
      assigned: assignedCount,
      total: scene.required_capabilities.length,
      percentage: Math.round((assignedCount / scene.required_capabilities.length) * 100)
    }
  }, [getCapabilityAssignment])

  const { t } = useTranslation();
  
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="w-5 h-5" />
          场景配置
        </CardTitle>
        <CardDescription>
          为不同的业务场景分配AI模型。配置完成后，相应功能将自动解锁。
          {!hasConfiguredProviders && " 请先配置模型提供商。"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!hasConfiguredProviders ? (
          <div className="text-center py-8 text-muted-foreground">
            <Settings className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>需要先配置模型提供商才能分配能力</p>
            <p className="text-sm mt-1">请滚动到下方"模型提供商管理"部分开始配置</p>
          </div>
        ) : (
          BUSINESS_SCENES.map(scene => {
            const completeness = getSceneCompleteness(scene)
            
            return (
              <div key={scene.key} className="border rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-start gap-3">
                    {scene.icon}
                    <div className="flex-1">
                      <h3 className="font-medium flex items-center gap-2">
                        {scene.name}
                        {completeness.percentage === 100 ? (
                          <Badge variant="default" className="text-xs">
                            <CheckCircle className="w-3 h-3 mr-1" />
                            已配置
                          </Badge>
                        ) : completeness.assigned > 0 ? (
                          <Badge variant="secondary" className="text-xs">
                            <AlertCircle className="w-3 h-3 mr-1" />
                            {completeness.percentage}% 完成
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">
                            <XCircle className="w-3 h-3 mr-1" />
                            未配置
                          </Badge>
                        )}
                      </h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        {scene.description}
                      </p>
                      
                      {/* 进度条 */}
                      {completeness.total > 0 && (
                        <div className="mt-2">
                          <div className="flex justify-between text-xs text-muted-foreground mb-1">
                            <span>配置进度</span>
                            <span>{completeness.assigned}/{completeness.total}</span>
                          </div>
                          <div className="w-full bg-muted rounded-full h-1.5">
                            <div 
                              className={`h-1.5 rounded-full transition-all duration-300 ${
                                completeness.percentage === 100 
                                  ? 'bg-green-500' 
                                  : completeness.percentage > 0 
                                    ? 'bg-blue-500' 
                                    : 'bg-muted'
                              }`}
                              style={{ width: `${completeness.percentage}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                
                <div className="space-y-3">
                  <div className="text-sm font-medium">所需能力配置：</div>
                  {scene.required_capabilities.map(capability => {
                    const assignment = getCapabilityAssignment(capability)
                    const availableModels = getAvailableModelsForCapability(capability)
                    const hasModels = availableModels.length > 0
                    const isAssigned = assignment !== undefined
                    
                    return (
                      <div key={capability} className="flex items-center justify-between p-3 bg-muted/50 rounded">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{t(`ModelCapability.${capability.toUpperCase()}`)}</Badge>
                          {isAssigned && (
                            <CheckCircle className="w-4 h-4 text-green-500" />
                          )}
                          {!hasModels && (
                            <AlertCircle className="w-4 h-4 text-amber-500" />
                          )}
                        </div>
                        
                        {hasModels ? (
                          <Select
                            value={assignment?.model_id || ""}
                            onValueChange={(modelId) => {
                              const model = models.find(m => m.id === modelId)
                              if (model) {
                                onUpdateGlobalCapability(capability, model.provider, modelId)
                              }
                            }}
                          >
                            <SelectTrigger className="w-md">
                              <SelectValue placeholder="选择模型" />
                            </SelectTrigger>
                            <SelectContent>
                              {availableModels.map(model => (
                                <SelectItem key={model.id} value={model.id}>
                                  <div className="flex items-center gap-2">
                                    {model.name} 
                                    <Badge variant="secondary" className="text-xs">
                                      {getProviderDisplayName(model.provider)}
                                    </Badge>
                                  </div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <div className="text-sm text-muted-foreground">
                            需要先配置支持 {t(`ModelCapability.${capability.toUpperCase()}`)} 能力的模型
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}// 提供商管理组件
// 提供商配置显示组件
function ProviderConfigDisplay({ provider }: { provider: Provider }) {
  const [tempApiKey, setTempApiKey] = useState(provider.api_key || '')
  const [useProxy, setUseProxy] = useState(provider.use_proxy || false)

  const handleApiKeyChange = async (newApiKey: string) => {
    if (newApiKey !== provider.api_key) {
      try {
        // 更新API密钥
        const providerId = typeof provider.id === 'string' ? parseInt(provider.id) : provider.id;
        await ModelSettingsAPI.updateProvider(providerId, {
          ...provider,
          api_key: newApiKey
        });
        toast.success('API Key 更新成功');
      } catch (error) {
        console.error('Failed to update API key:', error);
        toast.error('API Key 更新失败');
        setTempApiKey(provider.api_key || ''); // 恢复原值
      }
    }
  };

  const handleProxyToggle = async (checked: boolean) => {
    try {
      const providerId = typeof provider.id === 'string' ? parseInt(provider.id) : provider.id;
      await ModelSettingsAPI.updateProvider(providerId, {
        ...provider,
        use_proxy: checked
      });
      setUseProxy(checked);
      toast.success(`已${checked ? '启用' : '禁用'}代理`);
    } catch (error) {
      console.error('Failed to update proxy setting:', error);
      toast.error('代理设置更新失败');
      setUseProxy(!checked); // 恢复原状态
    }
  };

  return (
    <div className="mt-3 space-y-3 p-3 bg-muted/30 rounded-md">
      {/* Base URL - 只读显示 */}
      {provider.base_url && (
        <div className="space-y-1">
          <Label className="text-xs font-medium text-muted-foreground">Base URL</Label>
          <div className="flex items-center gap-2">
            <Input
              value={provider.base_url}
              readOnly
              className="font-mono text-xs bg-background/50"
            />
          </div>
        </div>
      )}

      {/* API Key - 明文可编辑 */}
      <div className="space-y-1">
        <Label className="text-xs font-medium text-muted-foreground">API Key</Label>
        <div className="flex items-center gap-2">
          <Input
            type="text"
            value={tempApiKey}
            onChange={(e) => setTempApiKey(e.target.value)}
            onBlur={() => handleApiKeyChange(tempApiKey)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.currentTarget.blur();
              }
            }}
            placeholder="输入API Key"
            className="font-mono text-xs"
          />
        </div>
      </div>

      {/* Get Key URL - 跳转链接 */}
      {provider.get_key_url && (
        <div className="space-y-1">
          <Label className="text-xs font-medium text-muted-foreground">获取密钥</Label>
          <div>
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs text-primary hover:underline"
              onClick={() => provider.get_key_url && openUrl(provider.get_key_url)}
            >
              前往获取 API Key →
            </Button>
          </div>
        </div>
      )}

      {/* 代理设置 */}
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium text-muted-foreground">使用代理转发请求</Label>
        <Switch
          checked={useProxy}
          onCheckedChange={handleProxyToggle}
        />
      </div>
    </div>
  )
}

// 添加提供商的空状态组件
function AddProviderEmptyState({ 
  onAddProvider 
}: { 
  onAddProvider: (providerData: Omit<Provider, 'key'>) => void 
}) {
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [newProvider, setNewProvider] = useState({
    name: "",
    description: "",
    config: {} as Record<string, any>
  })

  const handleAddProvider = () => {
    if (!newProvider.name.trim()) {
      toast.error("请输入提供商名称")
      return
    }
    
    onAddProvider({
      id: Date.now(), // 临时ID，后端会分配真实ID
      provider_type: newProvider.name.toLowerCase().replace(/\s+/g, '_'),
      name: newProvider.name,
      description: newProvider.description,
      config: newProvider.config,
      is_enabled: true
    })
    
    setNewProvider({ name: "", description: "", config: {} })
    setShowAddDialog(false)
  }

  return (
    <div className="text-center p-2 text-muted-foreground ml-auto">
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogTrigger asChild>
          <Button>
            <Plus className="w-4 h-4 mr-2" />
            添加提供商
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加模型提供商</DialogTitle>
            <DialogDescription>
              配置新的AI模型提供商信息
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label htmlFor="provider-name">提供商名称 *</Label>
              <Input
                id="provider-name"
                value={newProvider.name}
                onChange={(e) => setNewProvider(prev => ({ ...prev, name: e.target.value }))}
                placeholder="例如：OpenAI、Claude等"
                className="mt-1"
              />
            </div>
            
            <div>
              <Label htmlFor="provider-desc">描述（可选）</Label>
              <Input
                id="provider-desc"
                value={newProvider.description}
                onChange={(e) => setNewProvider(prev => ({ ...prev, description: e.target.value }))}
                placeholder="简单描述该提供商"
                className="mt-1"
              />
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>
              取消
            </Button>
            <Button onClick={handleAddProvider} disabled={!newProvider.name.trim()}>
              添加
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// 单个提供商详情组件
function ProviderDetailSection({
  provider,
  models,
  availableCapabilities,
  onToggleProvider,
  onDiscoverModels,
  onConfirmModelCapability,
  onToggleModel,
  onDeleteProvider,
  isLoading
}: {
  provider: Provider
  models: Model[]
  availableCapabilities: string[]
  onToggleProvider: (providerKey: string, enabled: boolean) => void
  onDiscoverModels: (providerKey: string) => void
  onConfirmModelCapability: (modelId: string) => void
  onToggleModel: (modelId: string, enabled: boolean) => void
  onDeleteProvider: (key: string) => void
  isLoading: boolean
}) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const availableModels = models.filter(m => m.is_available)
  const { t } = useTranslation();

  const handleConfirmDelete = () => {
    if (models.length > 0) {
      toast.error(`无法删除提供商 ${provider.name}，因为还有 ${models.length} 个模型正在使用`)
      return
    }
    
    onDeleteProvider(provider.key)
    setShowDeleteDialog(false)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <CardTitle className="text-xl">{provider.name}</CardTitle>
              <div className="flex items-center gap-2">
                <Switch
                  checked={provider.is_enabled}
                  onCheckedChange={(checked) => onToggleProvider(provider.key, checked)}
                  disabled={isLoading}
                />
                <span className="text-sm text-muted-foreground">
                  {provider.is_enabled ? "已启用" : "已禁用"}
                </span>
              </div>
              {models.length > 0 && (
                <Badge variant="outline" className="text-xs">
                  {availableModels.length}/{models.length} 可用
                </Badge>
              )}
            </div>
            {provider.description && (
              <CardDescription>{provider.description}</CardDescription>
            )}
          </div>
          
          <div className="flex items-center gap-2">            
            {provider.is_user_added && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowDeleteDialog(true)}
                disabled={isLoading}
                title="删除提供商"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        {/* 配置信息显示 */}
        <ProviderConfigDisplay provider={provider} />
        
        {/* 模型列表 */}
        <div className="flex items-center justify-end mt-6">
            <Button
              variant="default"
              size="sm"
              onClick={() => onDiscoverModels(provider.key)}
              disabled={isLoading}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4 mr-2" />
              )}
              发现模型
            </Button>
        </div>
        {models.length > 0 && (
          <div className="mt-0 space-y-4">
            <div className="text-sm font-medium">
              模型列表 ({availableModels.length}/{models.length} 可用)：
            </div>
            <div className="space-y-2 h-full">
              {models.map(model => (
                <div key={model.id} className="flex items-center justify-between p-3 border rounded-md">
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <div className="font-medium">{model.name}</div>
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {availableCapabilities.map(cap => {
                          const capKey = cap.toLowerCase() as keyof ModelCapabilities
                          const hasCapability = model.capabilities[capKey] || false
                          return (
                            <Badge 
                              key={cap}
                              variant={hasCapability ? "default" : "outline"}
                              className={`text-xs rounded-full px-2 py-0.5 font-semibold ${hasCapability ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
                            >
                              <BadgeCheckIcon className={`${hasCapability ? '' : 'hidden'}`} />{t(`ModelCapability.${cap.toUpperCase()}`)}
                            </Badge>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onConfirmModelCapability(model.id)}
                      disabled={isLoading}
                      title="测试模型能力"
                    >
                      {isLoading ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <SearchCheck className="w-3 h-3" />
                      )}
                    </Button>
                    <Switch
                      id={model.id}
                      checked={model.is_available}
                      onCheckedChange={(checked) => onToggleModel(model.id, checked)}
                    />
                    <Label htmlFor={model.id}>{model.is_available ? "已启用" : "未启用"}</Label>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {models.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <RefreshCw className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>暂无模型</p>
            <p className="text-sm mt-1">输入API Key后点击右侧"发现模型"来获取可用模型</p>
          </div>
        )}
      </CardContent>
      
      {/* 删除确认对话框 */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除提供商确认</DialogTitle>
            <DialogDescription>
              确定要删除提供商 "{provider.name}" 吗？
              这个操作无法撤销。
            </DialogDescription>
          </DialogHeader>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              取消
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleConfirmDelete}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

// 主组件
function SettingsAIModels() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [globalCapabilities, setGlobalCapabilities] = useState<GlobalCapability[]>([])
  const [availableCapabilities, setAvailableCapabilities] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [initialized, setInitialized] = useState(false)

  // 初始化数据
  useEffect(() => {
    const initializeData = async () => {
      setIsLoading(true)
      try {
        // 并行加载提供商数据和系统能力列表
        const [providersData, capabilitiesData] = await Promise.all([
          ModelSettingsAPI.getProviders().catch(() => []),
          ModelSettingsAPI.getAvailableCapabilities().catch(() => [])
        ])
        
        // console.log(`API endpoint: ${API_BASE_URL}`)
        
        setProviders(providersData)
        setAvailableCapabilities(capabilitiesData)
        
        // 为每个提供商加载现有模型
        const allModels: Model[] = []
        for (const provider of providersData) {
          try {
            const providerId = typeof provider.id === 'string' ? parseInt(provider.id) : provider.id
            const providerModels = await ModelSettingsAPI.getProviderModels(providerId, provider.key)
            allModels.push(...providerModels)
          } catch (error) {
            console.warn(`Failed to load models for provider ${provider.name}:`, error)
          }
        }
        
        setModels(allModels)
        
        // 加载全局能力分配
        const globalCapabilitiesData: GlobalCapability[] = []
        for (const capability of capabilitiesData) {
          try {
            const assignment = await ModelSettingsAPI.getGlobalCapability(capability)
            if (assignment) {
              globalCapabilitiesData.push(assignment)
            }
          } catch (error) {
            console.warn(`Failed to load global capability assignment for ${capability}:`, error)
          }
        }
        setGlobalCapabilities(globalCapabilitiesData)
        
        setInitialized(true)
      } catch (error) {
        console.error("Failed to initialize data:", error)
        toast.error("加载数据失败")
        
        // 降级使用空数据
        setProviders([])
        setModels([])
        setGlobalCapabilities([])
        setInitialized(true)
      } finally {
        setIsLoading(false)
      }
    }

    initializeData()
  }, [])

  // 添加提供商
  const handleAddProvider = async (providerData: Omit<Provider, 'key'>) => {
    setIsLoading(true)
    try {
      // 调用 API 创建提供商
      const newProvider = await ModelSettingsAPI.createProvider({
        provider_type: providerData.provider_type,
        display_name: providerData.name,
        base_url: providerData.config?.base_url || "",
        api_key: providerData.config?.api_key || "",
        extra_data_json: providerData.config || {},
        is_active: providerData.is_enabled,
        use_proxy: providerData.config?.use_proxy || false
      })
      
      setProviders(prev => [...prev, newProvider])
      toast.success(`提供商 ${providerData.name} 添加成功`)
    } catch (error) {
      console.error("Failed to add provider:", error)
      toast.error(`添加提供商失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsLoading(false)
    }
  }

  // 删除提供商
  const handleDeleteProvider = async (providerKey: string) => {
    setIsLoading(true)
    try {
      const provider = providers.find(p => p.key === providerKey)
      if (!provider) {
        throw new Error('Provider not found')
      }
      
      // 调用 API 删除提供商
      const providerId = typeof provider.id === 'string' ? parseInt(provider.id) : provider.id
      await ModelSettingsAPI.deleteProvider(providerId)
      
      setProviders(prev => prev.filter(p => p.key !== providerKey))
      setModels(prev => prev.filter(m => m.provider !== providerKey))
      toast.success("提供商删除成功")
    } catch (error) {
      console.error("Failed to delete provider:", error)
      toast.error(`删除提供商失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsLoading(false)
    }
  }

  // 发现模型
  const handleDiscoverModels = async (providerKey: string) => {
    setIsLoading(true)
    try {
      // 找到对应的提供商以获取其ID
      const provider = providers.find(p => p.key === providerKey)
      if (!provider) {
        throw new Error('Provider not found')
      }
      
      console.log(`Discovering models for provider: ${providerKey}, ID: ${provider.id}`)
      
      // 调用 API 发现新模型
      const providerId = typeof provider.id === 'string' ? parseInt(provider.id) : provider.id
      const discoveredModels = await ModelSettingsAPI.discoverModels(providerId, providerKey)
      
      // 发现完成后，获取该提供商的所有模型（包括之前已有的）
      const allProviderModels = await ModelSettingsAPI.getProviderModels(providerId, providerKey)
      
      // 更新模型列表，显示该提供商的所有模型
      setModels(prev => {
        const filtered = prev.filter(m => m.provider !== providerKey)
        return [...filtered, ...allProviderModels]
      })
      
      toast.success(`成功发现 ${discoveredModels.length} 个新模型，当前共有 ${allProviderModels.length} 个模型`)
    } catch (error) {
      console.error('Failed to discover models:', error)
      toast.error(`模型发现失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsLoading(false)
    }
  }

  // 测试模型能力
  const handleConfirmModelCapability = async (modelId: string) => {
    setIsLoading(true)
    try {
      console.log(`Testing model capability: ${modelId}`)
      
      // 获取模型的当前能力
      const numericModelId = parseInt(modelId, 10)
      if (isNaN(numericModelId)) {
        throw new Error('Invalid model ID')
      }
      
      const capabilities = await ModelSettingsAPI.confirmModelCapability(numericModelId)
      console.log('Model capabilities:', capabilities)
      
      // 更新模型状态为可用（如果成功获取到能力信息）
      setModels(prev => prev.map(model => 
        model.id === modelId ? { ...model, is_available: true, capabilities } : model
      ))
      
      // 计算能力数量
      const capabilityCount = Object.values(capabilities).filter(Boolean).length
      toast.success(`模型能力测试完成，发现 ${capabilityCount} 项能力`)
    } catch (error) {
      console.error("Failed to test model capability:", error)
      
      // 如果测试失败，标记模型为不可用
      setModels(prev => prev.map(model => 
        model.id === modelId ? { ...model, is_available: false } : model
      ))
      
      toast.error(`模型能力测试失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsLoading(false)
    }
  }
  
  // 切换提供商启用状态
  const handleToggleProvider = async (provider_key: string, enabled: boolean) => {
    try {
      // 找到要更新的提供商
      const provider = providers.find(p => p.key === provider_key);
      if (!provider) {
        console.error('Provider not found:', provider_key);
        return;
      }

      // 确保 ID 是数字
      const providerId = typeof provider.id === 'string' ? parseInt(provider.id, 10) : provider.id;
      if (isNaN(providerId)) {
        throw new Error(`Provider ID ${provider.id} is not numeric`);
      }

      // 创建更新对象
      const updatedProvider = {
        ...provider,
        is_enabled: enabled
      };

      // 调用API更新提供商
      await ModelSettingsAPI.updateProvider(providerId, updatedProvider);
      
      // 刷新提供商列表
      const updatedProviders = await ModelSettingsAPI.getProviders();
      setProviders(updatedProviders);
      toast.success(`提供商 ${provider.name} ${enabled ? '已启用' : '已禁用'}`);
    } catch (error) {
      console.error('Failed to toggle provider:', error);
      toast.error(`切换提供商状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  };

  // 切换模型启用状态
  const handleToggleModel = async (modelId: string, enabled: boolean) => {
    try {
      // 解析modelId为数字
      const numericModelId = parseInt(modelId, 10);
      if (isNaN(numericModelId)) {
        throw new Error(`Model ID ${modelId} is not numeric`);
      }

      // 调用API切换模型状态
      await ModelSettingsAPI.toggleModelEnabled(numericModelId, enabled);
      
      // 更新本地状态
      setModels(prev => prev.map(model => 
        model.id === modelId 
          ? { ...model, is_available: enabled }
          : model
      ));
      
      // 查找模型名称用于提示
      const model = models.find(m => m.id === modelId);
      const modelName = model ? model.name : `模型 ${modelId}`;
      
      toast.success(`${modelName} ${enabled ? '已启用' : '已禁用'}`);
    } catch (error) {
      console.error('Failed to toggle model:', error);
      toast.error(`切换模型状态失败: ${error instanceof Error ? error.message : '未知错误'}`);
    }
  };

  // 更新全局能力分配
  const handleUpdateGlobalCapability = async (capability: string, provider_key: string, model_id: string) => {
    setIsLoading(true)
    try {
      // 解析model_id为数字（后端API需要）
      const numericModelId = parseInt(model_id, 10)
      if (isNaN(numericModelId)) {
        throw new Error(`Model ID ${model_id} is not numeric`)
      }
      
      // 调用API分配全局能力
      await ModelSettingsAPI.assignGlobalCapability(capability, numericModelId)
      
      // 更新状态
      setGlobalCapabilities(prev => {
        const filtered = prev.filter(gc => gc.capability !== capability)
        return [...filtered, { capability, provider_key, model_id }]
      })
      toast.success(`${capability} 能力分配更新成功`)
    } catch (error) {
      console.error("Failed to update global capability:", error)
      toast.error(`能力分配更新失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setIsLoading(false)
    }
  }

  if (!initialized) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div>
        <p className="text-muted-foreground mt-1">
          先到最下方配置服务商和模型，然后在上方分配给具体场景。
        </p>
      </div>
      <GlobalCapabilitySection
        providers={providers}
        models={models}
        globalCapabilities={globalCapabilities}
        onUpdateGlobalCapability={handleUpdateGlobalCapability}
      />
      <Separator />
      <div>
        <p className="text-muted-foreground mt-1">
          在这里管理您的AI模型提供商，以及测试他们提供的模型各有什么能力。
        </p>
      </div>
      <Tabs defaultValue={providers.length > 0 ? providers[0].key : "empty"} orientation="vertical" className="flex flex-row gap-1">
        <TabsList className="flex flex-col h-fit w-48 gap-1">
          {providers.map(provider => (
              <TabsTrigger 
                key={provider.key}
                value={provider.key} 
                className="w-full justify-start text-left data-[state=active]:bg-background data-[state=active]:text-foreground"
              >
                <div className="flex items-center gap-2 w-full">
                  <Settings className="w-4 h-4 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{provider.name}</div>
                    <div className="text-xs text-muted-foreground truncate">
                      {provider.is_enabled ? "已启用" : "已禁用"}
                    </div>
                  </div>
                </div>
              </TabsTrigger>
            ))
          }
          <AddProviderEmptyState onAddProvider={handleAddProvider} />
        </TabsList>
        {providers.map(provider => (
            <TabsContent key={provider.key} value={provider.key} className="m-0 mt-0">
              <ProviderDetailSection
                provider={provider}
                models={models.filter(m => m.provider === provider.key)}
                availableCapabilities={availableCapabilities}
                onToggleProvider={handleToggleProvider}
                onDiscoverModels={handleDiscoverModels}
                onConfirmModelCapability={handleConfirmModelCapability}
                onToggleModel={handleToggleModel}
                onDeleteProvider={handleDeleteProvider}
                isLoading={isLoading}
              />
            </TabsContent>
          ))
        }
      </Tabs>
    </div>
  )
}

export default SettingsAIModels
