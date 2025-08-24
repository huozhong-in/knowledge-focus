"""
工具通道使用示例

演示如何使用工具通道机制让PydanticAI Agent调用前端TypeScript工具
"""

import asyncio
from pydantic_ai import Agent
from backend_tool_caller import g_backend_tool_caller
from tools.co_reading import (
    handle_active_preview_app,
    handle_scroll_pdf,
    handle_preview_app_screenshot,
    handle_control_preview_app,
    ensure_accessibility_permission
)

# 创建一个示例Agent，用于演示PDF共读功能
pdf_coread_agent = Agent(
    model='openai:gpt-4o-mini',  # 可以配置为其他模型
    system_prompt="""你是一个PDF共读助手。你可以帮助用户与PDF文档进行交互，包括：
1. 打开和激活PDF应用
2. 控制PDF滚动
3. 截图保存PDF内容
4. 管理PDF应用窗口

当用户要求与PDF文档交互时，你应该使用可用的工具来完成操作。
请始终确认操作结果并向用户报告执行状态。"""
)

# 注册工具到Agent
@pdf_coread_agent.tool
async def activate_pdf_app(pdf_path: str) -> dict:
    """激活Preview应用并打开指定PDF文件"""
    try:
        result = await handle_active_preview_app(pdf_path)
        return result
    except Exception as e:
        return {"success": False, "message": f"激活PDF应用失败: {e}"}

@pdf_coread_agent.tool
async def scroll_pdf_document(direction: str, amount: int = 1) -> dict:
    """滚动PDF文档，direction可以是'up'或'down'"""
    if direction not in ['up', 'down']:
        return {"success": False, "message": "direction必须是'up'或'down'"}
    
    try:
        result = await handle_scroll_pdf(direction, amount)
        return result
    except Exception as e:
        return {"success": False, "message": f"滚动PDF失败: {e}"}

@pdf_coread_agent.tool
async def take_pdf_screenshot(pdf_path: str) -> dict:
    """对当前PDF页面截图"""
    try:
        result = await handle_preview_app_screenshot(pdf_path)
        return result
    except Exception as e:
        return {"success": False, "message": f"截图失败: {e}"}

@pdf_coread_agent.tool
async def control_pdf_window(pdf_path: str, action: str = "focus") -> dict:
    """控制PDF窗口，action可以是'focus', 'minimize', 'close'"""
    if action not in ['focus', 'minimize', 'close']:
        return {"success": False, "message": "action必须是'focus', 'minimize', 'close'之一"}
    
    try:
        result = await handle_control_preview_app(pdf_path, action)
        return result
    except Exception as e:
        return {"success": False, "message": f"控制PDF窗口失败: {e}"}

@pdf_coread_agent.tool
async def check_accessibility_permission() -> dict:
    """检查并确保系统辅助功能权限"""
    try:
        result = await ensure_accessibility_permission()
        return result
    except Exception as e:
        return {"success": False, "message": f"权限检查失败: {e}"}

# 使用示例
async def example_pdf_interaction():
    """示例：与PDF文档交互"""
    
    # 示例PDF路径
    pdf_path = "/Users/example/Documents/sample.pdf"
    
    print("=== PDF共读Agent工具通道示例 ===\n")
    
    # 示例1：打开PDF并滚动
    print("📖 示例1：打开PDF并向下滚动")
    try:
        result = await pdf_coread_agent.run(
            f"请打开PDF文件 '{pdf_path}' 并向下滚动3次，然后报告当前状态"
        )
        print(f"Agent响应: {result.data}")
    except Exception as e:
        print(f"执行失败: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # 示例2：截图并最小化窗口
    print("📸 示例2：对PDF截图并最小化窗口")
    try:
        result = await pdf_coread_agent.run(
            f"请对PDF文件 '{pdf_path}' 进行截图，然后最小化窗口"
        )
        print(f"Agent响应: {result.data}")
    except Exception as e:
        print(f"执行失败: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # 示例3：检查权限状态
    print("🔐 示例3：检查系统权限")
    try:
        result = await pdf_coread_agent.run(
            "请检查系统辅助功能权限状态，如果没有权限请提示用户如何授权"
        )
        print(f"Agent响应: {result.data}")
    except Exception as e:
        print(f"执行失败: {e}")

# 直接测试工具通道功能
async def test_tool_channel_directly():
    """直接测试工具通道功能"""
    
    print("=== 直接测试工具通道 ===\n")
    
    # 测试1：激活PDF应用
    print("🔧 测试1：激活PDF应用")
    try:
        result = await g_backend_tool_caller.call_frontend_tool(
            "handle_active_preview_app",
            pdf_path="/Users/example/Documents/sample.pdf"
        )
        print(f"结果: {result}")
    except Exception as e:
        print(f"失败: {e}")
    
    print("\n" + "-"*30 + "\n")
    
    # 测试2：滚动PDF
    print("📜 测试2：向下滚动PDF")
    try:
        result = await g_backend_tool_caller.call_frontend_tool(
            "handle_scroll_pdf",
            direction="down",
            amount=2
        )
        print(f"结果: {result}")
    except Exception as e:
        print(f"失败: {e}")
    
    print("\n" + "-"*30 + "\n")
    
    # 测试3：权限检查
    print("🛡️  测试3：权限检查")
    try:
        result = await g_backend_tool_caller.call_frontend_tool(
            "ensure_accessibility_permission"
        )
        print(f"结果: {result}")
    except Exception as e:
        print(f"失败: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "direct":
        # 直接测试工具通道
        asyncio.run(test_tool_channel_directly())
    else:
        # 测试完整的Agent交互
        asyncio.run(example_pdf_interaction())
    
    print("\n=== 测试完成 ===")
    print("注意：前端必须正在运行并且已经注册了相应的工具处理函数才能正常工作")
