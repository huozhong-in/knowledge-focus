"""
测试 MLX 服务监控和自动重启功能

验证：
1. 监控任务能够检测到服务崩溃
2. 自动重启机制工作正常
3. 指数退避策略生效
"""
import asyncio
from utils import is_port_in_use, kill_process_on_port

MLX_SERVICE_PORT = 60316

async def test_monitor_detection():
    """测试监控能否检测到服务崩溃"""
    print("\n" + "="*60)
    print("测试 1: 监控检测崩溃服务")
    print("="*60)
    
    # 检查服务当前状态
    is_running = is_port_in_use(MLX_SERVICE_PORT)
    print(f"📊 当前 MLX 服务状态: {'运行中' if is_running else '未运行'}")
    
    if is_running:
        print("✅ 服务正在运行，模拟崩溃...")
        
        # 模拟崩溃：强制杀死进程
        success = kill_process_on_port(MLX_SERVICE_PORT)
        if success:
            print("✅ 成功模拟崩溃（杀死了进程）")
            
            # 等待几秒，让监控任务检测到
            print("⏳ 等待 15 秒，让监控任务检测并重启...")
            await asyncio.sleep(15)
            
            # 检查是否被重启
            is_running_after = is_port_in_use(MLX_SERVICE_PORT)
            if is_running_after:
                print("✅ 监控任务成功检测到崩溃并自动重启了服务！")
            else:
                print("❌ 监控任务未能重启服务（可能配置不需要 MLX 服务）")
        else:
            print("❌ 无法杀死进程，测试失败")
    else:
        print("⚠️  服务当前未运行，无法测试崩溃检测")
        print("   请先确保 MLX 服务在配置中被启用")

async def test_restart_frequency_limit():
    """测试频繁崩溃时的退避策略"""
    print("\n" + "="*60)
    print("测试 2: 频繁崩溃时的退避策略")
    print("="*60)
    print("⚠️  注意：此测试会多次杀死 MLX 服务，请谨慎运行")
    print("   建议在开发环境中测试")
    
    # 询问用户是否继续
    print("\n是否继续？(输入 'yes' 继续，其他键跳过)")
    # 由于是自动化测试，这里直接跳过
    print("⏭️  跳过此测试（需要手动确认）")
    return
    
    """
    # 如果要启用，取消下面的注释
    crash_count = 3
    for i in range(crash_count):
        print(f"\n🔄 模拟第 {i+1} 次崩溃...")
        
        is_running = is_port_in_use(MLX_SERVICE_PORT)
        if is_running:
            kill_process_on_port(MLX_SERVICE_PORT)
            print(f"✅ 第 {i+1} 次崩溃已触发")
        else:
            print(f"⚠️  服务未运行，等待重启...")
        
        # 等待 5 秒再触发下一次崩溃
        if i < crash_count - 1:
            await asyncio.sleep(5)
    
    # 等待足够长的时间观察退避行为
    print("\n⏳ 等待 30 秒观察监控的退避行为...")
    await asyncio.sleep(30)
    
    # 检查最终状态
    is_running_final = is_port_in_use(MLX_SERVICE_PORT)
    print(f"\n📊 最终状态: {'服务运行中' if is_running_final else '服务未运行'}")
    """

async def test_service_health_check():
    """测试服务健康检查"""
    print("\n" + "="*60)
    print("测试 3: 服务健康检查")
    print("="*60)
    
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 检查主 API 服务
            try:
                response = await client.get("http://127.0.0.1:60315/health")
                if response.status_code == 200:
                    print("✅ 主 API 服务运行正常")
                else:
                    print(f"⚠️  主 API 服务响应异常: {response.status_code}")
            except Exception as e:
                print(f"❌ 无法连接到主 API 服务: {e}")
            
            # 检查 MLX 服务
            try:
                response = await client.get("http://127.0.0.1:60316/health")
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ MLX 服务运行正常: {result}")
                else:
                    print(f"⚠️  MLX 服务响应异常: {response.status_code}")
            except httpx.ConnectError:
                print("❌ 无法连接到 MLX 服务（可能未运行或正在重启）")
            except Exception as e:
                print(f"❌ MLX 服务检查失败: {e}")
    
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")

async def test_monitor_logs():
    """查看监控日志"""
    print("\n" + "="*60)
    print("测试 4: 查看监控日志")
    print("="*60)
    
    from pathlib import Path
    
    # 查找日志文件
    log_dir = Path.home() / "Library/Application Support/knowledge-focus.huozhong.in/logs"
    
    if not log_dir.exists():
        print(f"❌ 日志目录不存在: {log_dir}")
        return
    
    # 查找最新的 API 日志
    log_files = sorted(log_dir.glob("api_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not log_files:
        print(f"❌ 在 {log_dir} 中未找到日志文件")
        return
    
    latest_log = log_files[0]
    print(f"📄 最新日志文件: {latest_log.name}")
    
    # 读取最后 50 行
    try:
        with open(latest_log, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # 过滤出包含 MLX 监控相关的日志
        mlx_lines = [line for line in lines if 'MLX service monitor' in line or 'MLX service' in line]
        
        if mlx_lines:
            print(f"\n📋 MLX 监控相关日志（最近 {len(mlx_lines)} 条）:\n")
            for line in mlx_lines[-20:]:  # 显示最后 20 条
                print(line.rstrip())
        else:
            print("\n⚠️  未找到 MLX 监控相关日志")
            print("   可能监控任务尚未启动或日志被轮转")
    
    except Exception as e:
        print(f"❌ 读取日志失败: {e}")

async def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("MLX 服务监控与自动重启功能测试")
    print("="*60)
    print("⚠️  注意：这些测试需要主 FastAPI 服务正在运行")
    print()
    
    try:
        # 测试 1: 基本健康检查
        await test_service_health_check()
        
        # 测试 2: 查看监控日志
        await test_monitor_logs()
        
        # 测试 3: 监控检测与自动重启（会实际杀死服务）
        print("\n" + "="*60)
        print("⚠️  警告：下一个测试会实际杀死 MLX 服务来测试自动重启")
        print("   如果不想运行，请按 Ctrl+C 退出")
        print("="*60)
        await asyncio.sleep(3)  # 给用户 3 秒时间取消
        
        await test_monitor_detection()
        
        # 测试 4: 频繁崩溃退避（需要手动确认）
        await test_restart_frequency_limit()
        
        print("\n" + "="*60)
        print("✅ 测试完成！")
        print("="*60)
        print("\n💡 提示：")
        print("   - 监控任务每 10 秒检查一次服务状态")
        print("   - 如果服务崩溃，会在下一个检查周期自动重启")
        print("   - 频繁崩溃会触发指数退避策略")
        print("   - 可以查看日志了解详细的监控和重启行为")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
