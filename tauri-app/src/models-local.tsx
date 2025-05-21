import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox"; // Assuming this component exists

// Define a type for a model
interface Model {
  id: string;
  name: string;
  attributes: {
    vision: boolean;
    reasoning: boolean;
    networking: boolean;
    toolUse: boolean;
    embedding: boolean;
    reranking: boolean;
  };
}

// Define a type for API configuration state
interface ApiConfigState {
  apiKey: string;
  apiEndpoint: string;
  models: Model[];
  loadingModels: boolean;
}

function ModelsLocal() {
  const [ollamaConfig, setOllamaConfig] = useState<ApiConfigState>({
    apiKey: "",
    apiEndpoint: "http://localhost:11434/v1/",
    models: [],
    loadingModels: false,
  });

  const [lmStudioConfig, setLmStudioConfig] = useState<ApiConfigState>({
    apiKey: "",
    apiEndpoint: "http://localhost:1234/v1/",
    models: [],
    loadingModels: false,
  });

  const [openAIConfig, setOpenAIConfig] = useState<ApiConfigState>({
    apiKey: "",
    apiEndpoint: "",
    models: [],
    loadingModels: false,
  });

  // Mock function to fetch models - replace with actual API call
  const fetchModels = async (
    _config: ApiConfigState,
    setConfig: React.Dispatch<React.SetStateAction<ApiConfigState>>
  ) => {
    setConfig((prev) => ({ ...prev, loadingModels: true, models: [] }));
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 1500));
    const mockModels: Model[] = [
      { id: "model1", name: "Llama 3 8B", attributes: { vision: false, reasoning: true, networking: false, toolUse: true, embedding: true, reranking: false } },
      { id: "model2", name: "Mistral 7B", attributes: { vision: false, reasoning: true, networking: false, toolUse: false, embedding: true, reranking: false } },
      { id: "model3", name: "LLaVA (Vision)", attributes: { vision: true, reasoning: true, networking: false, toolUse: false, embedding: true, reranking: false } },
    ];
    setConfig((prev) => ({ ...prev, models: mockModels, loadingModels: false }));
  };

  const handleAttributeChange = (
    modelId: string,
    attribute: keyof Model['attributes'],
    value: boolean,
    configType: 'ollama' | 'lmStudio' | 'openAI'
  ) => {
    let setConfig;
    if (configType === 'ollama') setConfig = setOllamaConfig;
    else if (configType === 'lmStudio') setConfig = setLmStudioConfig;
    else setConfig = setOpenAIConfig;

    setConfig((prev) => ({
      ...prev,
      models: prev.models.map(model =>
        model.id === modelId
          ? { ...model, attributes: { ...model.attributes, [attribute]: value } }
          : model
      ),
    }));
  };


  const renderConfigCard = (
    title: string,
    description: string,
    config: ApiConfigState,
    setConfig: React.Dispatch<React.SetStateAction<ApiConfigState>>,
    configType: 'ollama' | 'lmStudio' | 'openAI'
  ) => {
    return (
      <div className="flex flex-col gap-4 p-4 rounded-md border bg-card">
        <h4 className="font-medium text-lg">{title}</h4>
        <p className="text-sm text-muted-foreground">{description}</p>
        
        <div className="space-y-2">
          <Label htmlFor={`${configType}-api-key`}>API 密钥</Label>
          <Input 
            id={`${configType}-api-key`}
            type="password" 
            placeholder="输入 API 密钥 (如果需要)" 
            value={config.apiKey}
            onChange={(e) => setConfig(prev => ({...prev, apiKey: e.target.value}))}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor={`${configType}-api-endpoint`}>API 地址</Label>
          <Input 
            id={`${configType}-api-endpoint`}
            placeholder="输入 API 地址" 
            value={config.apiEndpoint}
            onChange={(e) => setConfig(prev => ({...prev, apiEndpoint: e.target.value}))}
          />
        </div>
        
        <Button onClick={() => fetchModels(config, setConfig)} disabled={config.loadingModels}>
          {config.loadingModels ? "检测中..." : "检测"}
        </Button>

        {config.models.length > 0 && (
          <div className="mt-4 space-y-4">
            <h5 className="font-medium">可用模型:</h5>
            {config.models.map(model => (
              <div key={model.id} className="p-3 border rounded-md bg-muted/50">
                <p className="font-semibold mb-2">{model.name}</p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  {(Object.keys(model.attributes) as Array<keyof Model['attributes']>).map(attrKey => (
                    <div key={attrKey} className="flex items-center space-x-2">
                      <Checkbox
                        id={`${configType}-${model.id}-${attrKey}`}
                        checked={model.attributes[attrKey]}
                        onCheckedChange={(checked) => handleAttributeChange(model.id, attrKey, !!checked, configType)}
                      />
                      <Label htmlFor={`${configType}-${model.id}-${attrKey}`} className="capitalize text-xs">
                        {attrKey === 'vision' ? '视觉' : 
                         attrKey === 'reasoning' ? '推理' :
                         attrKey === 'networking' ? '内置联网' :
                         attrKey === 'toolUse' ? '工具使用' :
                         attrKey === 'embedding' ? '嵌入' : 
                         attrKey === 'reranking' ? '重排序' : attrKey}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-1 flex-col gap-6 p-6 pt-0">
      {/* Description Section */}
      <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-6">
        <h2 className="text-2xl font-semibold leading-none tracking-tight mb-4">本地大模型</h2>
        <p className="text-sm text-muted-foreground mb-2">
          本地大模型在您的设备上直接运行，为您提供最高级别的数据隐私保护。
        </p>
        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
          <li><strong>智力程度：</strong> 模型的能力取决于您选择的具体模型和您的硬件配置。一些先进的本地模型可以提供接近商业模型的体验。</li>
          <li><strong>算力要求：</strong> 运行本地模型通常需要较强的CPU或GPU算力。请确保您的设备满足所选模型的最低要求。</li>
          <li><strong>数据隐私：</strong> 所有数据处理均在本地完成，数据不会离开您的设备，确保了最高程度的隐私安全。</li>
        </ul>
      </div>

      {/* API Configuration Section */}
      <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-6">
        <h3 className="text-xl font-semibold leading-none tracking-tight mb-4">API 配置</h3>
        <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-3"> {/* Adjusted grid for better responsiveness */}
          {renderConfigCard("Ollama", "配置通过 Ollama 运行的本地模型。", ollamaConfig, setOllamaConfig, 'ollama')}
          {renderConfigCard("LM Studio", "配置通过 LM Studio 运行的本地模型。", lmStudioConfig, setLmStudioConfig, 'lmStudio')}
          {renderConfigCard("OpenAI 兼容 API", "配置兼容 OpenAI API 格式的本地模型服务。", openAIConfig, setOpenAIConfig, 'openAI')}
        </div>
      </div>
    </div>
  );
}

export default ModelsLocal;