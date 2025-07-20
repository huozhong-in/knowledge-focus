import { useState, useEffect, useMemo, useCallback } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
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
import { toast } from "sonner"
import { Loader2 } from "lucide-react"

const API_BASE_URL = "http://127.0.0.1:60315"

// --- Type Definitions ---
interface Model {
  id: string
  name: string
}

interface ProviderConfig {
  provider_type: "ollama" | "lm_studio" | "openai_compatible"
  provider_name: string
  api_endpoint: string
  api_key: string | null
  enabled: boolean
  available_models: Model[] | null
  // UI state
  isDiscovering?: boolean
  isSaving?: boolean
}

type ModelRole = "base" | "vision" | "embedding" | "reranking"

interface RoleAssignment {
  provider_type?: string
  model_id?: string
}

// --- Helper Components & Functions ---

const roleLabels: Record<ModelRole, string> = {
  base: "基础模型",
  vision: "视觉模型",
  embedding: "嵌入模型",
  reranking: "重排序模型",
}

// --- Main Component ---

function SettingsLocalModels() {
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [roleAssignments, setRoleAssignments] = useState<
    Record<ModelRole, RoleAssignment>
  >({
    base: {},
    vision: {},
    embedding: {},
    reranking: {},
  })
  const [isLoading, setIsLoading] = useState(true)

  const fetchInitialData = useCallback(async () => {
    setIsLoading(true)
    try {
      const [configsRes, rolesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/local-models/configs`),
        fetch(`${API_BASE_URL}/local-models/roles`),
      ])

      if (!configsRes.ok || !rolesRes.ok) {
        throw new Error("获取模型配置失败")
      }

      const configsData = await configsRes.json()
      const rolesData = await rolesRes.json()

      if (configsData.success) {
        setProviders(configsData.data)
      } else {
        throw new Error(configsData.message || "获取服务商配置失败")
      }

      if (rolesData.success) {
        setRoleAssignments(rolesData.data)
      } else {
        throw new Error(rolesData.message || "获取角色分配失败")
      }
    } catch (error) {
      toast.error("加载失败", {
        description:
          error instanceof Error ? error.message : "无法连接到后端服务。",
      })
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchInitialData()
  }, [fetchInitialData])

  const handleProviderChange = (
    providerType: string,
    field: keyof ProviderConfig,
    value: any
  ) => {
    setProviders((prev) =>
      prev.map((p) =>
        p.provider_type === providerType ? { ...p, [field]: value } : p
      )
    )
  }

  const handleSaveChanges = async (providerType: string) => {
    const provider = providers.find((p) => p.provider_type === providerType)
    if (!provider) return

    setProviders((prev) =>
      prev.map((p) =>
        p.provider_type === providerType ? { ...p, isSaving: true } : p
      )
    )

    try {
      const response = await fetch(
        `${API_BASE_URL}/local-models/configs/${providerType}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_endpoint: provider.api_endpoint,
            api_key: provider.api_key,
            enabled: provider.enabled,
            available_models: provider.available_models, // Persist the discovered models
          }),
        }
      )
      const data = await response.json()
      if (!data.success) throw new Error(data.message)

      toast.success("保存成功", {
        description: `${provider.provider_name} 的配置已更新。`,
      })
    } catch (error) {
      toast.error("保存失败", {
        description: error instanceof Error ? error.message : "未知错误",
      })
    } finally {
      setProviders((prev) =>
        prev.map((p) =>
          p.provider_type === providerType ? { ...p, isSaving: false } : p
        )
      )
    }
  }

  const handleDiscoverModels = async (providerType: string) => {
    setProviders((prev) =>
      prev.map((p) =>
        p.provider_type === providerType ? { ...p, isDiscovering: true } : p
      )
    )
    try {
      const response = await fetch(
        `${API_BASE_URL}/local-models/configs/${providerType}/discover`,
        {
          method: "POST",
        }
      )
      const data = await response.json()
      if (!data.success) throw new Error(data.message)

      // Update the specific provider with the new list of models
      setProviders((prev) =>
        prev.map((p) =>
          p.provider_type === providerType
            ? { ...p, available_models: data.data.available_models }
            : p
        )
      )

      toast.success("检测成功", {
        description: `找到了 ${
          data.data.available_models?.length || 0
        } 个模型。`,
      })
    } catch (error) {
      toast.error("检测失败", {
        description:
          error instanceof Error
            ? error.message
            : "请检查API地址和密钥是否正确。",
      })
    } finally {
      setProviders((prev) =>
        prev.map((p) =>
          p.provider_type === providerType ? { ...p, isDiscovering: false } : p
        )
      )
    }
  }

  const handleRoleChange = async (role: ModelRole, value: string) => {
    if (!value) return // Do nothing if placeholder is selected

    const [provider_type, model_id] = value.split("::")
    const provider = providers.find((p) => p.provider_type === provider_type)
    const model = provider?.available_models?.find((m) => m.id === model_id)

    if (!model) return

    const model_info = {
      provider_type,
      model_id,
      model_name: model.name,
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/local-models/roles/${role}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(model_info),
        }
      )
      const data = await response.json()
      if (!data.success) throw new Error(data.message)

      setRoleAssignments((prev) => ({ ...prev, [role]: model_info }))
      toast.success("角色已分配", {
        description: `${roleLabels[role]} 已指定为 ${model.name}。`,
      })
    } catch (error) {
      toast.error("分配失败", {
        description: error instanceof Error ? error.message : "未知错误",
      })
    }
  }

  const allModels = useMemo(() => {
    return providers.flatMap(
      (p) =>
        p.available_models?.map((m) => ({
          ...m,
          provider_type: p.provider_type,
          provider_name: p.provider_name,
        })) || []
    )
  }, [providers])

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-6 p-6 pt-0">
      {/* Description Section */}
      <Card>
        <CardHeader>
          <CardTitle>本地大模型</CardTitle>
          <CardDescription>
            本地大模型在您的设备上直接运行，为您提供最高级别的数据隐私保护。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
            <li>
              <strong>智力程度：</strong>{" "}
              模型的能力取决于您选择的具体模型和您的硬件配置。
            </li>
            <li>
              <strong>算力要求：</strong>{" "}
              运行本地模型通常需要较强的CPU或GPU算力。
            </li>
            <li>
              <strong>数据隐私：</strong>{" "}
              所有数据处理均在本地完成，数据不会离开您的设备。
            </li>
          </ul>
        </CardContent>
      </Card>

      {/* Role Assignment Section */}
      <Card>
        <CardHeader>
          <CardTitle>功能角色分配</CardTitle>
          <CardDescription>
            为核心AI功能选择默认使用的模型。选择会立即保存。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {(Object.keys(roleLabels) as ModelRole[]).map((role) => (
            <div key={role} className="space-y-2">
              <Label>{roleLabels[role]}</Label>
              <Select
                value={
                  roleAssignments[role]?.model_id
                    ? `${roleAssignments[role].provider_type}::${roleAssignments[role].model_id}`
                    : ""
                }
                onValueChange={(value) => handleRoleChange(role, value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder={`选择一个模型...`} />
                </SelectTrigger>
                <SelectContent>
                  {allModels.length > 0 ? (
                    allModels.map((model) => (
                      <SelectItem
                        key={`${model.provider_type}-${model.id}`}
                        value={`${model.provider_type}::${model.id}`}
                      >
                        {model.name} ({model.provider_name})
                      </SelectItem>
                    ))
                  ) : (
                    <div className="px-2 py-1.5 text-sm text-muted-foreground">
                      请先检测可用模型
                    </div>
                  )}
                </SelectContent>
              </Select>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* API Configuration Section */}
      <div className="space-y-4">
        <h3 className="text-xl font-semibold leading-none tracking-tight">
          API 配置
        </h3>
        <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-3 items-start">
          {providers.map((provider) => (
            <ProviderConfigCard
              key={provider.provider_type}
              provider={provider}
              onChange={handleProviderChange}
              onSave={handleSaveChanges}
              onDiscover={handleDiscoverModels}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

interface ProviderCardProps {
  provider: ProviderConfig
  onChange: (
    providerType: string,
    field: keyof ProviderConfig,
    value: any
  ) => void
  onSave: (providerType: string) => void
  onDiscover: (providerType: string) => void
}

function ProviderConfigCard({
  provider,
  onChange,
  onSave,
  onDiscover,
}: ProviderCardProps) {
  const {
    provider_type,
    provider_name,
    api_endpoint,
    api_key,
    available_models,
    isDiscovering,
    isSaving,
  } = provider

  return (
    <Card>
      <CardHeader>
        <CardTitle>{provider_name}</CardTitle>
        <CardDescription>配置通过 {provider_name} 运行的模型。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="space-y-2">
          <Label htmlFor={`${provider_type}-api-endpoint`}>API 地址</Label>
          <Input
            id={`${provider_type}-api-endpoint`}
            placeholder="输入 API 地址"
            value={api_endpoint}
            onChange={(e) =>
              onChange(provider_type, "api_endpoint", e.target.value)
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${provider_type}-api-key`}>API 密钥</Label>
          <Input
            id={`${provider_type}-api-key`}
            type="password"
            placeholder="输入 API 密钥 (如果需要)"
            value={api_key || ""}
            onChange={(e) => onChange(provider_type, "api_key", e.target.value)}
          />
        </div>
        <div className="flex justify-between items-center gap-2">
          <Button
            onClick={() => onDiscover(provider_type)}
            disabled={isDiscovering || !api_endpoint}
            className="flex-1"
          >
            {isDiscovering ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : null}
            {isDiscovering ? "检测中..." : "检测可用模型"}
          </Button>
          <Button
            onClick={() => onSave(provider_type)}
            disabled={isSaving}
            variant="outline"
          >
            {isSaving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : null}
            保存
          </Button>
        </div>

        {available_models && available_models.length > 0 && (
          <div className="mt-4 space-y-4">
            <h5 className="font-medium">可用模型:</h5>
            <div className="space-y-2 pr-2">
              {available_models.map((model) => (
                <div
                  key={model.id}
                  className="p-3 border rounded-md bg-muted/50"
                >
                  <p className="font-semibold text-sm">{model.name}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default SettingsLocalModels
