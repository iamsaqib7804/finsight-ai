import pytest
from tests.conftest import BASE_URL

def test_ml_classification(setup_users, api_session):
    """Test if ML model correctly classifies 'Lunch' as Food"""
    # Login as User A before testing
    api_session.post(f"{BASE_URL}/auth/login", json={
        "email": setup_users['user_a_email'], "password": "Password123"
    })
    
    res = api_session.post(f"{BASE_URL}/expenses/classify", json={"description": "Lunch"})
    assert res.status_code == 200
    data = res.json()
    assert data['category'] == 'Food', f"Expected Food, got {data['category']}"
    assert data['confidence'] > 0.5

def test_settlements_flow(setup_users, api_session):
    """Test the full Pay -> Mark Received flow"""
    group_id = setup_users['group_id']
    user_a_id = setup_users['user_a_id']
    
    # 1. Check pending (User A ko receive karna hai)
    res = api_session.get(f"{BASE_URL}/settlements/pending")
    assert res.status_code == 200
    pending = res.json()
    
    # Find the exact settlement amount
    assert len(pending['to_receive']) >= 1, "User A should have pending receipts"
    amount_to_pay = pending['to_receive'][0]['amount']

    # 2. Login as User B to Pay
    api_session.post(f"{BASE_URL}/auth/logout")
    api_session.post(f"{BASE_URL}/auth/login", json={"email": setup_users['user_b_email'], "password": "Password123"})
    
    # ⭐ Ab clearly User A ka ID bhej rahe hain
    res = api_session.post(f"{BASE_URL}/settlements/", json={
        "receiver_id": user_a_id, 
        "amount": amount_to_pay
    })
    
    # Debugging (Agar fir bhi fail ho toh)
    if res.status_code != 201:
        print(f"FAILED PAYLOAD: receiver_id={user_a_id}, amount={amount_to_pay}")
        print(f"RESPONSE: {res.text}")
        
    assert res.status_code == 201, f"Failed to create settlement: {res.text}"
    settlement_id = res.json()['id']

    # Check if "You need to pay" is empty for User B
    res = api_session.get(f"{BASE_URL}/settlements/pending")
    assert len(res.json()['to_pay']) == 0, "User B should not owe money after paying"

    # 3. Login as User A to "Mark as received"
    api_session.post(f"{BASE_URL}/auth/logout")
    api_session.post(f"{BASE_URL}/auth/login", json={"email": setup_users['user_a_email'], "password": "Password123"})
    
    # Confirm Receipt
    res = api_session.post(f"{BASE_URL}/settlements/{settlement_id}/complete")
    assert res.status_code == 200, f"Failed to complete: {res.text}"

    # Final check: Both balances should be 0
    res = api_session.get(f"{BASE_URL}/settlements/pending")
    final_pending = res.json()
    assert len(final_pending['to_pay']) == 0
    assert len(final_pending['to_receive']) == 0, "User A should not have pending receipts after confirmation"