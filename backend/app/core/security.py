"""
安全模块 - 认证和授权
"""
import logging
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

logger = logging.getLogger(__name__)

# 使用 HTTPBearer 进行 token 认证
security = HTTPBearer(auto_error=False)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    验证 API Key

    Args:
        credentials: HTTP 认证凭证

    Returns:
        str: 验证通过的 API Key

    Raises:
        HTTPException: 认证失败
    """
    if not credentials:
        logger.warning("Missing authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1003, "reason": "Missing authorization header", "data": None}
        )

    token = credentials.credentials

    if token != settings.api_key:
        logger.warning(f"Invalid API key attempted")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 1003, "reason": "Invalid or expired API key", "data": None}
        )

    return token


def create_response(code: int = 0, reason: str = "success", data=None):
    """
    创建统一格式的响应

    Args:
        code: 错误码，0 表示成功
        reason: 描述信息
        data: 响应数据

    Returns:
        dict: 统一格式响应
    """
    return {
        "code": code,
        "reason": reason,
        "data": data
    }


def create_error_response(code: int, reason: str):
    """创建错误响应"""
    return create_response(code=code, reason=reason, data=None)
