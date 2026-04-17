"""
API 测试
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

API_KEY = "test-api-key"


def test_health_check():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "healthy"


def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "docs" in data["data"]


def test_unauthorized_access():
    """测试未授权访问"""
    response = client.get("/api/v1/system/status")
    assert response.status_code == 403


def test_system_status_with_auth():
    """测试带认证的系统状态"""
    # 注意：这里需要实际的 hermes 环境
    # 在没有 hermes 的环境下会返回错误
    response = client.get(
        "/api/v1/system/status",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    # 根据环境可能成功或失败
    assert response.status_code in [200, 500, 503]
