"""聊天助手 Agent 定义。

默认以对话方式直接回答；当问题涉及最新信息、无法确定的事实或用户要求查证时，
自动调用网页搜索工具获取资料后再作答。
"""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.chat_models import init_chat_model
from app.tools import internet_search
from app.config import settings

SYSTEM_PROMPT = """你是一个友好、简洁的中文聊天助手。
工作方式：
1. 能用已有知识回答的问题，直接回答，不要搜索。
2. 当问题涉及实时/最新信息（新闻、天气、价格、版本、近期事件等），或你对事实不确定，
   或用户明确要求查证时，调用网页搜索工具获取资料。
3. 基于搜索结果作答时，进行简明总结，并在末尾列出参考来源链接。
4. 搜索失败或没有可用结果时，如实说明，然后基于已有知识给出回答并提示可能存在时效性问题。
5. 一次搜索信息不足时，可以换用更精确的关键词再次搜索，但不要超过 3 次。
"""


def build_model():
    return init_chat_model(
        model=settings.llm_model,
        model_provider=settings.model_provider,
        api_key=settings.api_key,
        base_url=settings.base_url,
        extra_body=settings.extra_body,
    )


def create_websearch_agent(checkpointer):
    return create_agent(
        model=build_model(),
        tools=[internet_search],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={"internet_search": True},
                interrupt_mode="per_call",
            )
        ],
        name="websearch-agent",
    )
