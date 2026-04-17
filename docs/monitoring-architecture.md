# Hermes Agent 监控系统架构设计

## 概述

本文档设计基于 **Python + FastAPI** 的 Hermes Agent 监控与管理外挂系统。核心设计原则是：

1. **不重复造轮子**：Hermes 已内置 OpenAI 兼容 HTTP API（随 `hermes gateway` 启动，默认 `http://127.0.0.1:8642/v1`），外挂系统**反向代理**对话请求，不重新实现 completion 协议
2. **专注管理面**：外挂负责 sessions/config/gateway/cron/skills 等**管理类 API** 和**监控/审计**功能
3. **实时双向通信**：WebSocket 提供工具进度、审批流、日志流等实时事件
4. **与 Hermes 同栈**：Python 3.11+ + FastAPI + uvicorn，便于日后导入官方模块

---

## 架构全景

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    外部客户端                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  External    │  │  Monitor UI  │  │  Mobile App  │  │  Custom Bot  │                  │
│  │    Apps      │  │  (监控界面)   │  │   (监控)     │  │   (审计)      │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
└─────────┼─────────────────┼─────────────────┼─────────────────┼──────────────────────────┘
          │                 │                 │                 │
          │                 │ WebSocket       │                 │
          │  (对话请求)      │ (事件/审批)     │                 │
          │                 │                 │                 │
          ▼                 ▼                 │                 │
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              Hermes API Gateway 外挂                                      │
│                              FastAPI + uvicorn + Python 3.11+                             │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         HTTP REST API Router                                     │   │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐  │   │
│   │  │  /sessions  │ │  /config    │ │  /gateway   │ │   /skills   │ │   /cron    │  │   │
│   │  │  (会话管理)  │ │  (配置管理)  │ │  (网关管理)  │ │  (技能管理)  │ │ (任务调度)  │  │   │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘  │   │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐  │   │
│   │  │   /auth     │ │   /tools    │ │    /mcp     │ │  /webhook   │ │  /profile  │  │   │
│   │  │  (认证管理)  │ │  (工具配置)  │ │  (MCP管理)  │ │ (Webhook)   │ │ (多实例)   │  │   │
│   │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘  │   │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                                  │   │
│   │  │  /insights  │ │   /logs     │ │  /metrics   │  ← 只读监控接口                    │   │
│   │  │  (数据分析)  │ │  (日志查询)  │ │  (性能指标)  │                                  │   │
│   │  └─────────────┘ └─────────────┘ └─────────────┘                                  │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│   ┌──────────────────────────────────────┴──────────────────────────────────────────┐   │
│   │                    Reverse Proxy (/v1/*) → Hermes 内置 API                       │   │
│   │                                                                                  │   │
│   │   /v1/chat/completions  ──────┐                                                 │   │
│   │   /v1/responses               ├─────►  http://127.0.0.1:8642/v1/*               │   │
│   │   /v1/models                  │      (透传 + 可选审计日志)                        │   │
│   │   /v1/responses/{id}         ┘                                                 │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│   ┌──────────────────────────────────────┴──────────────────────────────────────────┐   │
│   │                         WebSocket Hub (实时双向通信)                            │   │
│   │                                                                                  │   │
│   │   事件推送:  tool_progress  ─────►  工具执行进度                                 │   │
│   │              log_stream     ─────►  实时日志流                                   │   │
│   │              agent_status   ─────►  Agent 状态变更                               │   │
│   │              session_events ─────►  会话事件                                     │   │
│   │                                                                                  │   │
│   │   客户端请求: approve_tool  ─────►  审批工具调用                                 │   │
│   │              reject_tool    ─────►  拒绝工具调用                                 │   │
│   │              interrupt      ─────►  中断会话                                     │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│   ┌──────────────────────────────────────┴──────────────────────────────────────────┐   │
│   │                      Hermes CLI Runner / Job Queue                              │   │
│   │                                                                                  │   │
│   │   subprocess.run(["hermes", "sessions", "list"], ...)  ─────►  同步执行          │   │
│   │   BackgroundTasks (FastAPI)  ──────────────────────────────►  异步执行           │   │
│   │   asyncio.create_subprocess_exec(...)  ────────────────────►  流式输出           │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│   ┌──────────────────────────────────────┴──────────────────────────────────────────┐   │
│   │                         Authn/z & Multi-tenant                                  │   │
│   │                                                                                  │   │
│   │   API Key 验证 ──────►  访问控制  ──────►  审计日志                              │   │
│   │   JWT Token         ──────►  权限角色  ──────►  操作追踪                         │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
          │                    │                           │
          │ CLI 命令           │ HTTP 反向代理              │ state.db (SQLite)
          │                    │                           │
          ▼                    ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              Hermes Runtime (同一机器)                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                      hermes gateway (内置 API Server)                            │   │
│   │                                                                                  │   │
│   │   Port: 8642 (默认)                                                              │   │
│   │                                                                                  │   │
│   │   POST /v1/chat/completions  ─────┐                                             │   │
│   │   POST /v1/responses             ├─────►  OpenAI 兼容 API                        │   │
│   │   GET  /v1/models                │      SSE 流式输出                             │   │
│   │   GET  /v1/responses/{id}       ┘      hermes.tool.progress (自定义事件)          │   │
│   │                                    Auth: Bearer <API_SERVER_KEY>                 │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
│   ┌─────────────────────────────────┐  ┌─────────────────────────────────────────────┐   │
│   │        hermes CLI               │  │           state.db (SQLite)                 │   │
│   │                                 │  │                                             │   │
│   │  sessions list/export/rename   │  │  sessions 表 ────── 会话元数据              │   │
│   │  config show/edit/set          │  │  messages 表 ────── 消息内容                │   │
│   │  gateway status/start/stop     │  │  tool_calls 表 ──── 工具调用记录            │   │
│   │  skills search/install         │  │  logs 表 ────────── 运行日志                │   │
│   │  cron/webhook/auth/...         │  │  config 表 ──────── 配置项                  │   │
│   │                                 │  │                                             │   │
│   └─────────────────────────────────┘  └─────────────────────────────────────────────┘   │
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                      Hermes Agent Core                                          │   │
│   │                                                                                  │   │
│   │   - LLM 对话执行                                                                 │   │
│   │   - 工具调用 (web, terminal, skills...)                                         │   │
│   │   - 多平台 Gateway (Telegram, Discord, Slack...)                                │   │
│   │   - Cron 任务调度                                                                │   │
│   │   - MCP 服务集成                                                                 │   │
│   └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心设计决策

### 1. 职责边界划分

| 功能 | Hermes 内置 API | 外挂系统 | 说明 |
|------|----------------|----------|------|
| **对话 Completion** | ✅ `/v1/chat/completions` | ❌ 反向代理 | 不重复实现，透传即可 |
| **Responses API** | ✅ `/v1/responses` | ❌ 反向代理 | 支持服务端多轮状态 |
| **模型列表** | ✅ `/v1/models` | ❌ 透传或缓存 | 代理获取 |
| **会话管理** | ❌ | ✅ `/sessions/*` | list/rename/export/delete/prune |
| **配置管理** | ❌ | ✅ `/config/*` | show/edit/set/check |
| **网关管理** | ❌ | ✅ `/gateway/*` | 状态/启停/平台配置 |
| **认证管理** | ❌ | ✅ `/auth/*` | providers/credentials |
| **技能管理** | ❌ | ✅ `/skills/*` | search/install/configure |
| **日志查询** | ❌ | ✅ `/logs/*` | 查询/过滤/统计 |
| **数据分析** | ❌ | ✅ `/insights/*` | 使用统计/趋势 |
| **实时事件** | ❌ (仅SSE) | ✅ WebSocket | tool_progress, log_stream |
| **双向控制** | ❌ | ✅ WebSocket | 审批/中断/命令 |

### 2. 技术栈选型

```yaml
语言: Python 3.11+
框架: FastAPI 0.100+
服务器: uvicorn (HTTP/2, WebSocket)
CLI 执行: subprocess + asyncio
数据库: SQLite (Hermes 共用，只读访问)
缓存: 内存 (asyncio.Lock 保护)
认证: API Key + JWT (可选)
文档: OpenAPI (FastAPI 自动生成)
```

### 3. 调用 Hermes 的三种方式

```python
# 方式 1: 同步 CLI 调用 (管理类命令)
import subprocess

def run_hermes_cli(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(
        ["hermes"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PATH": f"{os.environ.get('HOME')}/.local/bin:/usr/local/bin:{os.environ.get('PATH')}"}
    )
    if result.returncode != 0:
        raise CLIError(result.stderr)
    return result.stdout

# 使用示例
output = run_hermes_cli(["sessions", "list", "--limit", "20"])
```

```python
# 方式 2: 异步流式调用 (logs -f)
import asyncio

async def stream_hermes_logs():
    proc = await asyncio.create_subprocess_exec(
        "hermes", "logs", "-f",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield line.decode().strip()
```

```python
# 方式 3: HTTP 转发 (对话请求)
import httpx

async def proxy_to_hermes(request: Request, path: str):
    """反向代理到 Hermes 内置 API"""
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=f"http://127.0.0.1:8642{path}",
            headers={"Authorization": f"Bearer {HERMES_API_KEY}"},
            content=await request.body()
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )
```

---

## 模块详细设计

### 项目结构

```
hermes-agent-ui-monitor/
├── backend/                       # Python FastAPI 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI 应用入口
│   │   ├── config.py              # 配置管理 (pydantic-settings)
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py            # 依赖注入 (auth, db)
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py      # API v1 路由聚合
│   │   │   │   ├── endpoints/
│   │   │   │   │   ├── sessions.py    # 会话管理
│   │   │   │   │   ├── config.py      # 配置管理
│   │   │   │   │   ├── gateway.py     # 网关管理
│   │   │   │   │   ├── auth.py        # 认证管理
│   │   │   │   │   ├── skills.py      # 技能管理
│   │   │   │   │   ├── tools.py       # 工具配置
│   │   │   │   │   ├── cron.py        # 任务调度
│   │   │   │   │   ├── webhook.py     # Webhook
│   │   │   │   │   ├── mcp.py         # MCP 服务
│   │   │   │   │   ├── logs.py        # 日志查询
│   │   │   │   │   ├── insights.py    # 数据分析
│   │   │   │   │   ├── profile.py     # 多实例
│   │   │   │   │   └── proxy.py       # /v1/* 反向代理
│   │   │   │   └── models/
│   │   │   │       ├── session.py     # Pydantic 模型
│   │   │   │       ├── config.py
│   │   │   │       ├── gateway.py
│   │   │   │       └── ...
│   │   │   └── ws/
│   │   │       ├── __init__.py
│   │   │       ├── router.py      # WebSocket 路由
│   │   │       ├── manager.py     # 连接管理
│   │   │       └── handlers.py    # 消息处理器
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── hermes_cli.py      # CLI 执行封装
│   │   │   ├── hermes_proxy.py    # HTTP 代理封装
│   │   │   ├── state_db.py        # SQLite 只读访问
│   │   │   ├── event_bus.py       # 内部事件总线
│   │   │   └── security.py        # 认证/授权
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── monitor_service.py # 监控轮询服务
│   │   │   ├── log_collector.py   # 日志收集器
│   │   │   └── job_queue.py       # 后台任务队列
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── parsers.py         # CLI 输出解析
│   │       └── helpers.py         # 辅助函数
│   │
│   ├── tests/
│   ├── __init__.py
│   ├── test_api/
│   └── test_ws/
│
├── scripts/
│   └── startup.sh                 # 启动脚本
│
├── pyproject.toml                 # Poetry 依赖
├── requirements.txt               # pip 依赖
├── Dockerfile
└── README.md
│
└── frontend/                      # 前端项目 (Next.js/React)
    ├── app/
    ├── components/
    ├── hooks/
    └── lib/
```

---

## API 设计规范

### 统一响应格式

所有 API 响应（REST 和 WebSocket）均采用统一 JSON 格式：

```typescript
interface ApiResponse<T> {
  code: number;      // 0 表示成功，非 0 表示错误码
  reason: string;    // 成功时为 "success" 或描述信息，失败时为错误详情
  data: T;           // 响应数据，类型根据接口而定
}
```

**成功响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "version": "2.5.1",
    "status": "running"
  }
}
```

**错误响应示例**：
```json
{
  "code": 1001,
  "reason": "session not found: abc123",
  "data": null
}
```

**错误码定义**：
| 错误码 | 含义 | 说明 |
|--------|------|------|
| 0 | 成功 | 请求处理成功 |
| 1000 | 通用错误 | 未分类的错误 |
| 1001 | 资源不存在 | 请求的资源不存在 |
| 1002 | 参数错误 | 请求参数不合法 |
| 1003 | 认证失败 | API Key 无效或过期 |
| 1004 | 权限不足 | 无权限执行此操作 |
| 1005 | CLI 执行失败 | Hermes CLI 命令执行失败 |
| 1006 | 超时 | 请求处理超时 |
| 1007 | 服务不可用 | Hermes 服务未运行 |
| 2000 | WebSocket 错误 | 连接或消息处理错误 |

---

## REST API 详细设计

### 基础信息

```yaml
Base URL: http://localhost:8000/api/v1
Docs: http://localhost:8000/docs (Swagger UI)
OpenAPI: http://localhost:8000/openapi.json

认证 Header:
  Authorization: Bearer <MONITOR_API_KEY>
  X-Hermes-Profile: <profile_name>  (多实例场景)

请求/响应格式: JSON
Content-Type: application/json
```

### API 端点总览

#### 1. 系统状态 (只读监控)

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/system/status` | 获取系统整体状态 |
| GET | `/api/v1/system/doctor` | 运行诊断检查 |
| GET | `/api/v1/system/version` | 获取版本信息 |
| GET | `/api/v1/system/health` | 健康检查 |

**请求示例**：
```http
GET /api/v1/system/status
Authorization: Bearer sk-monitor-xxx
```

**响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "version": "2.5.1",
    "config_loaded": true,
    "auth_status": "authenticated",
    "components": {
      "cli": true,
      "gateway": true,
      "cron": false,
      "memory": true
    },
    "model": {
      "provider": "anthropic",
      "model_name": "claude-sonnet-4"
    },
    "timestamp": "2025-03-05T10:30:00Z"
  }
}
```

#### 2. 会话管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/sessions` | 列出会话（支持分页、过滤） |
| GET | `/api/v1/sessions/{id}` | 获取会话详情 |
| POST | `/api/v1/sessions/{id}/rename` | 重命名会话 |
| GET | `/api/v1/sessions/{id}/export` | 导出单个会话（JSONL） |
| POST | `/api/v1/sessions/export` | 批量导出（按条件） |
| DELETE | `/api/v1/sessions/{id}` | 删除会话 |
| POST | `/api/v1/sessions/prune` | 清理旧会话 |
| GET | `/api/v1/sessions/stats` | 会话统计 |

**GET /api/v1/sessions 请求参数**：
```
?source=cli|telegram|discord&limit=20&offset=0&status=active
```

**GET /api/v1/sessions 响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "sessions": [
      {
        "id": "20250305_091523_a1b2c3d4",
        "name": "session_20250305_091523",
        "title": "调试认证流程",
        "preview": "用户: 如何配置API密钥?",
        "source": "cli",
        "status": "active",
        "message_count": 24,
        "created_at": "2025-03-05T09:15:23Z",
        "updated_at": "2025-03-05T10:30:00Z"
      }
    ],
    "pagination": {
      "total": 142,
      "limit": 20,
      "offset": 0,
      "has_more": true
    }
  }
}
```

**POST /api/v1/sessions/{id}/rename 请求体**：
```json
{
  "title": "新的会话标题"
}
```

**POST /api/v1/sessions/{id}/rename 响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "id": "20250305_091523_a1b2c3d4",
    "title": "新的会话标题",
    "updated_at": "2025-03-05T11:00:00Z"
  }
}
```

#### 3. 配置管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/config` | 获取完整配置 |
| GET | `/api/v1/config/{key}` | 获取特定配置项 |
| POST | `/api/v1/config` | 设置配置项 |
| POST | `/api/v1/config/batch` | 批量设置 |
| POST | `/api/v1/config/check` | 检查配置完整性 |
| POST | `/api/v1/config/migrate` | 迁移配置 |

**POST /api/v1/config 请求体**：
```json
{
  "key": "model",
  "value": "anthropic/claude-opus-4"
}
```

**POST /api/v1/config 响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "key": "model",
    "value": "anthropic/claude-opus-4",
    "previous_value": "anthropic/claude-sonnet-4"
  }
}
```

#### 4. 网关管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/gateway/status` | 网关状态 |
| POST | `/api/v1/gateway/start` | 启动网关 |
| POST | `/api/v1/gateway/stop` | 停止网关 |
| POST | `/api/v1/gateway/restart` | 重启网关 |
| GET | `/api/v1/gateway/platforms` | 平台列表 |
| POST | `/api/v1/gateway/setup` | 配置平台 |

**GET /api/v1/gateway/status 响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "running": true,
    "service_type": "systemd",
    "uptime": 86400,
    "pid": 1234,
    "connected_platforms": ["telegram", "discord"],
    "platforms": [
      {
        "platform": "telegram",
        "status": "connected",
        "webhook_url": "https://...",
        "last_activity": "2025-03-05T10:30:00Z",
        "stats": {
          "messages_received": 1234,
          "messages_sent": 567
        }
      }
    ]
  }
}
```

#### 5. 认证管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/auth/providers` | 提供商列表 |
| GET | `/api/v1/auth/credentials` | 池化凭证列表 |
| POST | `/api/v1/auth/login` | 添加认证 |
| POST | `/api/v1/auth/logout` | 清除认证 |
| DELETE | `/api/v1/auth/credentials/{id}` | 移除凭证 |
| POST | `/api/v1/auth/reset` | 重置耗尽状态 |

**GET /api/v1/auth/providers 响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "providers": [
      {
        "name": "anthropic",
        "authenticated": true,
        "exhausted": false,
        "last_used": "2025-03-05T10:00:00Z"
      },
      {
        "name": "openai",
        "authenticated": false
      }
    ]
  }
}
```

#### 6. 技能管理

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/skills` | 已安装技能列表 |
| GET | `/api/v1/skills/search` | 搜索技能 |
| POST | `/api/v1/skills/install` | 安装技能 |
| POST | `/api/v1/skills/{name}/enable` | 启用技能 |
| POST | `/api/v1/skills/{name}/disable` | 禁用技能 |
| DELETE | `/api/v1/skills/{name}` | 卸载技能 |

#### 7. 日志查询

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/v1/logs` | 查询日志 |
| GET | `/api/v1/logs/errors` | 错误日志 |
| GET | `/api/v1/logs/stream` | SSE 流式日志 |

**GET /api/v1/logs 请求参数**：
```
?component=agent|gateway|cli|tools|cron|system
&level=DEBUG|INFO|WARN|ERROR
&since=1h|1d|7d
&search=keyword
&limit=50&offset=0
```

**GET /api/v1/logs 响应示例**：
```json
{
  "code": 0,
  "reason": "success",
  "data": {
    "logs": [
      {
        "id": "log_001",
        "timestamp": "2025-03-05T10:30:00Z",
        "level": "INFO",
        "component": "agent",
        "message": "Processing user query...",
        "session_id": "20250305_091523_a1b2c3d4"
      }
    ],
    "pagination": {
      "total": 1000,
      "limit": 50,
      "offset": 0,
      "has_more": true
    }
  }
}
```

#### 8. 数据分析

```http
GET /api/v1/insights?days=30         # 使用洞察
GET /api/v1/insights/models          # 模型使用统计
GET /api/v1/insights/tools           # 工具使用统计
GET /api/v1/insights/daily           # 每日统计
```

#### 9. 反向代理 (透传 Hermes 内置 API)

```http
# 以下路径反向代理到 http://127.0.0.1:8642/v1/*
POST   /api/v1/proxy/chat/completions
POST   /api/v1/proxy/responses
GET    /api/v1/proxy/models
GET    /api/v1/proxy/responses/{id}
DELETE /api/v1/proxy/responses/{id}
```

---

## WebSocket 接口设计

### 连接端点

```
ws://localhost:8000/ws?token=<MONITOR_API_KEY>&profile=<name>
```

### 消息协议规范

WebSocket 消息采用与 REST API 统一的响应格式：

```typescript
// WebSocket 消息格式
interface WSMessage<T> {
  id: string;           // 消息唯一 ID
  type: string;         // 消息类型
  direction: "S->C" | "C->S";  // S->C: 服务端推送, C->S: 客户端请求
  timestamp: number;    // 毫秒时间戳
  payload: T;           // 消息载荷
}

// 统一响应格式（适用于 C->S 请求的响应）
interface WSResponse<T> {
  id: string;           // 对应请求的消息 ID
  type: string;         // 响应类型 (通常为 request_id + ".response")
  direction: "S->C";    // 服务端返回
  timestamp: number;
  payload: {
    code: number;       // 0 成功，非 0 错误
    reason: string;     // 成功/失败描述
    data: T;            // 响应数据
  };
}
```

### 消息流向总览

| 消息类型 | 方向 | 说明 |
|----------|------|------|
| `system.status` | S->C | 服务端推送系统状态更新 |
| `agent.status` | S->C | 服务端推送 Agent 状态变更 |
| `log.stream` | S->C | 服务端推送实时日志 |
| `tool.progress` | S->C | 服务端推送工具执行进度 |
| `approval.request` | S->C | 服务端推送审批请求 |
| `session.event` | S->C | 服务端推送会话事件 |
| `gateway.status` | S->C | 服务端推送网关状态 |
| `heartbeat` | S->C | 服务端心跳 |
| `subscribe` | C->S | 客户端订阅事件 |
| `unsubscribe` | C->S | 客户端取消订阅 |
| `approval.response` | C->S | 客户端响应审批请求 |
| `interrupt` | C->S | 客户端中断会话 |
| `command.execute` | C->S | 客户端执行命令 |
| `ping` | C->S | 客户端心跳 |

---

### S->C 消息（服务端推送）

#### 1. 系统状态更新 (system.status)
**方向**: S->C
**触发时机**: 系统状态变更、定时轮询
**频率**: 30秒

```json
{
  "id": "msg_001",
  "type": "system.status",
  "direction": "S->C",
  "timestamp": 1704067200000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "version": "2.5.1",
      "config_loaded": true,
      "auth_status": "authenticated",
      "components": {
        "cli": true,
        "gateway": true,
        "cron": false,
        "memory": true
      },
      "model": {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4"
      },
      "timestamp": "2025-03-05T10:30:00Z"
    }
  }
}
```

#### 2. Agent 状态更新 (agent.status)
**方向**: S->C
**触发时机**: Agent 状态变更
**频率**: 10秒或状态变更时

```json
{
  "id": "msg_002",
  "type": "agent.status",
  "direction": "S->C",
  "timestamp": 1704067201000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "agent_id": "session_abc123",
      "status": "working",
      "current_activity": {
        "type": "tool_call",
        "description": "Executing: web_search",
        "started_at": 1704067200000
      },
      "metrics": {
        "total_messages": 24,
        "total_tokens": 3500
      }
    }
  }
}
```

#### 3. 实时日志 (log.stream)
**方向**: S->C
**触发时机**: 新日志产生
**频率**: 实时流

```json
{
  "id": "msg_003",
  "type": "log.stream",
  "direction": "S->C",
  "timestamp": 1704067202000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "id": "log_001",
      "timestamp": "2025-03-05T10:30:00Z",
      "level": "INFO",
      "component": "agent",
      "message": "Processing user query...",
      "session_id": "session_abc123",
      "metadata": {}
    }
  }
}
```

#### 4. 工具进度 (tool.progress)
**方向**: S->C
**触发时机**: 工具执行状态变更
**频率**: 实时

```json
{
  "id": "msg_004",
  "type": "tool.progress",
  "direction": "S->C",
  "timestamp": 1704067203000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "tool_call_id": "call_001",
      "session_id": "session_abc123",
      "tool": "web_search",
      "status": "running",
      "progress": 50,
      "message": "Searching: 'Python FastAPI tutorial'",
      "intermediate_results": []
    }
  }
}
```

#### 5. 审批请求 (approval.request)
**方向**: S->C
**触发时机**: 需要用户审批的操作

```json
{
  "id": "msg_005",
  "type": "approval.request",
  "direction": "S->C",
  "timestamp": 1704067204000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "request_id": "req_001",
      "session_id": "session_abc123",
      "type": "tool_call",
      "tool": "terminal",
      "command": "rm -rf /important/data",
      "risk": "high",
      "timeout": 30
    }
  }
}
```

#### 6. 会话事件 (session.event)
**方向**: S->C
**触发时机**: 会话生命周期事件

```json
{
  "id": "msg_006",
  "type": "session.event",
  "direction": "S->C",
  "timestamp": 1704067205000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "event_type": "created|updated|deleted|completed",
      "session_id": "session_abc123",
      "session": {
        "id": "session_abc123",
        "title": "新会话",
        "status": "active"
      }
    }
  }
}
```

#### 7. 网关状态 (gateway.status)
**方向**: S->C
**触发时机**: 网关状态变更
**频率**: 30秒

```json
{
  "id": "msg_007",
  "type": "gateway.status",
  "direction": "S->C",
  "timestamp": 1704067206000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "running": true,
      "service_type": "systemd",
      "uptime": 86400,
      "connected_platforms": ["telegram", "discord"]
    }
  }
}
```

#### 8. 服务端心跳 (heartbeat)
**方向**: S->C
**触发时机**: 定时心跳
**频率**: 30秒

```json
{
  "id": "msg_008",
  "type": "heartbeat",
  "direction": "S->C",
  "timestamp": 1704067207000,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "server_time": "2025-03-05T10:30:07Z",
      "connections": 5
    }
  }
}
```

---

### C->S 消息（客户端请求）

#### 1. 订阅事件 (subscribe)
**方向**: C->S
**说明**: 客户端订阅指定类型的事件

**请求**：
```json
{
  "id": "client_001",
  "type": "subscribe",
  "direction": "C->S",
  "timestamp": 1704067200000,
  "payload": {
    "events": ["agent.status", "log.stream"],
    "session_id": "session_abc123"
  }
}
```

**响应** (S->C)：
```json
{
  "id": "client_001",
  "type": "subscribe.response",
  "direction": "S->C",
  "timestamp": 1704067200100,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "subscribed": ["agent.status", "log.stream"],
      "client_id": "ws_client_001"
    }
  }
}
```

#### 2. 取消订阅 (unsubscribe)
**方向**: C->S

**请求**：
```json
{
  "id": "client_002",
  "type": "unsubscribe",
  "direction": "C->S",
  "timestamp": 1704067201000,
  "payload": {
    "events": ["log.stream"]
  }
}
```

**响应**：
```json
{
  "id": "client_002",
  "type": "unsubscribe.response",
  "direction": "S->C",
  "timestamp": 1704067201100,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "unsubscribed": ["log.stream"]
    }
  }
}
```

#### 3. 审批响应 (approval.response)
**方向**: C->S
**说明**: 客户端响应审批请求

**请求**：
```json
{
  "id": "client_003",
  "type": "approval.response",
  "direction": "C->S",
  "timestamp": 1704067205000,
  "payload": {
    "request_id": "req_001",
    "approved": false,
    "reason": "Too dangerous"
  }
}
```

**响应**：
```json
{
  "id": "client_003",
  "type": "approval.response.response",
  "direction": "S->C",
  "timestamp": 1704067205100,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "request_id": "req_001",
      "processed": true
    }
  }
}
```

#### 4. 中断会话 (interrupt)
**方向**: C->S

**请求**：
```json
{
  "id": "client_004",
  "type": "interrupt",
  "direction": "C->S",
  "timestamp": 1704067206000,
  "payload": {
    "session_id": "session_abc123"
  }
}
```

**响应**：
```json
{
  "id": "client_004",
  "type": "interrupt.response",
  "direction": "S->C",
  "timestamp": 1704067206100,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "session_id": "session_abc123",
      "interrupted": true
    }
  }
}
```

#### 5. 执行命令 (command.execute)
**方向**: C->S
**说明**: 客户端请求执行 CLI 命令

**请求**：
```json
{
  "id": "client_005",
  "type": "command.execute",
  "direction": "C->S",
  "timestamp": 1704067207000,
  "payload": {
    "command": ["sessions", "list", "--limit", "10"],
    "async": false
  }
}
```

**响应**（同步）：
```json
{
  "id": "client_005",
  "type": "command.execute.response",
  "direction": "S->C",
  "timestamp": 1704067207500,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "stdout": "...",
      "stderr": "",
      "returncode": 0,
      "duration_ms": 450
    }
  }
}
```

#### 6. 客户端心跳 (ping)
**方向**: C->S

**请求**：
```json
{
  "id": "client_006",
  "type": "ping",
  "direction": "C->S",
  "timestamp": 1704067208000,
  "payload": {}
}
```

**响应** (pong)：
```json
{
  "id": "client_006",
  "type": "pong",
  "direction": "S->C",
  "timestamp": 1704067208100,
  "payload": {
    "code": 0,
    "reason": "success",
    "data": {
      "server_time": "2025-03-05T10:30:08Z"
    }
  }
}
```

---

## 数据模型

### 核心实体

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional, Any
from enum import Enum

# ==================== 枚举类型 ====================

class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class Component(str, Enum):
    AGENT = "agent"
    GATEWAY = "gateway"
    CLI = "cli"
    TOOLS = "tools"
    CRON = "cron"
    SYSTEM = "system"
    MCP = "mcp"

class SessionSource(str, Enum):
    CLI = "cli"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    EMAIL = "email"
    HOMEASSISTANT = "homeassistant"

# ==================== 系统状态 ====================

class SystemStatus(BaseModel):
    version: str
    config_loaded: bool
    auth_status: Literal["authenticated", "not_authenticated", "error"]
    components: dict[str, bool]
    model: dict[str, str]
    timestamp: datetime

class ComponentStatus(BaseModel):
    name: str
    running: bool
    uptime: Optional[int] = None
    last_error: Optional[str] = None

# ==================== 会话 ====================

class Session(BaseModel):
    id: str
    name: str
    title: Optional[str] = None
    preview: Optional[str] = None
    source: SessionSource
    status: Literal["active", "paused", "completed"]
    message_count: int
    created_at: datetime
    updated_at: datetime
    parent_id: Optional[str] = None
    skill_names: list[str] = []
    model: Optional[str] = None

class SessionDetail(Session):
    messages: list["Message"] = []

class Message(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    model: Optional[str] = None
    tokens: Optional[int] = None
    tool_calls: list["ToolCall"] = []

# ==================== 工具调用 ====================

class ToolCall(BaseModel):
    id: str
    tool: str
    input: dict[str, Any]
    output: Optional[Any] = None
    status: Literal["pending", "running", "completed", "error"]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None

class ToolProgress(BaseModel):
    tool_call_id: str
    session_id: str
    tool: str
    status: str
    progress: int  # 0-100
    message: str
    intermediate_results: list[Any] = []

# ==================== 网关 ====================

class GatewayStatus(BaseModel):
    running: bool
    service_type: Literal["systemd", "launchd", "foreground", "none"]
    uptime: Optional[int] = None
    pid: Optional[int] = None
    connected_platforms: list[str]
    platforms: list["PlatformStatus"] = []

class PlatformStatus(BaseModel):
    platform: str
    status: Literal["connected", "disconnected", "error"]
    webhook_url: Optional[str] = None
    last_activity: Optional[datetime] = None
    stats: dict[str, int] = {}

# ==================== 日志 ====================

class LogEntry(BaseModel):
    id: str
    timestamp: datetime
    level: LogLevel
    component: Component
    message: str
    session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    metadata: dict[str, Any] = {}

# ==================== 洞察统计 ====================

class Insights(BaseModel):
    period: dict[str, Any]
    summary: dict[str, Any]
    by_model: dict[str, "ModelStats"]
    by_source: dict[str, int]
    by_tool: dict[str, "ToolStats"]
    daily: list["DailyStats"]

class ModelStats(BaseModel):
    sessions: int
    messages: int
    tokens: int
    cost: Optional[float] = None

class ToolStats(BaseModel):
    calls: int
    success_rate: float
    average_duration_ms: int

class DailyStats(BaseModel):
    date: str
    sessions: int
    messages: int
    tokens: int
    cost: Optional[float] = None

# ==================== 技能 ====================

class Skill(BaseModel):
    name: str
    version: str
    description: str
    author: Optional[str] = None
    installed: bool = False
    enabled: bool = False
    config: dict[str, Any] = {}
    slash_commands: list[str] = []

# ==================== 像素办公室 (前端展示) ====================

class PixelAgent(BaseModel):
    id: str
    name: str
    display_name: str
    type: Literal["cli", "gateway", "session", "worker", "cron"]
    position: dict[str, int]
    status: AgentStatus
    current_activity: Optional[dict[str, Any]] = None
    appearance: dict[str, Any]
    metrics: dict[str, Any]
    session_id: Optional[str] = None
    platform: Optional[str] = None
```

---

## 与 Hermes API Server 集成

### 内置 API Server 配置

```bash
# ~/.hermes/.env
API_SERVER_ENABLED=true
API_SERVER_KEY=change-me-local-dev
API_SERVER_PORT=8642
API_SERVER_HOST=127.0.0.1
API_SERVER_CORS_ORIGINS=http://localhost:3000
```

启动后可用端点：
- `POST http://localhost:8642/v1/chat/completions`
- `POST http://localhost:8642/v1/responses`
- `GET  http://localhost:8642/v1/models`
- `GET  http://localhost:8642/v1/responses/{id}`
- `GET  http://localhost:8642/health`

### 外挂系统反向代理配置

```python
# app/core/hermes_proxy.py
import httpx
from fastapi import Request, Response
from app.config import settings

HERMES_BASE_URL = f"http://{settings.hermes_api_host}:{settings.hermes_api_port}"

async def proxy_to_hermes(request: Request, path: str) -> Response:
    """
    反向代理请求到 Hermes 内置 API Server
    同时记录审计日志（可选）
    """
    body = await request.body()
    headers = {
        "Authorization": f"Bearer {settings.hermes_api_key}",
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.request(
            method=request.method,
            url=f"{HERMES_BASE_URL}{path}",
            headers=headers,
            content=body,
            params=request.query_params
        )

        # 可选：记录审计日志
        await audit_logger.log_request(request, response)

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers={
                "Content-Type": response.headers.get("Content-Type", "application/json"),
                "X-Proxy-By": "hermes-monitor-api"
            }
        )

# SSE 流式代理
async def proxy_stream_to_hermes(request: Request, path: str):
    """代理 SSE 流式响应"""
    body = await request.body()
    headers = {"Authorization": f"Bearer {settings.hermes_api_key}"}

    async with httpx.AsyncClient() as client:
        async with client.stream(
            method=request.method,
            url=f"{HERMES_BASE_URL}{path}",
            headers=headers,
            content=body
        ) as response:
            async for chunk in response.aiter_bytes():
                yield chunk
```

### 代理路由注册

```python
# app/api/v1/endpoints/proxy.py
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from app.core.hermes_proxy import proxy_to_hermes, proxy_stream_to_hermes

router = APIRouter()

@router.post("/chat/completions")
async def proxy_chat_completions(request: Request):
    """代理到 Hermes /v1/chat/completions"""
    body = await request.json()

    # 检查是否流式请求
    if body.get("stream", False):
        return StreamingResponse(
            proxy_stream_to_hermes(request, "/v1/chat/completions"),
            media_type="text/event-stream"
        )

    return await proxy_to_hermes(request, "/v1/chat/completions")

@router.post("/responses")
async def proxy_responses(request: Request):
    """代理到 Hermes /v1/responses"""
    body = await request.json()

    if body.get("stream", False):
        return StreamingResponse(
            proxy_stream_to_hermes(request, "/v1/responses"),
            media_type="text/event-stream"
        )

    return await proxy_to_hermes(request, "/v1/responses")

@router.get("/models")
async def proxy_models(request: Request):
    """代理到 Hermes /v1/models"""
    return await proxy_to_hermes(request, "/v1/models")

@router.get("/responses/{response_id}")
async def proxy_get_response(response_id: str, request: Request):
    """代理到 Hermes /v1/responses/{id}"""
    return await proxy_to_hermes(request, f"/v1/responses/{response_id}")

@router.delete("/responses/{response_id}")
async def proxy_delete_response(response_id: str, request: Request):
    """代理到 Hermes DELETE /v1/responses/{id}"""
    return await proxy_to_hermes(request, f"/v1/responses/{response_id}")
```

---

## 核心服务实现

### 1. CLI 执行器

```python
# app/core/hermes_cli.py
import asyncio
import subprocess
from typing import Optional, AsyncGenerator
from dataclasses import dataclass

@dataclass
class CLIResult:
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int

class HermesCLIError(Exception):
    pass

class HermesCLI:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.env = self._prepare_env()

    def _prepare_env(self) -> dict:
        """准备环境变量，确保 hermes 在 PATH 中"""
        import os
        home = os.environ.get("HOME", "")
        path = os.environ.get("PATH", "")
        return {
            **os.environ,
            "PATH": f"{home}/.local/bin:/usr/local/bin:{path}"
        }

    async def run(
        self,
        args: list[str],
        timeout: Optional[int] = None
    ) -> CLIResult:
        """执行 hermes CLI 命令"""
        cmd = ["hermes"] + args
        timeout = timeout or self.timeout

        start_time = asyncio.get_event_loop().time()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )

            duration_ms = int(
                (asyncio.get_event_loop().time() - start_time) * 1000
            )

            return CLIResult(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                returncode=proc.returncode,
                duration_ms=duration_ms
            )

        except asyncio.TimeoutError:
            proc.kill()
            raise HermesCLIError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    async def stream(
        self,
        args: list[str]
    ) -> AsyncGenerator[str, None]:
        """流式执行命令（如 logs -f）"""
        cmd = ["hermes"] + args

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env
        )

        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", errors="replace").rstrip()
        finally:
            proc.kill()
            await proc.wait()

    # ===== 常用命令封装 =====

    async def get_status(self) -> dict:
        """获取 hermes status"""
        result = await self.run(["status", "--json"])
        if result.returncode != 0:
            raise HermesCLIError(result.stderr)
        import json
        return json.loads(result.stdout)

    async def get_config(self) -> dict:
        """获取 hermes config"""
        result = await self.run(["config", "show", "--json"])
        if result.returncode != 0:
            raise HermesCLIError(result.stderr)
        import json
        return json.loads(result.stdout)

    async def list_sessions(
        self,
        source: Optional[str] = None,
        limit: int = 20
    ) -> list[dict]:
        """获取会话列表"""
        args = ["sessions", "list", "--limit", str(limit)]
        if source:
            args.extend(["--source", source])

        result = await self.run(args)
        if result.returncode != 0:
            raise HermesCLIError(result.stderr)

        # 解析 stdout（可能是 JSON 或表格格式）
        import json
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            # 解析表格格式
            return self._parse_table_output(result.stdout)

    def _parse_table_output(self, output: str) -> list[dict]:
        """解析 hermes 表格输出为字典列表"""
        lines = output.strip().split("\n")
        if len(lines) < 2:
            return []

        # 假设第一行是表头
        headers = [h.strip() for h in lines[0].split()]
        results = []

        for line in lines[1:]:
            if line.strip() and not line.startswith("-"):
                values = [v.strip() for v in line.split()]
                if len(values) >= len(headers):
                    results.append(dict(zip(headers, values)))

        return results

# 全局 CLI 实例
hermes_cli = HermesCLI()
```

### 2. 状态数据库访问

```python
# app/core/state_db.py
import sqlite3
import json
from contextlib import contextmanager
from typing import Optional, Generator
from app.config import settings

class StateDB:
    """只读访问 Hermes state.db"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.hermes_state_db_path

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取只读连接"""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_session(self, session_id: str) -> Optional[dict]:
        """获取会话详情"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_session_messages(
        self,
        session_id: str,
        limit: int = 100
    ) -> list[dict]:
        """获取会话消息"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_sessions(
        self,
        limit: int = 20,
        source: Optional[str] = None
    ) -> list[dict]:
        """获取最近会话"""
        with self._get_connection() as conn:
            if source:
                cursor = conn.execute(
                    """
                    SELECT * FROM sessions
                    WHERE source = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (source, limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM sessions
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """获取数据库统计"""
        with self._get_connection() as conn:
            stats = {}

            # 会话统计
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            stats["total_sessions"] = cursor.fetchone()[0]

            # 消息统计
            cursor = conn.execute("SELECT COUNT(*) FROM messages")
            stats["total_messages"] = cursor.fetchone()[0]

            # 按来源统计
            cursor = conn.execute(
                "SELECT source, COUNT(*) FROM sessions GROUP BY source"
            )
            stats["by_source"] = {row[0]: row[1] for row in cursor.fetchall()}

            return stats

# 全局实例
state_db = StateDB()
```

### 3. 监控服务

```python
# app/services/monitor_service.py
import asyncio
from typing import Callable, Any
from datetime import datetime
from app.core.hermes_cli import hermes_cli
from app.api.ws.manager import WebSocketManager

class MonitorService:
    """后台监控服务，定期轮询 Hermes 状态"""

    def __init__(self, ws_manager: WebSocketManager):
        self.ws_manager = ws_manager
        self.running = False
        self.tasks = []

        # 配置轮询间隔（秒）
        self.intervals = {
            "system_status": 30,
            "gateway_status": 30,
            "sessions": 10,
            "logs": 5,
        }

        # 缓存
        self._cache = {}

    async def start(self):
        """启动监控服务"""
        self.running = True

        self.tasks = [
            asyncio.create_task(self._poll_system_status()),
            asyncio.create_task(self._poll_gateway_status()),
            asyncio.create_task(self._poll_sessions()),
            asyncio.create_task(self._stream_logs()),
        ]

    async def stop(self):
        """停止监控服务"""
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _poll_system_status(self):
        """轮询系统状态"""
        while self.running:
            try:
                status = await hermes_cli.get_status()

                # 检查变化
                if status != self._cache.get("system_status"):
                    self._cache["system_status"] = status
                    await self.ws_manager.broadcast({
                        "type": "system.status",
                        "direction": "S->C",
                        "payload": {
                            "code": 0,
                            "reason": "success",
                            "data": status
                        }
                    })

            except Exception as e:
                print(f"Error polling system status: {e}")

            await asyncio.sleep(self.intervals["system_status"])

    async def _poll_gateway_status(self):
        """轮询网关状态"""
        while self.running:
            try:
                result = await hermes_cli.run(["gateway", "status"])
                # 解析输出...

            except Exception as e:
                print(f"Error polling gateway status: {e}")

            await asyncio.sleep(self.intervals["gateway_status"])

    async def _poll_sessions(self):
        """轮询会话列表"""
        while self.running:
            try:
                sessions = await hermes_cli.list_sessions(limit=50)

                await self.ws_manager.broadcast({
                    "type": "sessions.update",
                    "direction": "S->C",
                    "payload": {
                        "code": 0,
                        "reason": "success",
                        "data": {"sessions": sessions, "count": len(sessions)}
                    }
                })

            except Exception as e:
                print(f"Error polling sessions: {e}")

            await asyncio.sleep(self.intervals["sessions"])

    async def _stream_logs(self):
        """流式收集日志"""
        while self.running:
            try:
                async for line in hermes_cli.stream(["logs", "-f"]):
                    # 解析日志行
                    log_entry = self._parse_log_line(line)
                    if log_entry:
                        await self.ws_manager.broadcast({
                            "type": "log.stream",
                            "direction": "S->C",
                            "payload": {
                                "code": 0,
                                "reason": "success",
                                "data": log_entry
                            }
                        })

            except Exception as e:
                print(f"Error streaming logs: {e}")
                await asyncio.sleep(5)  # 出错后等待重连

    def _parse_log_line(self, line: str) -> Optional[dict]:
        """解析日志行"""
        # 实现日志解析逻辑
        return {"message": line, "level": "INFO"}
```

### 4. WebSocket 管理器

```python
# app/api/ws/manager.py
from typing import Dict, Set
from fastapi import WebSocket
import json

class WebSocketManager:
    """WebSocket 连接管理"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # event_type -> set of client_ids

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

        # 清理订阅
        for event_type in self.subscriptions:
            self.subscriptions[event_type].discard(client_id)

    async def send_to(self, client_id: str, message: dict):
        """发送消息给特定客户端"""
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

    async def broadcast(self, message: dict):
        """广播给所有客户端"""
        disconnected = []
        for client_id, ws in self.active_connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)

        # 清理断开的连接
        for client_id in disconnected:
            self.disconnect(client_id)

    async def broadcast_to_subscribers(self, event_type: str, message: dict):
        """广播给订阅者"""
        subscribers = self.subscriptions.get(event_type, set())
        for client_id in subscribers:
            await self.send_to(client_id, message)

    def subscribe(self, client_id: str, event_types: list[str]):
        """订阅事件"""
        for event_type in event_types:
            if event_type not in self.subscriptions:
                self.subscriptions[event_type] = set()
            self.subscriptions[event_type].add(client_id)

    def unsubscribe(self, client_id: str, event_types: list[str]):
        """取消订阅"""
        for event_type in event_types:
            if event_type in self.subscriptions:
                self.subscriptions[event_type].discard(client_id)

# 全局实例
ws_manager = WebSocketManager()
```

---

## 部署配置

### 环境变量

```bash
# .env
# FastAPI 配置
APP_NAME=hermes-monitor-api
APP_VERSION=1.0.0
DEBUG=false
HOST=0.0.0.0
PORT=8000
WORKERS=4

# 认证
API_KEY=your-monitor-api-key
JWT_SECRET=your-jwt-secret

# Hermes 配置
HERMES_PROFILE=default
HERMES_STATE_DB_PATH=~/.hermes/state.db

# Hermes API Server (内置)
HERMES_API_HOST=127.0.0.1
HERMES_API_PORT=8642
HERMES_API_KEY=change-me-local-dev

# CORS
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com

# 日志
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Docker Compose

```yaml
# docker-compose.yml
version: "3.8"

services:
  hermes-monitor-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - API_KEY=${API_KEY}
      - HERMES_API_KEY=${HERMES_API_KEY}
      - HERMES_API_HOST=host.docker.internal
    volumes:
      - ~/.hermes:/app/.hermes:ro
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - hermes-gateway
    networks:
      - hermes-net

  hermes-gateway:
    image: hermes-agent:latest
    command: ["hermes", "gateway"]
    ports:
      - "8642:8642"
    environment:
      - API_SERVER_ENABLED=true
      - API_SERVER_KEY=${HERMES_API_KEY}
      - API_SERVER_PORT=8642
      - API_SERVER_HOST=0.0.0.0
    volumes:
      - ~/.hermes:/root/.hermes
    networks:
      - hermes-net

networks:
  hermes-net:
    driver: bridge
```

---

## 前端集成示例

### WebSocket 连接

```typescript
// frontend/lib/websocket.ts
class HermesMonitorWS {
  private ws: WebSocket | null = null;
  private reconnectInterval = 3000;
  private maxReconnectAttempts = 10;
  private reconnectAttempts = 0;

  constructor(private url: string, private token: string) {}

  connect() {
    this.ws = new WebSocket(`${this.url}?token=${this.token}`);

    this.ws.onopen = () => {
      console.log('Connected to Hermes Monitor');
      this.reconnectAttempts = 0;

      // 订阅事件
      this.send({
        type: 'subscribe',
        payload: {
          events: ['system.status', 'agent.status', 'log.stream']
        }
      });
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };

    this.ws.onclose = () => {
      this.reconnect();
    };
  }

  private reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), this.reconnectInterval);
    }
  }

  send(message: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  handleMessage(message: any) {
    switch (message.type) {
      case 'system.status':
        // 更新系统状态 UI
        break;
      case 'agent.status':
        // 更新像素办公室动画
        break;
      case 'log.stream':
        // 追加日志到面板
        break;
      case 'approval.request':
        // 显示审批弹窗
        this.showApprovalDialog(message.payload);
        break;
    }
  }

  approveTool(requestId: string, approved: boolean, reason?: string) {
    this.send({
      type: 'approval.response',
      payload: { requestId, approved, reason }
    });
  }
}
```

### API 客户端

```typescript
// frontend/lib/api.ts
const API_BASE = 'http://localhost:8000/api/v1';

class HermesMonitorAPI {
  private token: string;

  constructor(token: string) {
    this.token = token;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
        ...options?.headers
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return response.json();
  }

  // 系统状态
  async getSystemStatus() {
    return this.request('/system/status');
  }

  // 会话管理
  async listSessions(params?: { source?: string; limit?: number }) {
    const query = new URLSearchParams(params as any).toString();
    return this.request(`/sessions?${query}`);
  }

  async getSession(id: string) {
    return this.request(`/sessions/${id}`);
  }

  async renameSession(id: string, title: string) {
    return this.request(`/sessions/${id}/rename`, {
      method: 'POST',
      body: JSON.stringify({ title })
    });
  }

  // 配置管理
  async getConfig() {
    return this.request('/config');
  }

  async setConfig(key: string, value: any) {
    return this.request('/config', {
      method: 'POST',
      body: JSON.stringify({ key, value })
    });
  }

  // 代理对话请求到 Hermes 内置 API
  async chatCompletion(messages: any[], stream = false) {
    return this.request('/proxy/chat/completions', {
      method: 'POST',
      body: JSON.stringify({ messages, stream })
    });
  }
}
```

---

## 总结

本架构设计明确了 Hermes Agent 监控外挂的定位：**专注于管理面和监控面，复用 Hermes 内置的对话 API**。

### 核心优势

1. **不重复造轮子**: 对话能力完全复用 Hermes 内置的 OpenAI 兼容 API
2. **职责清晰**: 外挂 = 管理 API + 监控 + 审批流，Hermes = 对话执行
3. **同栈开发**: Python + FastAPI 与 Hermes 一致，便于维护
4. **实时双向**: WebSocket 支持工具进度、日志流、审批交互
5. **灵活部署**: 支持反向代理、独立部署、Docker Compose

### 技术亮点

- **CLI 封装**: `subprocess` + `asyncio` 实现同步/异步/流式调用
- **只读数据库**: 直接读取 Hermes SQLite，避免数据不一致
- **SSE 透传**: 流式响应无缝代理，支持 `hermes.tool.progress`
- **多级缓存**: 内存缓存 + 轮询去重，减少 CLI 调用开销
- **审计日志**: 可选记录所有对话请求，满足合规需求

### 后续扩展

- [ ] 多租户支持（按 profile 隔离）
- [ ] 更细粒度的权限控制（RBAC）
- [ ] 历史数据归档（对接 S3/OSS）
- [ ] 告警规则引擎（Prometheus 集成）
- [ ] 机器学习分析（异常检测）


