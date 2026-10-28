from contextlib import asynccontextmanager
import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from langchain.messages import HumanMessage, RemoveMessage
from langgraph.stream import AsyncGraphRunStream
from langgraph.types import Command
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import json

from app.agent import create_websearch_agent
from app.config import settings
from app.schemas import (
    ChatRequest,
    HistoryResponse,
    MessageItem,
    ResumeRequest,
    ThreadListResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.require()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    db_conn = await aiosqlite.connect(str(settings.db_path))
    db_conn.row_factory = aiosqlite.Row

    # 建表
    await db_conn.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db_conn.commit()

    # 存到 app.state 供路由使用
    app.state.db_conn = db_conn
    async with AsyncSqliteSaver.from_conn_string(str(settings.db_path)) as checkpointer:
        app.state.agent = create_websearch_agent(checkpointer)
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse(settings.web_path)


@app.get("/threads", response_model=ThreadListResponse)
async def list_threads():
    async with app.state.db_conn.execute(
        "SELECT thread_id, title, created_at, updated_at FROM threads ORDER BY updated_at DESC"
    ) as cursor:
        rows = await cursor.fetchall()
    return {"threads": [dict(r) for r in rows]}


@app.get("/threads/{thread_id}/history", response_model=HistoryResponse)
async def get_history(thread_id: str) -> HistoryResponse:
    config = {"configurable": {"thread_id": thread_id}}
    state = await app.state.agent.aget_state(config)
    messages = state.values.get("messages", [])

    def to_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content)

    return HistoryResponse(
        thread_id=thread_id,
        messages=[
            MessageItem(role=m.type, content=to_text(m.content)) for m in messages
        ],
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    await app.state.db_conn.execute(
        """INSERT INTO threads (thread_id, title) VALUES (?, ?)
           ON CONFLICT(thread_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP""",
        (req.thread_id, req.message[:30]),
    )
    await app.state.db_conn.commit()
    config = {"configurable": {"thread_id": req.thread_id}}
    stream = await app.state.agent.astream_events(
        {"messages": [HumanMessage(content=req.message)]},
        config=config,
        version="v3",
    )
    return await sse_response(stream, config)


@app.post("/resume/stream")
async def resume_stream(req: ResumeRequest):
    decisions = {}
    for d in req.decisions:
        if d.type == "approve":
            decisions[d.interrupt_id] = {"type": "approve"}
        else:
            decisions[d.interrupt_id] = {
                "type": "reject",
                "message": d.message or "用户拒绝",
            }
    config = {"configurable": {"thread_id": req.thread_id}}
    stream = await app.state.agent.astream_events(
        Command(resume=decisions),
        config=config,
        version="v3",
    )
    return await sse_response(stream, config)


async def stream_output(stream: AsyncGraphRunStream):
    """把 agent 的流式输出转换成 SSE 格式的字符串。"""
    async for message in stream.messages:
        async for delta in message.text:
            yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"

        # 每个 message 结束后检查一次中断，而不是每个 token 都查
        interrupts = await stream.interrupts()
        if interrupts:
            payload = {
                "type": "interrupt",
                "interrupts": [{"id": i.id, "value": i.value} for i in interrupts],
            }
            yield f"data: {json.dumps(payload)}\n\n"


async def sse_response(stream: AsyncGraphRunStream, config: dict) -> StreamingResponse:
    """把流包装成 SSE 响应，并在末尾统一发送 done 事件。"""

    async def event_generator():
        try:
            async for chunk in stream_output(stream):
                yield chunk
        except Exception as e:  # noqa: BLE001
            body = getattr(e, "body", None)
            msg = getattr(e, "message", None) or str(e)
            if body:
                msg = f"{msg} | response_body={body}"

            # 内容审核拦截：删除触发报错的最后一条用户消息，避免污染后续对话
            if "inappropriate content" in msg.lower():
                try:
                    state = await app.state.agent.aget_state(config)
                    human_msgs = [
                        m
                        for m in state.values["messages"]
                        if isinstance(m, HumanMessage)
                    ]
                    if human_msgs:
                        last_human = human_msgs[-1]
                        await app.state.agent.aupdate_state(
                            config,
                            {"messages": [RemoveMessage(id=last_human.id)]},
                        )
                    msg = "该内容因安全策略被跳过，已从本会话移除，请换个话题继续。"
                except Exception as cleanup_err:  # noqa: BLE001
                    msg = f"{msg}（清理失败：{cleanup_err}）"

            payload = {"type": "error", "content": msg}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
