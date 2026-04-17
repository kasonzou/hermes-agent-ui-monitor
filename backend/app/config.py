"""
配置管理模块
使用 Pydantic Settings 管理环境变量和配置
"""
from functools import lru_cache
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # 应用基本信息
    app_name: str = Field(default="hermes-monitor-api", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    debug: bool = Field(default=False, description="调试模式")

    # 服务器配置
    host: str = Field(default="0.0.0.0", description="监听地址")
    port: int = Field(default=8000, description="监听端口")
    workers: int = Field(default=1, description="工作进程数")

    # 认证配置
    api_key: str = Field(default="change-me-local-dev", description="API 认证密钥")
    jwt_secret: Optional[str] = Field(default=None, description="JWT 密钥")
    jwt_algorithm: str = Field(default="HS256", description="JWT 算法")
    jwt_expires_hours: int = Field(default=24, description="JWT 过期时间（小时）")

    # Hermes CLI 配置
    hermes_profile: str = Field(default="default", description="Hermes profile 名称")
    hermes_state_db_path: str = Field(
        default="~/.hermes/state.db",
        description="Hermes SQLite 数据库路径"
    )

    # Hermes API Server 配置（内置 API）
    hermes_api_host: str = Field(default="127.0.0.1", description="Hermes API 主机")
    hermes_api_port: int = Field(default=8642, description="Hermes API 端口")
    hermes_api_key: str = Field(default="", description="Hermes API 密钥")

    # CORS 配置
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        description="允许的 CORS 来源"
    )
    cors_allow_credentials: bool = Field(default=True, description="允许 CORS 携带凭证")
    cors_allow_methods: List[str] = Field(
        default_factory=lambda: ["*"],
        description="允许的 CORS 方法"
    )
    cors_allow_headers: List[str] = Field(
        default_factory=lambda: ["*"],
        description="允许的 CORS 请求头"
    )

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_format: str = Field(default="text", description="日志格式 (text/json)")

    # WebSocket 配置
    ws_heartbeat_interval: int = Field(default=30, description="WebSocket 心跳间隔（秒）")
    ws_max_connections: int = Field(default=100, description="最大 WebSocket 连接数")

    # 监控配置
    monitor_poll_interval: int = Field(default=30, description="监控轮询间隔（秒）")
    log_stream_buffer_size: int = Field(default=1000, description="日志流缓冲区大小")

    @property
    def hermes_api_base_url(self) -> str:
        """Hermes API 基础 URL"""
        return f"http://{self.hermes_api_host}:{self.hermes_api_port}"

    @property
    def hermes_state_db_full_path(self) -> str:
        """Hermes 数据库完整路径（展开 ~）"""
        import os
        return os.path.expanduser(self.hermes_state_db_path)


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 导出配置实例
settings = get_settings()
