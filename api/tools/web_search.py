from sqlmodel import Session, select
from db_mgr import Tool
from pydantic_ai import RunContext
from pydantic_ai.common_tools.tavily import tavily_search_tool

def search_use_tavily(ctx: RunContext[int], query: str, session: Session) -> str:
    """
    使用Tavily进行网络搜索

    需要在metadata_json中配置api_key

    Args:
        query (str): 搜索查询字符串
        api_key (str): Tavily API密钥

    Returns:
        str: 搜索结果摘要
    """
    tool = session.exec(
        select(Tool).where(Tool.name == "search_use_tavily").first()
    )
    meta_data_json = tool.metadata_json if tool and tool.metadata_json else {}
    api_key = meta_data_json.get("api_key", "")
    if api_key == "":
        return "Error: Tavily API key is not configured."
    try:
        results = tavily_search_tool(query, api_key=api_key)
        if results and isinstance(results, list):
            # 返回前3条结果的摘要
            summaries = [result.get("snippet", "") for result in results[:3]]
            return "\n".join(summaries) if summaries else "No relevant information found."
        return "No relevant information found."
    except Exception as e:
        return f"Error during web search: {str(e)}"

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