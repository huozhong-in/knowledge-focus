"""
测试 Metal GPU 锁在实际场景中的效果

模拟: 文件打标签 (MLX-VLM) + 向量化 (Docling) 并发
"""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_concurrent_operations():
    """测试并发操作"""
    from multivector_mgr import acquire_metal_lock_async, release_metal_lock_async
    
    async def mock_mlx_vlm_tagging():
        """模拟 MLX-VLM 打标签任务"""
        logger.info("[MLX-VLM] 开始打标签任务")
        await acquire_metal_lock_async("MLX-VLM tagging")
        try:
            await asyncio.sleep(2)  # 模拟推理耗时
            logger.info("[MLX-VLM] 打标签完成")
        finally:
            await release_metal_lock_async("MLX-VLM tagging")
    
    async def mock_docling_vectorization():
        """模拟 Docling 向量化任务"""
        logger.info("[Docling] 开始向量化任务")
        await acquire_metal_lock_async("Docling vectorization")
        try:
            await asyncio.sleep(3)  # 模拟解析耗时
            logger.info("[Docling] 向量化完成")
        finally:
            await release_metal_lock_async("Docling vectorization")
    
    # 并发启动两个任务
    logger.info("=== 开始并发测试 ===")
    start = asyncio.get_event_loop().time()
    
    await asyncio.gather(
        mock_mlx_vlm_tagging(),
        mock_docling_vectorization()
    )
    
    end = asyncio.get_event_loop().time()
    logger.info(f"=== 测试完成,总耗时: {end - start:.2f}秒 ===")
    logger.info("如果锁正常工作,总耗时应接近 5秒 (串行执行)")

if __name__ == "__main__":
    asyncio.run(test_concurrent_operations())