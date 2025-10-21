import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
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
} from '@/components/ui/alert-dialog';
import { Loader2, Download, Trash2, CheckCircle, Cpu, HardDrive } from 'lucide-react';
import { useBuiltinModels, BuiltinModel } from '@/hooks/useBuiltinModels';
import { useBridgeEvents } from '@/hooks/useBridgeEvents';
import { toast } from 'sonner';

interface BuiltinModelsTabProps {
  onModelDownloaded?: (modelId: string) => void;
}

/**
 * 内置模型管理标签页
 * 显示内置 MLX-VLM 模型列表,提供下载、删除等功能
 */
export function BuiltinModelsTab({ onModelDownloaded }: BuiltinModelsTabProps) {
  const {
    models,
    serverStatus,
    loading,
    downloadModel,
    deleteModel,
    downloadStates,  // 直接使用 downloadStates 而不是 getDownloadState
    updateDownloadProgress,
    markDownloadCompleted,
    markDownloadFailed,
  } = useBuiltinModels();

  // 监听 bridge events 更新下载进度
  useBridgeEvents({
    'model-download-progress': (payload) => {
      const { model_name, percentage } = payload;
      const progress = percentage as number || 0;
      updateDownloadProgress(model_name as string, progress);
    },
    'model-download-completed': async (payload) => {
      const { model_name } = payload;
      markDownloadCompleted(model_name as string);
      toast.success(`Model file download completed: ${model_name}`);
      
      // 🎯 自动分配能力逻辑
      try {
        const response = await fetch(`http://127.0.0.1:60315/models/builtin/${model_name}/auto-assign`, {
          method: 'POST',
        });
        
        const result = await response.json();
        
        if (result.success) {
          const assignedCount = result.assigned_capabilities?.length || 0;
          
          if (assignedCount > 0) {
            // 新手场景: 自动分配了能力
            toast.success(
              `Model ready! Auto-assigned ${assignedCount} capabilities. Check scene configuration for details.`,
              { duration: 5000 }
            );
          } else {
            // 熟手场景: 已有配置，不自动覆盖
            toast.info(
              'Model ready! You can manually assign it in scene configuration.',
              { duration: 4000 }
            );
          }
        } else {
          // 自动分配失败，但模型已下载
          toast.warning(
            'Model downloaded successfully, but auto-assignment failed. Please configure manually.',
            { duration: 4000 }
          );
        }
      } catch (error) {
        console.error('Auto-assign failed:', error);
        toast.warning(
          'Model downloaded successfully. Please configure in scene settings.',
          { duration: 4000 }
        );
      }
      
      // 触发回调,用于其他逻辑
      if (onModelDownloaded) {
        onModelDownloaded(model_name as string);
      }
    },
    'model-download-failed': (payload) => {
      const { model_name, error_message } = payload;
      markDownloadFailed(model_name as string, error_message as string);
      toast.error(`Model download failed: ${error_message}`);
    }
  }, { showToasts: false, logEvents: true });

  const handleDownload = async (modelId: string) => {
    await downloadModel(modelId);
  };

  const handleDelete = async (modelId: string) => {
    await deleteModel(modelId);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 标题说明 */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5" />
          <h3 className="text-lg font-semibold">Built-in MLX Models</h3>
          <Badge variant="secondary">Apple MLX</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Use Apple MLX framework to run small vision-language models locally without external services.
          <br />
          Downloaded models can be used directly in scene configuration.
        </p>
      </div>

      {/* 服务器状态 */}
      {serverStatus.running && (
        <Card className="border-green-200 bg-green-50 dark:bg-green-950/20">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle className="w-4 h-4 text-green-600" />
              <span className="text-green-900 dark:text-green-100">
                Server running
                {serverStatus.loaded_model && ` - Loaded: ${serverStatus.loaded_model}`}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 模型列表 */}
      <div className="space-y-3">
        {models.map((model) => {
          const downloadState = downloadStates[model.model_id] || {
            downloading: false,
            progress: 0,
            error: null,
            completed: false
          };
          
          return (
            <ModelCard
              key={model.model_id}
              model={model}
              downloadState={downloadState}
              onDownload={handleDownload}
              onDelete={handleDelete}
            />
          );
        })}
      </div>
    </div>
  );
}

interface ModelCardProps {
  model: BuiltinModel;
  downloadState: {
    downloading: boolean;
    progress: number;
    error: string | null;
  };
  onDownload: (modelId: string) => void;
  onDelete: (modelId: string) => void;
}

/**
 * 单个模型卡片
 */
function ModelCard({ model, downloadState, onDownload, onDelete }: ModelCardProps) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const formatSize = (mb: number) => {
    if (mb >= 1024) {
      return `${(mb / 1024).toFixed(1)} GB`;
    }
    return `${mb} MB`;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="text-base">{model.display_name}</CardTitle>
            <CardDescription>{model.description}</CardDescription>
          </div>
          {model.downloaded && (
            <Badge variant="default" className="bg-green-600">
              <CheckCircle className="w-3 h-3 mr-1" />
              Downloaded
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* 模型信息 */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">Size:</span>
            <span className="font-medium">{formatSize(model.size_mb)}</span>
          </div>
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-muted-foreground" />
            <span className="text-muted-foreground">Capabilities:</span>
            <span className="font-medium">{model.capabilities.length} items</span>
          </div>
        </div>

        {/* 能力标签 */}
        <div className="flex flex-wrap gap-2">
          {model.capabilities.map((cap) => (
            <Badge key={cap} variant="outline" className="text-xs">
              {cap}
            </Badge>
          ))}
        </div>

        {/* 下载进度 */}
        {!model.downloaded && downloadState.downloading && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Downloading...</span>
              <span className="font-medium">{Math.round(downloadState.progress)}%</span>
            </div>
            <Progress value={downloadState.progress} className="h-2" />
          </div>
        )}

        {/* 错误提示 */}
        {!model.downloaded && downloadState.error && (
          <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">
            {downloadState.error}
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex items-center gap-2">
          {!model.downloaded ? (
            <Button
              onClick={() => onDownload(model.model_id)}
              disabled={downloadState.downloading}
              className="flex-1"
            >
              {downloadState.downloading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Downloading...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4 mr-2" />
                  Download Model
                </>
              )}
            </Button>
          ) : (
            <>
              <div className="flex-1 text-sm text-muted-foreground">
                Ready, can be used in scene configuration
              </div>
              <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Trash2 className="w-4 h-4 mr-2" />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Confirm Model Deletion?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will delete the model file ({formatSize(model.size_mb)}), freeing up disk space.
                      You'll need to re-download it to use again.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => {
                        onDelete(model.model_id);
                        setShowDeleteDialog(false);
                      }}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </>
          )}
        </div>

        {/* 本地路径(仅调试用) */}
        {model.downloaded && model.local_path && (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer hover:underline">View Storage Path</summary>
            <p className="mt-1 p-2 bg-muted rounded font-mono break-all">{model.local_path}</p>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
