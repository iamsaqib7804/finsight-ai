import pytest
import requests
import random
import string

BASE_URL = "http://localhost:5000/api"

@pytest.fixture(scope="session")
def api_session():
    session = requests.Session()
    yield session
    session.close()

@pytest.fixture(scope="session")  # ⭐ FIX: module -> session
def setup_users(api_session):
    def get_random_email():
        return f"test_{''.join(random.choices(string.ascii_lowercase, k=5))}@test.com"

    user_a_email = get_random_email()
    user_b_email = get_random_email()

    # 1. Register User A
    res = api_session.post(f"{BASE_URL}/auth/register", json={
        "name": "User A", "email": user_a_email, "password": "Password123"
    })
    assert res.status_code == 201, f"User A reg failed: {res.text}"
    
    # 2. Create Group
    res = api_session.post(f"{BASE_URL}/groups/", json={"name": "Automation Test Group"})
    assert res.status_code == 201, f"Group creation failed: {res.text}"
    group_id = res.json()['group']['id']

    # 3. Logout A, Register User B
    api_session.post(f"{BASE_URL}/auth/logout")
    
    res = api_session.post(f"{BASE_URL}/auth/register", json={
        "name": "User B", "email": user_b_email, "password": "Password123"
    })
    assert res.status_code == 201, f"User B reg failed: {res.text}"
    
    # 4. Login User A & Add User B
    api_session.post(f"{BASE_URL}/auth/logout")
    
    res = api_session.post(f"{BASE_URL}/auth/login", json={"email": user_a_email, "password": "Password123"})
    assert res.status_code == 200, f"User A login failed: {res.text}"

    res = api_session.post(f"{BASE_URL}/groups/{group_id}/members", json={"email": user_b_email})
    assert res.status_code == 201, f"Adding User B failed: {res.text}"

    # 5. Create Expense (₹100) - User A ne pay kiya, dono ka split
    res = api_session.get(f"{BASE_URL}/groups/{group_id}")
    assert res.status_code == 200, f"Fetching group failed: {res.text}"
    
    data = res.json()
    if 'members' in data:
        members = data['members']
    elif 'group' in data and 'members' in data['group']:
        members = data['group']['members']
    else:
        members = []
    
    assert len(members) == 2, f"Expected 2 members, got {len(members)}. Response: {data}"
    
    participant_ids = [m['user_id'] for m in members]

    res = api_session.post(f"{BASE_URL}/expenses/", json={
        "description": "Dinner",
        "amount": 100,
        "group_id": group_id,
        "split_type": "equal",
        "participants": participant_ids
    })
    assert res.status_code == 201, f"Expense creation failed: {res.text}"

    return {
        "user_a_email": user_a_email,
        "user_b_email": user_b_email,
        "group_id": group_id,
        "user_a_id": participant_ids[0],
        "user_b_id": participant_ids[1]
    }