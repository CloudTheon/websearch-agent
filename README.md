# websearch-agent

一个基于 **FastAPI + LangGraph** 的流式网页搜索问答助手。默认用已有知识直接回答，遇到实时/不确定性问题时自动调用网页搜索工具（Tavily）取证，并在调用工具前通过**人工审批（Human-in-the-Loop）**暂停，由用户决定是否允许搜索。

- 后端：FastAPI，SSE 流式输出
- Agent：LangChain `create_agent` + `HumanInTheLoopMiddleware`
- 持久化：SQLite（LangGraph checkpointer 存对话状态 + 自建 `threads` 表存会话列表）
- 前端：单文件原生 JS（`static/index.html`），含会话列表、历史回看、流式输出与审批卡片

## 功能特性

- 💬 流式打字机式回答（SSE）
- 🔍 自动判断是否搜索，搜索前弹出**审批卡片**（显示工具名与参数，可批准/拒绝）
- 📚 多会话管理：左侧栏列出历史会话，点击回看，支持新建对话
- 💾 对话按 `thread_id` 持久化，刷新/重开浏览器不丢失
- 🛡️ 内容安全：若上游返回内容审查错误，自动移除当前会话中触发审查的最后一条用户消息，避免污染后续对话

## 环境要求

- Python >= 3.14
- 使用 [uv](https://github.com/astral-sh/uv) 管理依赖（也可用 `pip`）

## 安装

```bash
# 克隆后进入目录
cd websearch-agent

# 用 uv 创建虚拟环境并安装依赖
uv sync
# 或
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## 配置

程序通过环境变量读取配置（`app/config.py` 中调用了 `load_dotenv()`，因此也可放到项目根目录的 `.env` 文件）。**必须**提供的变量：

| 变量 | 说明 |
| --- | --- |
| `LLM_MODEL` | 模型名，如 `gpt-4o`、`Qwen/Qwen3-...` 等 |
| `API_KEY` | LLM 服务的 API Key |
| `BASE_URL` | OpenAI 兼容的 API 地址，如 `https://api.openai.com/v1` 或第三方兼容网关 |
| `TAVILY_API_KEY` | [Tavily](https://tavily.com) 搜索服务的 Key |

可选：`extra_body` 当前在代码中硬编码为 `{"enable_thinking": False}`（用于关闭部分推理模型的思考过程），如需修改请改 `app/config.py`。

示例 `.env`：

```env
LLM_MODEL=gpt-4o
API_KEY=sk-xxxx
BASE_URL=https://api.openai.com/v1
TAVILY_API_KEY=tvly-xxxx
```

## 运行

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问 <http://127.0.0.1:8000/> 即可使用前端界面。

## API 参考

所有接口返回 JSON，流式接口返回 `text/event-stream`（SSE，`data: {json}\n\n` 格式）。

### `GET /`
返回前端页面 `static/index.html`。

### `GET /threads`
返回会话列表（按最近更新倒序）。

**响应**
```json
{
  "threads": [
    { "thread_id": "web-xxx", "title": "你好", "created_at": "...", "updated_at": "..." }
  ]
}
```

### `GET /threads/{thread_id}/history`
返回指定会话的消息历史。

**响应**
```json
{
  "thread_id": "web-xxx",
  "messages": [
    { "role": "human", "content": "今天天气如何？" },
    { "role": "ai", "content": "..." }
  ]
}
```
`role` 可能为 `human` / `ai` / `tool` / `system`。

### `POST /chat/stream`
发起一轮对话，流式返回。

**请求体**
```json
{ "message": "最新的人工智能新闻", "thread_id": "web-xxx" }
```

**SSE 事件类型**
| type | 字段 | 说明 |
| --- | --- | --- |
| `token` | `content` | 模型输出的文本增量 |
| `interrupt` | `interrupts:[{id, value}]` | 需要人工审批，等待 `/resume/stream` |
| `error` | `content` | 错误信息（含上游错误体） |
| `done` | — | 本轮流结束 |

### `POST /resume/stream`
对中断的工具调用做出批准/拒绝，继续流式执行。

**请求体**
```json
{
  "thread_id": "web-xxx",
  "decisions": [
    { "interrupt_id": "033ed2bd-...", "type": "approve" }
  ]
}
```
`type` 可为 `approve`（批准）或 `reject`（拒绝，可带 `message` 说明）。`interrupt_id` 来自上一步 `interrupt` 事件中的 `id`。返回的 SSE 事件类型同上。

## 前端使用

- **新建对话**：点击左侧「+ 新建对话」，自动生成无连字符 UUID 的 `thread_id`（如 `web-9f8a7b6c5d4e...`）。
- **历史回看**：点击左侧会话条目，加载并展示该会话全部历史消息。
- **搜索审批**：当模型决定调用搜索工具时，底部弹出审批卡片，显示工具名与参数，点「批准」继续、「拒绝」跳过。
- 发送期间输入框禁用，避免重复提交。

## 数据存储

- 对话状态：LangGraph `AsyncSqliteSaver`，库文件位于 `data/agent.db`。
- 会话列表：`threads` 表（自建），记录 `thread_id` / `title` / 时间戳。

## 注意事项

- **`thread_id` 复用与内容审查**：对话按 `thread_id` 持久化，每次请求都会把整段历史发给模型。若历史中包含被上游内容安全策略拦截的内容，该 `thread_id` 此后每次请求都会报 `data_inspection_failed`。后端已在拦截时自动移除最后一条用户消息来缓解；若仍无法恢复，请「新建对话」换一个 `thread_id`。
- **CORS**：默认 `allow_origins=["*"]`，仅适合本地开发；生产环境请在 `app/config.py` 中收紧。
- **`enable_thinking`**：作为 `extra_body` 固定发送，若你的 `BASE_URL` 对应服务不支持该字段，可能返回 400，请按需注释/调整 `app/config.py`。
