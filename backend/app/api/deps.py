"""
API 依赖注入
"""
from app.core.hermes_cli import get_hermes_cli
from app.core.hermes_proxy import get_hermes_proxy
from app.core.state_db import get_state_db

# 导出常用依赖
__all__ = ["get_hermes_cli", "get_hermes_proxy", "get_state_db"]
