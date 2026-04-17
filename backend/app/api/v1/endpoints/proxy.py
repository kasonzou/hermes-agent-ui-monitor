"""
Hermes 内置 API 反向代理端点
"""
from fastapi import APIRouter, Depends, Request
from app.core.security import verify_api_key
from app.core.hermes_proxy import get_hermes_proxy, HermesProxyError

router = APIRouter()


@router.post("/chat/completions")
async def proxy_chat_completions(request: Request, _: str = Depends(verify_api_key)):
    """
    代理到 Hermes /v1/chat/completions
    支持流式和非流式响应
    """
    proxy = get_hermes_proxy()

    try:
        body = await request.json()

        # 检查是否流式请求
        if body.get("stream", False):
            return await proxy.proxy_stream(request, "/v1/chat/completions")
        else:
            return await proxy.proxy_request(request, "/v1/chat/completions")

    except HermesProxyError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/responses")
async def proxy_responses(request: Request, _: str = Depends(verify_api_key)):
    """
    代理到 Hermes /v1/responses
    支持流式和非流式响应
    """
    proxy = get_hermes_proxy()

    try:
        body = await request.json()

        if body.get("stream", False):
            return await proxy.proxy_stream(request, "/v1/responses")
        else:
            return await proxy.proxy_request(request, "/v1/responses")

    except HermesProxyError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def proxy_models(request: Request, _: str = Depends(verify_api_key)):
    """代理到 Hermes /v1/models"""
    proxy = get_hermes_proxy()
    return await proxy.proxy_request(request, "/v1/models")


@router.get("/responses/{response_id}")
async def proxy_get_response(response_id: str, request: Request, _: str = Depends(verify_api_key)):
    """代理到 Hermes /v1/responses/{id}"""
    proxy = get_hermes_proxy()
    return await proxy.proxy_request(request, f"/v1/responses/{response_id}")


@router.delete("/responses/{response_id}")
async def proxy_delete_response(response_id: str, request: Request, _: str = Depends(verify_api_key)):
    """代理到 Hermes DELETE /v1/responses/{id}"""
    proxy = get_hermes_proxy()
    return await proxy.proxy_request(request, f"/v1/responses/{response_id}")
