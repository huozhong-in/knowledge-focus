"""
测试 Metal GPU 互斥锁是否正常工作
"""
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入锁函数
from multivector_mgr import acquire_metal_lock, release_metal_lock

def simulate_docling_work(name: str, duration: float):
    """模拟 Docling 工作"""
    logger.info(f"[{name}] 开始工作")
    acquire_metal_lock(f"Docling-{name}")
    try:
        logger.info(f"[{name}] 获得锁,执行工作...")
        time.sleep(duration)
        logger.info(f"[{name}] 工作完成")
    finally:
        release_metal_lock(f"Docling-{name}")

def simulate_mlx_work(name: str, duration: float):
    """模拟 MLX-VLM 工作"""
    logger.info(f"[{name}] 开始工作")
    acquire_metal_lock(f"MLX-{name}")
    try:
        logger.info(f"[{name}] 获得锁,执行工作...")
        time.sleep(duration)
        logger.info(f"[{name}] 工作完成")
    finally:
        release_metal_lock(f"MLX-{name}")

def test_lock():
    """测试锁机制"""
    logger.info("=== 开始测试 Metal GPU 互斥锁 ===")
    
    # 创建3个线程模拟并发任务
    threads = [
        threading.Thread(target=simulate_docling_work, args=("Task1", 2)),
        threading.Thread(target=simulate_mlx_work, args=("Task2", 1.5)),
        threading.Thread(target=simulate_docling_work, args=("Task3", 1)),
    ]
    
    # 同时启动所有线程
    start_time = time.time()
    for t in threads:
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    total_time = time.time() - start_time
    logger.info(f"=== 测试完成,总耗时: {total_time:.2f}秒 ===")
    logger.info(f"如果锁正常工作,总耗时应接近 {2+1.5+1}秒 (任务顺序执行)")

if __name__ == "__main__":
    test_lock()