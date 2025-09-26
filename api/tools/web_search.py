from sqlmodel import Session, select
from sqlalchemy import Engine
from db_mgr import Tool as ToolSpec
from pydantic_ai import RunContext
import httpx

async def search_use_tavily(ctx: RunContext[Engine], query: str) -> str:
    """
    使用Tavily进行网络搜索，将结果摘要返回

    Args:
        query (str): 搜索查询

    Returns:
        str: 搜索结果摘要
    """
    with Session(ctx.deps) as session:
        tool_spec = session.exec(
            select(ToolSpec).where(ToolSpec.name == "search_use_tavily")
        ).first()
        meta_data_json = tool_spec.metadata_json if tool_spec and tool_spec.metadata_json else {}
        api_key = meta_data_json.get("api_key", "")
        if api_key == "":
            return "Error: Tavily API key is not configured."
        
        # 直接调用Tavily API
        try:
            url = "https://api.tavily.com/search"
            headers = {"Content-Type": "application/json"}
            data = {
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "include_raw_content": False,
                "max_results": 3,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=headers)
                response.raise_for_status()
                result = response.json()
                
                # 格式化搜索结果
                if "results" in result and result["results"]:
                    formatted_results = []
                    for item in result["results"]:
                        formatted_results.append(f"- {item.get('title', 'No title')}: {item.get('content', 'No content')[:200]}... (来源: {item.get('url', 'No URL')})")
                    
                    answer = result.get("answer", "")
                    output = f"搜索结果:\n{chr(10).join(formatted_results)}"
                    if answer:
                        output = f"总结答案: {answer}\n\n{output}"
                    
                    return output
                else:
                    return "未找到相关搜索结果。"
                    
        except Exception as e:
            return f"搜索时出现错误: {str(e)}"

def test_api_key(api_key: str) -> bool:
    """
    测试Tavily API密钥是否有效

    Args:
        api_key (str): Tavily API密钥

    Returns:
        bool: 如果API密钥有效则返回True，否则返回False
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={api_key}"

    async def main():
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                print(f"Available tools: {', '.join([t.name for t in tools_result.tools])}")
    
    import asyncio
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error testing API key: {e}")
        return False
    return True