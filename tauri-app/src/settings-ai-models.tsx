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
  SearchCheck,
  ExternalLinkIcon,
  Cpu,
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
  source_type?: string  // 模型来源类型: builtin, configurable, vip
  config: Record<string, any>
  is_enabled: boolean
  is_user_added?: boolean  // 是否为用户添加的提供商
  support_discovery?: boolean // 是否支持模型发现
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
  structured_output: boolean
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
  required_capabilities: string[]
  icon?: React.ReactNode
}

// 业务场景定义
const BUSINESS_SCENES: BusinessScene[] = [
  {
    key: "SCENE_FILE_TAGGING",
    required_capabilities: ["structured_output"],
    icon: <Settings className="w-4 h-4" />
  },
  {
    key: "SCENE_MULTIVECTOR", 
    required_capabilities: ["vision"],
    icon: <Settings className="w-4 h-4" />
  },
  {
    key: "SCENE_MULTIMODAL_ANSWER_SYNTHESIS",
    required_capabilities: ["text", "vision", "tool_use"],
    icon: <Settings className="w-4 h-4" />
  },
  {
    key: "SCENE_KNOWLEDGE_FRAGMENT_DESENSITIZATION",
    required_capabilities: ["text"],
    icon: <Settings className="w-4 h-4" />
  },
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
        structured_output: capabilitiesData.includes('structured_output') || capabilitiesData.includes('STRUCTURED_OUTPUT')
      }
    }
    
    // 如果是键值对格式（新格式），直接使用并提供默认值
    return {
      text: capabilitiesData?.text ?? false,
      vision: capabilitiesData?.vision ?? false,
      tool_use: capabilitiesData?.tool_use ?? false,
      structured_output: capabilitiesData?.structured_output ?? false
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
        source_type: config.source_type,  // 添加 source_type 字段
        support_discovery: config.support_discovery,
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
          {t("SETTINGS.aimodels.scene-config")}
        </CardTitle>
        <CardDescription>
          {t("SETTINGS.aimodels.scene-config-description")}
          {!hasConfiguredProviders && t("SETTINGS.aimodels.please-configure-model-provider")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!hasConfiguredProviders ? (
          <div className="text-center py-8 text-muted-foreground">
            <Settings className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>{t("SETTINGS.aimodels.please-configure-model-provider2")}</p>
            <p className="text-sm mt-1">{t("SETTINGS.aimodels.please-configure-model-provider3")}</p>
          </div>
        ) : (
          BUSINESS_SCENES.map(scene => {
            const completeness = getSceneCompleteness(scene)
            const sceneName = t(`SETTINGS.aimodels.business-scene.${scene.key}.name`)
            const sceneDescription = t(`SETTINGS.aimodels.business-scene.${scene.key}.description`)
            return (
              <div key={scene.key} className="border rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-start gap-3">
                    {scene.icon}
                    <div className="flex-1">
                      <h3 className="font-medium flex items-center gap-2">
                        {sceneName}
                        {completeness.percentage === 100 ? (
                          <Badge variant="default" className="text-xs">
                            <CheckCircle className="w-3 h-3 mr-1" />
                            {t("SETTINGS.aimodels.config-completed")}
                          </Badge>
                        ) : completeness.assigned > 0 ? (
                          <Badge variant="secondary" className="text-xs">
                            <AlertCircle className="w-3 h-3 mr-1" />
                            {completeness.percentage}% {t("SETTINGS.aimodels.config-completed-description")}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">
                            <XCircle className="w-3 h-3 mr-1" />
                            {t("SETTINGS.aimodels.config-not-completed")}
                          </Badge>
                        )}
                      </h3>
                      <p className="text-sm text-muted-foreground mt-1">
                        {sceneDescription}
                      </p>
                      
                      {/* 进度条 */}
                      {completeness.total > 0 && (
                        <div className="mt-2">
                          <div className="flex justify-between text-xs text-muted-foreground mb-1">
                            <span>{t("SETTINGS.aimodels.config-progress")}</span>
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
                  <div className="text-sm font-medium">{t("SETTINGS.aimodels.required-capability-config")}：</div>
                  {scene.required_capabilities.map(capability => {
                    const assignment = getCapabilityAssignment(capability)
                    const availableModels = getAvailableModelsForCapability(capability)
                    const hasModels = availableModels.length > 0
                    const isAssigned = assignment !== undefined
                    
                    return (
                      <div key={capability} className="flex items-center justify-between p-3 bg-muted/50 rounded">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{t(`SETTINGS.aimodels.ModelCapability.${capability.toUpperCase()}`)}</Badge>
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
                              if (modelId === "0") {
                                // 取消关联：传递特殊值
                                onUpdateGlobalCapability(capability, "", "0")
                              } else {
                                const model = models.find(m => m.id === modelId)
                                if (model) {
                                  onUpdateGlobalCapability(capability, model.provider, modelId)
                                }
                              }
                            }}
                          >
                            <SelectTrigger className="w-md">
                              <SelectValue placeholder={t("SETTINGS.aimodels.select-model")} />
                            </SelectTrigger>
                            <SelectContent>
                              {/* 未分配选项 - 放在最顶部 */}
                              {/* <SelectItem value="0" className="text-muted-foreground italic">
                                <div className="flex items-center gap-2">
                                  <XCircle className="w-3 h-3" />
                                  {t("SETTINGS.aimodels.unassigned")}
                                </div>
                              </SelectItem> */}
                              
                              {/* 分隔线 */}
                              {/* {availableModels.length > 0 && (
                                <div className="border-t my-1" />
                              )} */}
                              
                              {/* 可用模型列表 */}
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
                            {t("SETTINGS.aimodels.please-configure-model-provider4", {capability: t(`SETTINGS.aimodels.ModelCapability.${capability.toUpperCase()}`)})}
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
  const { t } = useTranslation();

  const handleApiKeyChange = async (newApiKey: string) => {
    if (newApiKey !== provider.api_key) {
      try {
        // 更新API密钥
        const providerId = typeof provider.id === 'string' ? parseInt(provider.id) : provider.id;
        await ModelSettingsAPI.updateProvider(providerId, {
          ...provider,
          api_key: newApiKey
        });
        toast.success('API Key updated successfully');
      } catch (error) {
        console.error('Failed to update API key:', error);
        toast.error('API Key update failed');
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
      toast.success(`Proxy ${checked ? 'enabled' : 'disabled'} successfully`);
    } catch (error) {
      console.error('Failed to update proxy setting:', error);
      toast.error('Proxy setting update failed');
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
          <Label className="text-xs font-medium text-muted-foreground">{t('SETTINGS.aimodels.get-key')}</Label>
          <div>
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs text-primary hover:underline"
              onClick={() => provider.get_key_url && openUrl(provider.get_key_url)}
            >
              {t('SETTINGS.aimodels.go-to-get-api-key')}
              <ExternalLinkIcon className="w-4 h-4 inline-block ml-1" />
            </Button>
          </div>
        </div>
      )}

      {/* 代理设置 */}
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium text-muted-foreground">{t('SETTINGS.aimodels.use-proxy')}</Label>
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
  const { t } = useTranslation();

  const handleAddProvider = () => {
    if (!newProvider.name.trim()) {
      toast.error(t('SETTINGS.aimodels.enter-provider-name'))
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
          <Button disabled={true}>
            <Plus className="w-4 h-4 mr-2" />
            {t('SETTINGS.aimodels.add-provider')}
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('SETTINGS.aimodels.add-provider')}</DialogTitle>
            <DialogDescription>
              {t('SETTINGS.aimodels.add-provider-description')}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <Label htmlFor="provider-name">{t('SETTINGS.aimodels.provider-name')} *</Label>
              <Input
                id="provider-name"
                value={newProvider.name}
                onChange={(e) => setNewProvider(prev => ({ ...prev, name: e.target.value }))}
                placeholder="exameple: OpenAI / Claude"
                className="mt-1"
              />
            </div>
            
            <div>
              <Label htmlFor="provider-desc">{t('SETTINGS.aimodels.provider-description-optional')}</Label>
              <Input
                id="provider-desc"
                value={newProvider.description}
                onChange={(e) => setNewProvider(prev => ({ ...prev, description: e.target.value }))}
                placeholder={t('SETTINGS.aimodels.provider-description-optional')}
                className="mt-1"
              />
            </div>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddDialog(false)}>
              {t('SETTINGS.aimodels.cancel')}
            </Button>
            <Button onClick={handleAddProvider} disabled={!newProvider.name.trim()}>
              {t('SETTINGS.aimodels.add')}
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
  // onToggleProvider,
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
      toast.error(`Can't delete ${provider.name}， ${models.length} models are in use`)
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
              {/* <div className="flex items-center gap-2">
                <Switch
                  checked={provider.is_enabled}
                  onCheckedChange={(checked) => onToggleProvider(provider.key, checked)}
                  disabled={isLoading}
                />
                <span className="text-sm text-muted-foreground">
                  {provider.is_enabled ? "Enabled" : "Disabled"}
                </span>
              </div>
              {models.length > 0 && (
                <Badge variant="outline" className="text-xs">
                  {availableModels.length}/{models.length} Available
                </Badge>
              )} */}
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
                title="Delete Provider"
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
              disabled={isLoading || !provider.support_discovery}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4 mr-2" />
              )}
              {t('SETTINGS.aimodels.discover-models')}
            </Button>
        </div>
        {models.length > 0 && (
          <div className="mt-0 space-y-4">
            <div className="text-sm font-medium">
              {t('SETTINGS.aimodels.model-list')}  ({availableModels.length}/{models.length})available:
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
                              {/* <BadgeCheckIcon className={`${hasCapability ? '' : 'hidden'}`} /> */}
                              <BadgeCheckIcon />
                              {t(`SETTINGS.aimodels.ModelCapability.${cap.toUpperCase()}`)}
                            </Badge>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onConfirmModelCapability(model.id)}
                      disabled={isLoading}
                      title={t('SETTINGS.aimodels.test-model-capability')}
                    >
                      {isLoading ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <SearchCheck className="w-3 h-3" />
                      )}
                      {t('SETTINGS.aimodels.test-model-capability')}
                    </Button>
                    <Switch
                      id={model.id}
                      checked={model.is_available}
                      onCheckedChange={(checked) => onToggleModel(model.id, checked)}
                    />
                    <Label htmlFor={model.id}>{model.is_available ? t('SETTINGS.aimodels.enabled') : t('SETTINGS.aimodels.disabled')}</Label>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {models.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <RefreshCw className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>{t('SETTINGS.aimodels.no-models')}</p>
            <p className="text-sm mt-1">{t('SETTINGS.aimodels.no-models-details')}</p>
          </div>
        )}
      </CardContent>
      
      {/* 删除确认对话框 */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('SETTINGS.aimodels.delete-provider-confirmation')}</DialogTitle>
            <DialogDescription>
              {t('SETTINGS.aimodels.delete-provider-confirmation-details', { providerName: provider.name })}
            </DialogDescription>
          </DialogHeader>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              {t('SETTINGS.aimodels.cancel')}
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleConfirmDelete}
            >
              {t('SETTINGS.aimodels.delete')}
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
  const { t } = useTranslation();

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
      toast.success("Provider deleted successfully")
    } catch (error) {
      console.error("Failed to delete provider:", error)
      toast.error(`Failed to delete provider: ${error instanceof Error ? error.message : 'Unknown error'}`)
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
      
      toast.success(`${discoveredModels.length} discoverd，${allProviderModels.length} total`)
    } catch (error) {
      console.error('Failed to discover models:', error)
      toast.error(`Failed to discover models: ${error instanceof Error ? error.message : 'Unknown error'}`)
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
      
      // 更新模型状态中的能力信息
      setModels(prev => prev.map(model => 
        model.id === modelId 
          ? { ...model, capabilities: capabilities }
          : model
      ))
      
      // 计算能力数量
      const capabilityCount = Object.values(capabilities).filter(Boolean).length
      toast.success(`model capability test completed, ${capabilityCount} capabilities found`)

    } catch (error) {
      console.error("Failed to test model capability:", error)
      toast.error(`Failed to test model capability: ${error instanceof Error ? error.message : 'Unknown error'}`)
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
      toast.success(`Provider ${provider.name} ${enabled ? 'enabled' : 'disabled'}`);
    } catch (error) {
      console.error('Failed to toggle provider:', error);
      toast.error(`Failed to toggle provider status: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
      toast.error(`Failed to toggle model status: ${error instanceof Error ? error.message : 'Unknown error'}`);
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
      toast.success(`${capability} capability assignment updated successfully`)
    } catch (error) {
      console.error("Failed to update global capability:", error)
      toast.error(`Failed to update capability assignment: ${error instanceof Error ? error.message : 'Unknown error'}`)
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
    <div className="container mx-auto px-6">
      <div>
        <p className="text-muted-foreground mt-1">
          {t('SETTINGS.aimodels.description2')}
        </p>
      </div>
      <GlobalCapabilitySection
        providers={providers}
        models={models}
        globalCapabilities={globalCapabilities}
        onUpdateGlobalCapability={handleUpdateGlobalCapability}
      />
      <Separator className="my-12" />
      <div>
        <p className="text-muted-foreground mt-1">
          {t('SETTINGS.aimodels.description3')}
        </p>
      </div>
      <Tabs defaultValue={providers.length > 0 ? providers[0].key : "empty"} orientation="vertical" className="flex flex-row gap-1">
        <TabsList className="flex flex-col h-fit w-48 gap-1">
          {providers.map(provider => {
            const isBuiltin = provider.source_type === 'builtin';
            const providerModels = models.filter(m => m.provider === provider.key);
            const availableModels = providerModels.filter(m => m.is_available);
            const shouldBeBold = isBuiltin || availableModels.length > 0;
            
            return (
              <TabsTrigger 
                key={provider.key}
                value={provider.key} 
                className="w-full justify-start text-left data-[state=active]:bg-background data-[state=active]:text-foreground"
              >
                <div className="flex items-center gap-2 w-full">
                  {isBuiltin ? (
                    <Cpu className="w-4 h-4 flex-shrink-0 text-primary" />
                  ) : (
                    <Settings className="w-4 h-4 flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1">
                      <span className={`${shouldBeBold ? 'font-bold' : 'font-medium'} truncate`}>
                        {provider.name}
                      </span>
                      {isBuiltin && (
                        <Badge variant="secondary" className="text-xs px-1 py-0 h-4">Built-in</Badge>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground truncate">
                      {availableModels.length}/{providerModels.length} Available
                    </div>
                  </div>
                </div>
              </TabsTrigger>
            );
          })}
          <AddProviderEmptyState onAddProvider={handleAddProvider} />
        </TabsList>
        {providers.map(provider => {
          const isBuiltin = provider.source_type === 'builtin';
          return (
            <TabsContent key={provider.key} value={provider.key} className="m-0 mt-0">
              {isBuiltin ? (
                <div className="p-6 bg-blue-50 dark:bg-blue-950/20 rounded-lg border border-blue-200 dark:border-blue-800">
                  <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-2">
                    Built-in MLX-VLM Models
                  </h3>
                  <p className="text-sm text-blue-700 dark:text-blue-300 mb-4">
                    Built-in model (mlx-community/Qwen3-VL-4B-Instruct-3bit) is automatically enabled, supporting local visual understanding capabilities.
                  </p>
                  <ul className="text-sm text-blue-600 dark:text-blue-400 space-y-2">
                    <li>✅ On-demand loading: Automatically loads the model upon first use</li>
                    <li>✅ Intelligent unloading: Automatically unloads after switching all capabilities to other models</li>
                    <li>✅ Priority queue: Session requests take precedence, batch tasks are queued</li>
                    <li>✅ Image preprocessing: Automatically compresses large images to speed up inference</li>
                  </ul>
                </div>
              ) : (
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
              )}
            </TabsContent>
          );
        })}
      </Tabs>
    </div>
  )
}

export default SettingsAIModels
