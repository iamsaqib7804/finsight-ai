import pytest
import requests
import io
from tests.conftest import BASE_URL

def test_unauthorized_access():
    """Test that APIs block unauthenticated users"""
    new_session = requests.Session()
    res = new_session.get(f"{BASE_URL}/dashboard/")
    assert res.status_code == 401, "API should block unauthenticated users"

def test_rate_limiting():
    """Test that spam login attempts get blocked"""
    new_session = requests.Session()
    for i in range(6):
        res = new_session.post(f"{BASE_URL}/auth/login", json={
            "email": "spam@test.com", "password": "wrongpassword"
        })
    assert res.status_code == 429, "Rate limit did not trigger"

def test_file_upload_size_limit(setup_users, api_session):
    """Test that uploading a file > 5MB is rejected"""
    api_session.post(f"{BASE_URL}/auth/login", json={
        "email": setup_users['user_a_email'], "password": "Password123"
    })
    
    res = api_session.post(f"{BASE_URL}/expenses/", json={"description": "Test Receipt", "amount": 10})
    expense_id = res.json()['expense']['id']
    
    large_file = io.BytesIO(b"0" * (6 * 1024 * 1024)) 
    
    res = api_session.post(
        f"{BASE_URL}/expenses/{expense_id}/receipt",
        files={"receipt": ("test.jpg", large_file, "image/jpeg")}
    )
    
    assert res.status_code in [413, 400], "Server should reject files > 5MB"