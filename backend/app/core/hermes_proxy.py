"""
Hermes API Server HTTP 代理封装
反向代理对话请求到 Hermes 内置 API Server
"""
import logging
from typing import Optional, AsyncGenerator
import httpx
from fastapi import Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from app.config import settings

logger = logging.getLogger(__name__)


class HermesProxyError(Exception):
    """代理错误"""
    pass


class HermesProxy:
    """Hermes API Server 代理"""

    def __init__(self):
        self.base_url = settings.hermes_api_base_url
        self.api_key = settings.hermes_api_key
        self.timeout = 300.0  # 5 分钟超时（用于长对话）

    def _get_headers(self, content_type: Optional[str] = None) -> dict:
        """获取请求头"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def proxy_request(
        self,
        request: Request,
        path: str,
        method: Optional[str] = None
    ) -> Response:
        """
        反向代理请求到 Hermes API Server

        Args:
            request: FastAPI 请求对象
            path: API 路径（如 /v1/chat/completions）
            method: HTTP 方法（默认使用 request.method）

        Returns:
            Response: FastAPI 响应对象
        """
        method = method or request.method
        body = await request.body()
        content_type = request.headers.get("Content-Type", "application/json")

        url = f"{self.base_url}{path}"
        headers = self._get_headers(content_type)

        logger.debug(f"Proxying {method} {path} to {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                    params=request.query_params
                )

                logger.debug(f"Proxied response: {response.status_code}")

                # 可选：记录审计日志
                # await self._audit_log(request, response)

                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers={
                        "Content-Type": response.headers.get("Content-Type", "application/json"),
                        "X-Proxy-By": "hermes-monitor-api"
                    }
                )

        except httpx.TimeoutException:
            logger.error(f"Proxy timeout for {path}")
            raise HTTPException(status_code=504, detail="Gateway timeout")
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Hermes API at {self.base_url}")
            raise HTTPException(status_code=503, detail="Hermes API Server unavailable")
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

    async def proxy_stream(
        self,
        request: Request,
        path: str,
        method: Optional[str] = None
    ) -> StreamingResponse:
        """
        代理 SSE 流式响应

        Args:
            request: FastAPI 请求对象
            path: API 路径
            method: HTTP 方法

        Returns:
            StreamingResponse: 流式响应
        """
        method = method or request.method
        body = await request.body()

        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        logger.debug(f"Proxying stream {method} {path}")

        async def generate():
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        method=method,
                        url=url,
                        headers=headers,
                        content=body,
                        params=request.query_params
                    ) as response:
                        async for chunk in response.aiter_bytes():
                            yield chunk
            except Exception as e:
                logger.error(f"Stream error: {e}")
                raise

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"X-Proxy-By": "hermes-monitor-api"}
        )

    async def get_models(self) -> dict:
        """获取模型列表（直接调用）"""
        url = f"{self.base_url}/v1/models"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise HermesProxyError(f"Failed to get models: {response.status_code}")

            return response.json()

    async def health_check(self) -> bool:
        """检查 Hermes API Server 健康状态"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers=self._get_headers()
                )
                return response.status_code == 200
        except Exception:
            return False


# 全局代理实例
_hermes_proxy: Optional[HermesProxy] = None


def get_hermes_proxy() -> HermesProxy:
    """获取 Hermes Proxy 实例"""
    global _hermes_proxy
    if _hermes_proxy is None:
        _hermes_proxy = HermesProxy()
    return _hermes_proxy
