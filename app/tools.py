from typing import Literal

from langchain.tools import tool
from tavily import AsyncTavilyClient
from app.config import settings

tavily_client = AsyncTavilyClient(api_key=settings.tavily_api_key)


@tool
async def internet_search(
    query: str,
    topic: Literal["news", "finance", "general"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
):
    """
    根据用户问题，进行网络信息搜索！
    :param query: 用户的查询信息
    :param topic: 查询的类型
    :param max_results: 返回的最大条数
    :param include_raw_content: 是否返回原内容 False 精简 True 详细
    :return:
    """
    return await tavily_client.search(
        query=query,
        topic=topic,
        max_results=max_results,
        include_raw_content=include_raw_content,
    )
