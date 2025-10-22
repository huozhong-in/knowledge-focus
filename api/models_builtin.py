import json
import logging
import time
from pathlib import Path
from config import VLM_MODEL, singleton
from typing import Optional, List, Dict, Callable
from sqlalchemy import Engine
from huggingface_hub import snapshot_download
from tqdm import tqdm

logger = logging.getLogger(__name__)

# 支持的内置模型配置
BUILTIN_MODELS = {
    "qwen3-vl-4b": {
        "display_name": "Qwen3-VL 4B (3-bit)",
        "hf_model_id": VLM_MODEL,
        "description": "Small vision-language model suitable for local use",
        "capabilities": ["vision", "text", "structured_output", "tool_use"],
        "estimated_size_mb": 2590,
    }
}

@singleton
class ModelsBuiltin:
    """
    内置模型管理器
    负责 MLX-VLM 模型的下载、加载、卸载和服务器管理
    """
    
    def __init__(self, engine: Engine, base_dir: str):
        self.engine = engine
        self.base_dir = base_dir
        self.builtin_models_dir = Path(base_dir) / "builtin_models"
        self.builtin_models_dir.mkdir(parents=True, exist_ok=True)        
        # 跟踪已下载模型的实际路径
        # key: model_id (如 "qwen3-vl-4b"), value: 实际下载路径
        self.downloaded_models_paths: Dict[str, str] = {}
        self._load_downloaded_models_cache()
        logger.info(f"ModelsBuiltin initialized with base_dir: {base_dir}")
    
    def _load_downloaded_models_cache(self):
        """加载已下载模型的缓存信息"""
        cache_file = self.builtin_models_dir / ".downloaded_models.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    self.downloaded_models_paths = json.load(f)
                logger.info(f"Loaded {len(self.downloaded_models_paths)} cached model paths")
            except Exception as e:
                logger.warning(f"Failed to load model cache: {e}")
                self.downloaded_models_paths = {}
    
    def _save_downloaded_models_cache(self):
        """保存已下载模型的缓存信息"""
        cache_file = self.builtin_models_dir / ".downloaded_models.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.downloaded_models_paths, f, indent=2)
            logger.debug("Saved model cache")
        except Exception as e:
            logger.warning(f"Failed to save model cache: {e}")
    
    def is_model_downloaded(self, model_id: str) -> bool:
        """
        检查模型是否已下载
        
        Args:
            model_id: 模型ID (如 "qwen3-vl-4b")
            
        Returns:
            True 如果模型已下载
        """
        # 检查缓存中是否有记录
        if model_id not in self.downloaded_models_paths:
            return False
        
        # 验证路径是否仍然存在
        model_path = Path(self.downloaded_models_paths[model_id])
        if not model_path.exists():
            # 路径不存在，从缓存中移除
            del self.downloaded_models_paths[model_id]
            self._save_downloaded_models_cache()
            return False
        
        # logger.info(f"Model {model_id} is downloaded at: {model_path}")
        return True
    
    def get_model_path(self, model_id: str) -> Optional[str]:
        """
        获取已下载模型的实际路径
        
        Args:
            model_id: 模型ID
            
        Returns:
            模型路径，如果未下载则返回 None
        """
        if self.is_model_downloaded(model_id):
            return self.downloaded_models_paths[model_id]
        return None
    
    def get_downloaded_models(self) -> List[str]:
        """
        获取所有已下载的模型ID列表
        
        Returns:
            已下载模型的ID列表
        """
        downloaded = []
        
        for model_id in BUILTIN_MODELS.keys():
            if self.is_model_downloaded(model_id):
                downloaded.append(model_id)
        
        logger.info(f"Found {len(downloaded)} downloaded models: {downloaded}")
        return downloaded
    
    def get_supported_models(self) -> List[Dict]:
        """
        获取所有支持的内置模型信息
        
        Returns:
            模型信息列表，包含下载状态
        """
        models = []
        
        for model_id, config in BUILTIN_MODELS.items():
            is_downloaded = self.is_model_downloaded(model_id)
            model_info = {
                "model_id": model_id,
                "display_name": config["display_name"],
                "description": config["description"],
                "capabilities": config["capabilities"],
                "size_mb": config["estimated_size_mb"],
                "downloaded": is_downloaded,
                "path": self.get_model_path(model_id) if is_downloaded else None,
            }
            models.append(model_info)
        
        return models
    
    def download_model(
        self, 
        model_id: str, 
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> str:
        """
        下载指定的 MLX-VLM 模型到本地
        
        Args:
            model_id: 模型简称 (如 "qwen3-vl-4b")，对应 BUILTIN_MODELS 中的 key
            progress_callback: 进度回调函数（可选，用于测试），接收 {"progress": 0-100, "status": str, "message": str}
                              实际下载进度会通过 bridge_events 自动推送到前端
            
        Returns:
            下载后的本地模型路径
            
        Raises:
            ValueError: 如果模型ID不在支持列表中
            Exception: 下载失败
        """
        # 验证模型ID
        if model_id not in BUILTIN_MODELS:
            raise ValueError(f"不支持的模型ID: {model_id}. 支持的模型: {list(BUILTIN_MODELS.keys())}")
        
        model_config = BUILTIN_MODELS[model_id]
        hf_model_id = model_config["hf_model_id"]  # HuggingFace 的完整模型ID
        
        logger.info(f"开始下载模型: {model_id} (HF: {hf_model_id})")
        
        # 使用统一桥接器发送事件到前端
        from bridge_events import BridgeEventSender
        bridge_events = BridgeEventSender(source="models_builtin")
        
        # 定义进度报告器类
        class ProgressReporter(tqdm):
            """自定义进度报告器,将下载进度通过桥接事件报告给前端"""
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.callback = progress_callback
                self.bridge = bridge_events
                self.model_id = model_id  # 使用 model_id 而不是 display_name
                
            def update(self, n=1):
                super().update(n)
                if self.total:
                    progress_pct = int((self.n / self.total) * 100)
                    
                    # 通过统一桥接器发送进度到前端
                    self.bridge.model_download_progress(
                        model_name=self.model_id,  # 发送 model_id 以便前端匹配
                        current=self.n,
                        total=self.total,
                        message=f"正在下载 {self.desc or '文件'}: {progress_pct}%",
                        stage="downloading"
                    )
                    
                    # 如果提供了回调函数(用于测试),也调用它
                    if self.callback:
                        self.callback({
                            "progress": progress_pct,
                            "status": "downloading",
                            "message": f"正在下载 {self.desc or '文件'}: {progress_pct}%",
                            "current": self.n,
                            "total": self.total
                        })
        
        # 尝试多个镜像站点
        max_attempts_per_endpoint = 3
        endpoints = ['https://huggingface.co', 'https://hf-mirror.com']
        last_exception = None
        
        # 发送开始下载事件
        bridge_events.model_download_progress(
            model_name=model_id,  # 使用 model_id
            current=0,
            total=100,
            message=f"准备下载模型 {model_config['display_name']}...",
            stage="starting"
        )
        
        if progress_callback:
            progress_callback({
                "progress": 0,
                "status": "starting",
                "message": f"准备下载模型 {model_config['display_name']}..."
            })
        
        for endpoint in endpoints:
            for attempt in range(max_attempts_per_endpoint):
                try:
                    logger.info(f"尝试从 {endpoint} 下载 (第 {attempt + 1}/{max_attempts_per_endpoint} 次)")
                    
                    bridge_events.model_download_progress(
                        model_name=model_id,  # 使用 model_id
                        current=0,
                        total=100,
                        message=f"连接到 {endpoint}...",
                        stage="connecting"
                    )
                    
                    if progress_callback:
                        progress_callback({
                            "progress": 0,
                            "status": "connecting",
                            "message": f"连接到 {endpoint}..."
                        })
                    
                    # 使用 snapshot_download 下载模型
                    local_path = snapshot_download(
                        repo_id=hf_model_id,
                        cache_dir=str(self.builtin_models_dir),
                        tqdm_class=ProgressReporter,
                        allow_patterns=["*.safetensors", "*.json", "*.txt", "*.npz"],  # 下载必要文件
                        endpoint=endpoint,
                    )
                    
                    logger.info(f"模型下载成功: {local_path}")
                    
                    # 保存实际路径到缓存
                    self.downloaded_models_paths[model_id] = str(local_path)
                    self._save_downloaded_models_cache()
                    logger.info(f"Saved model path to cache: {model_id} -> {local_path}")
                    
                    # 通过统一桥接器发送完成事件
                    bridge_events.model_download_completed(
                        model_name=model_id,  # 使用 model_id
                        local_path=str(local_path),
                        message=f"模型 {model_config['display_name']} 下载完成"
                    )
                    
                    # 发送完成事件(回调)
                    if progress_callback:
                        progress_callback({
                            "progress": 100,
                            "status": "completed",
                            "message": f"模型 {model_config['display_name']} 下载完成",
                            "path": local_path
                        })
                    
                    return local_path
                    
                except Exception as e:
                    last_exception = e
                    error_msg = f"下载失败 (尝试 {attempt + 1}/{max_attempts_per_endpoint}，镜像: {endpoint}): {str(e)}"
                    logger.warning(error_msg, exc_info=True)
                    
                    if progress_callback:
                        progress_callback({
                            "progress": 0,
                            "status": "failed_attempt",
                            "message": error_msg,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts_per_endpoint,
                            "endpoint": endpoint
                        })
                    
                    # 短暂等待后重试
                    if attempt < max_attempts_per_endpoint - 1:
                        time.sleep(2)
            
            logger.error(f"镜像站 {endpoint} 所有尝试均失败")
        
        # 所有尝试都失败了
        final_error_msg = f"所有镜像站下载模型 {model_id} 均失败: {str(last_exception)}"
        logger.error(final_error_msg, exc_info=True)
        
        # 通过统一桥接器发送失败事件
        bridge_events.model_download_failed(
            model_name=model_id,  # 使用 model_id
            error_message=final_error_msg,
            details={"last_error": str(last_exception)}
        )
        
        if progress_callback:
            progress_callback({
                "progress": 0,
                "status": "failed",
                "message": final_error_msg,
                "error": str(last_exception)
            })
        
        raise Exception(final_error_msg)
    
    async def download_model_async(
        self, 
        model_id: str,
        mirror: str = "huggingface",
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> str:
        """
        异步下载指定的 MLX-VLM 模型（用于 Splash 页面）
        
        Args:
            model_id: 模型简称 (如 "qwen3-vl-4b")
            mirror: 镜像站点选择 ("huggingface" 或 "hf-mirror")
            progress_callback: 可选的进度回调函数（测试用）
            
        Returns:
            下载后的本地模型路径
            
        Raises:
            ValueError: 如果模型ID不在支持列表中
            Exception: 下载失败
        """
        import asyncio
        
        # 验证模型ID
        if model_id not in BUILTIN_MODELS:
            raise ValueError(f"不支持的模型ID: {model_id}")
        
        model_config = BUILTIN_MODELS[model_id]
        hf_model_id = model_config["hf_model_id"]
        
        logger.info(f"开始异步下载模型: {model_id} (镜像: {mirror})")
        
        from bridge_events import BridgeEventSender
        bridge_events = BridgeEventSender(source="models_builtin")
        
        # 镜像站点映射
        endpoint_map = {
            "huggingface": "https://huggingface.co",
            "hf-mirror": "https://hf-mirror.com"
        }
        endpoint = endpoint_map.get(mirror, endpoint_map["huggingface"])
        
        # 节流状态（每秒最多发送1次进度事件）
        last_progress_time = [0.0]  # 使用列表以便在闭包中修改
        
        # 定义节流的进度报告器
        class ThrottledProgressReporter(tqdm):
            """节流的进度报告器，避免过于频繁的事件推送"""
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.callback = progress_callback
                self.bridge = bridge_events
                self.model_id = model_id
                
            def update(self, n=1):
                super().update(n)
                current_time = time.time()
                
                # 节流：每秒最多发送1次
                if self.total and (current_time - last_progress_time[0] >= 1.0):
                    last_progress_time[0] = current_time
                    progress_pct = int((self.n / self.total) * 100)
                    
                    # 推送到前端
                    self.bridge.model_download_progress(
                        model_name=self.model_id,
                        current=self.n,
                        total=self.total,
                        message=f"下载中: {progress_pct}%",
                        stage="downloading"
                    )
                    
                    if self.callback:
                        self.callback({
                            "progress": progress_pct,
                            "status": "downloading",
                            "message": f"下载中: {progress_pct}%"
                        })
        
        # 发送开始下载事件
        bridge_events.model_download_progress(
            model_name=model_id,
            current=0,
            total=100,
            message=f"准备下载模型 {model_config['display_name']}...",
            stage="starting"
        )
        
        try:
            # 在线程池中运行同步的下载操作
            loop = asyncio.get_event_loop()
            
            def _download_sync():
                """同步下载函数（在线程池中执行）"""
                logger.info(f"使用镜像 {endpoint} 下载模型")
                
                local_path = snapshot_download(
                    repo_id=hf_model_id,
                    cache_dir=str(self.builtin_models_dir),
                    tqdm_class=ThrottledProgressReporter,
                    allow_patterns=["*.safetensors", "*.json", "*.txt", "*.npz"],
                    endpoint=endpoint,
                )
                
                return local_path
            
            # 异步执行下载
            local_path = await loop.run_in_executor(None, _download_sync)
            
            logger.info(f"模型下载成功: {local_path}")
            
            # 保存路径到缓存
            self.downloaded_models_paths[model_id] = str(local_path)
            self._save_downloaded_models_cache()
            
            # 发送完成事件
            bridge_events.model_download_completed(
                model_name=model_id,
                local_path=str(local_path),
                message=f"模型 {model_config['display_name']} 下载完成"
            )
            
            if progress_callback:
                progress_callback({
                    "progress": 100,
                    "status": "completed",
                    "message": "下载完成",
                    "path": local_path
                })
            
            return local_path
            
        except Exception as e:
            error_msg = f"下载模型 {model_id} 失败 (镜像: {mirror}): {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # 发送失败事件
            bridge_events.model_download_failed(
                model_name=model_id,
                error_message=error_msg,
                details={"mirror": mirror, "error": str(e)}
            )
            
            if progress_callback:
                progress_callback({
                    "progress": 0,
                    "status": "failed",
                    "message": error_msg,
                    "error": str(e)
                })
            
            raise Exception(error_msg)
    
    def delete_model(self, model_id: str) -> bool:
        """
        删除已下载的模型文件
        
        Args:
            model_id: 模型ID
            
        Returns:
            True 如果删除成功
        """
        if model_id not in BUILTIN_MODELS:
            raise ValueError(f"不支持的模型ID: {model_id}")
        
        model_path = self.get_model_path(model_id)
        if not model_path:
            logger.warning(f"Model {model_id} not found in downloaded cache")
            return False
        
        model_path_obj = Path(model_path)
        if not model_path_obj.exists():
            logger.warning(f"Model path {model_path} does not exist on disk")
            # 仍然从缓存中移除
            if model_id in self.downloaded_models_paths:
                del self.downloaded_models_paths[model_id]
                self._save_downloaded_models_cache()
            return False
        
        try:
            import shutil
            
            # HuggingFace 缓存结构:
            # cache_dir/models--{repo_owner}--{repo_name}/
            #   ├── blobs/
            #   ├── refs/
            #   └── snapshots/
            #       └── {hash}/  <- snapshot_download 返回的路径
            
            # 我们需要删除整个 models--{repo_owner}--{repo_name} 目录
            # 而不仅仅是 snapshots/{hash} 子目录
            
            # 向上查找到 models-- 开头的目录
            current_path = model_path_obj
            models_cache_root = None
            
            # 最多向上查找5层
            for _ in range(5):
                if current_path.name.startswith("models--"):
                    models_cache_root = current_path
                    break
                current_path = current_path.parent
                if current_path == current_path.parent:  # 到达根目录
                    break
            
            if models_cache_root and models_cache_root.exists():
                logger.info(f"Deleting HuggingFace cache directory: {models_cache_root}")
                shutil.rmtree(models_cache_root)
                logger.info(f"Successfully deleted model cache: {models_cache_root}")
            else:
                # 如果没找到 models-- 目录,直接删除给定路径
                logger.warning(f"Could not find models-- cache root, deleting given path: {model_path}")
                shutil.rmtree(model_path_obj)
                logger.info(f"Deleted model path: {model_path}")
            
            # 从缓存中移除
            if model_id in self.downloaded_models_paths:
                del self.downloaded_models_paths[model_id]
                self._save_downloaded_models_cache()
                logger.info(f"Removed {model_id} from downloaded models cache")
            
            return True
        except Exception as e:
            logger.error(f"删除模型失败: {e}", exc_info=True)
            return False
    
    def should_auto_load(self, base_dir: str) -> tuple[bool, Optional[str]]:
        """
        判断是否应该自动加载内置全能小模型
        检查任意一项系统能力配置为使用内置模型则返回 True
        
        Returns:
            (should_load, model_id): 是否应该加载，以及要加载的模型ID
        """
        from model_config_mgr import ModelConfigMgr, ModelCapability
        from db_mgr import ModelSourceType, ModelProvider
        from model_capability_confirm import ModelCapabilityConfirm
        from sqlmodel import Session, select
        
        model_config_mgr = ModelConfigMgr(self.engine)
        capability_mgr = ModelCapabilityConfirm(engine=self.engine, base_dir=base_dir)
        for cap in capability_mgr.get_sorted_capability_names():
            logger.debug(f"Supported capability: {cap}")            
            cap_config = model_config_mgr.get_model_for_global_capability(ModelCapability(cap))
            
            if not cap_config:
                continue
            
            # 查询对应的 provider
            with Session(self.engine) as session:
                provider = session.exec(
                    select(ModelProvider).where(ModelProvider.id == cap_config.provider_id)
                ).first()
                
                if not provider:
                    continue
                
                # 检查是否是 BUILTIN 类型
                if provider.source_type != ModelSourceType.BUILTIN:
                    continue
                
                # 找到对应的内置模型ID
                model_identifier = cap_config.model_identifier
                for model_id, config in BUILTIN_MODELS.items():
                    if config["hf_model_id"] == model_identifier or model_id == model_identifier:
                        logger.info(f"Should auto-load builtin model: {model_id}")
                        return True, model_id
    
        return False, None
    
    def auto_load_on_startup(self, base_dir: str) -> bool:
        """
        应用启动时自动加载模型（如果配置了使用内置模型）
        
        Returns:
            True 如果成功加载或无需加载
        """
        should_load, model_id = self.should_auto_load(base_dir=base_dir)
        
        if not should_load:
            logger.info("No builtin model configured for auto-load")
            return True
        
        # 检查模型是否已下载
        if not self.is_model_downloaded(model_id):
            logger.warning(f"Builtin model {model_id} is configured but not downloaded")
            return False
        
        
    
    def unload_current_model(self) -> bool:
        """
        卸载当前加载的模型（停止服务器）
        
        Returns:
            True 如果成功卸载
        """
        if not self.is_server_running():
            logger.info("No model is currently loaded")
            return True
        
        logger.info("Unloading current builtin model")
        return self.stop_mlx_server()
    
    

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(stream=sys.stdout)]
    )

    from config import TEST_DB_PATH
    from sqlmodel import create_engine
    engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
    base_dir=Path(TEST_DB_PATH).parent.as_posix()
    models_mgr = ModelsBuiltin(engine=engine, base_dir=base_dir)

    # test download_model_async()
    model_id = "qwen3-vl-4b"
    # import asyncio
    # asyncio.run(models_mgr.download_model_async(model_id=model_id, mirror="huggingface"))
    
    models_mgr.delete_model(model_id=model_id)