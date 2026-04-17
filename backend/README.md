# Hermes Monitor API

基于 FastAPI 的 Hermes Agent 监控与管理外挂系统

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件
```

### 3. 启动服务

```bash
./scripts/start.sh
# 或使用 uvicorn 直接启动
uvicorn app.main:app --reload
```

## API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── api/v1/endpoints/    # API 端点
│   ├── core/                # 核心模块
│   ├── main.py             # 主应用入口
│   └── config.py           # 配置
├── tests/                  # 测试
├── scripts/                # 启动脚本
└── requirements.txt        # 依赖
```

## 核心功能

- **系统状态监控**: GET /api/v1/system/status
- **会话管理**: GET/POST/DELETE /api/v1/sessions
- **网关管理**: GET/POST /api/v1/gateway
- **配置管理**: GET/POST /api/v1/config
- **技能管理**: GET/POST /api/v1/skills
- **日志查询**: GET /api/v1/logs
- **代理对话**: POST /api/v1/proxy/chat/completions

## 认证

所有 API（除 /health 外）需要在请求头中携带：
```
Authorization: Bearer <API_KEY>
```

## 响应格式

统一响应格式：
```json
{
  "code": 0,
  "reason": "success",
  "data": { }
}
```

错误码：
- 0: 成功
- 1001: 资源不存在
- 1002: 参数错误
- 1003: 认证失败
- 1005: CLI 执行失败
