"""Backend tests for Yatra Sathi - Women Safety AI Platform."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://safe-journey-india-1.preview.emergentagent.com").rstrip("/")
ADMIN_PIN = "1234"

# ── Fixtures ───
@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="session")
def admin_headers():
    return {"Content-Type": "application/json", "X-Admin-Pin": ADMIN_PIN}

# ── Health ───
def test_health(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

def test_root(client):
    r = client.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200

# ── KYC ───
class TestKYC:
    def test_kyc_valid(self, client):
        r = client.post(f"{BASE_URL}/api/kyc", json={
            "full_name": "TEST_Priya Sharma", "phone": "9876543210",
            "aadhaar_last4": "1234", "email": "priya@test.com"
        }, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["full_name"] == "TEST_Priya Sharma"
        assert data["phone"] == "9876543210"
        assert data["aadhaar_last4"] == "1234"
        assert data["verified"] is True
        assert data["id"].startswith("KYC-")

    def test_kyc_invalid_phone(self, client):
        r = client.post(f"{BASE_URL}/api/kyc", json={
            "full_name": "Tester", "phone": "12345", "aadhaar_last4": "1234"
        }, timeout=15)
        assert r.status_code == 400

    def test_kyc_invalid_aadhaar(self, client):
        r = client.post(f"{BASE_URL}/api/kyc", json={
            "full_name": "Tester", "phone": "9876543210", "aadhaar_last4": "12"
        }, timeout=15)
        assert r.status_code == 400

    def test_kyc_short_name(self, client):
        r = client.post(f"{BASE_URL}/api/kyc", json={
            "full_name": "A", "phone": "9876543210", "aadhaar_last4": "1234"
        }, timeout=15)
        assert r.status_code == 400

# ── Complaints ───
class TestComplaints:
    complaint_ids = {}

    def test_create_smoking_complaint(self, client):
        r = client.post(f"{BASE_URL}/api/complaints", json={
            "category": "smoking",
            "description": "TEST_3 men smoking in toilet near coach S5 seat 32",
            "train_no": "12951", "coach": "S5", "station": "Bhopal",
            "reporter_name": "TEST_Reporter"
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["category"] == "smoking"
        assert d["id"].startswith("YS-SMK-")
        assert d["status"] == "acknowledged"
        assert isinstance(d["sms_sent_to"], list) and len(d["sms_sent_to"]) > 0
        assert "RPF" in d["assigned_to"]
        assert d["severity"] in ("low", "medium", "high", "critical")
        # AI summary may or may not be present (budget fallback acceptable)
        assert len(d["ai_summary"]) > 0
        TestComplaints.complaint_ids["smoking"] = d["id"]

    def test_create_cleanliness_with_photo(self, client):
        # 1x1 pixel PNG base64
        tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        r = client.post(f"{BASE_URL}/api/complaints", json={
            "category": "cleanliness",
            "description": "TEST_Toilet dirty in coach B1",
            "train_no": "12009", "coach": "B1",
            "photo_b64": tiny_png
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_photo"] is True
        assert "IRCTC" in d["assigned_to"] or "Cleaning" in d["assigned_to"]
        TestComplaints.complaint_ids["cleanliness"] = d["id"]

    def test_list_complaints_no_photo_field(self, client):
        r = client.get(f"{BASE_URL}/api/complaints", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) > 0
        for it in items:
            assert "photo_b64" not in it, "photo_b64 must not be exposed in list"

    def test_list_complaints_category_filter(self, client):
        r = client.get(f"{BASE_URL}/api/complaints?category=smoking", timeout=15)
        assert r.status_code == 200
        for it in r.json():
            assert it["category"] == "smoking"

    def test_get_complaint_photo(self, client):
        cid = TestComplaints.complaint_ids.get("cleanliness")
        assert cid, "Prior test must create complaint with photo"
        r = client.get(f"{BASE_URL}/api/complaints/{cid}/photo", timeout=15)
        assert r.status_code == 200
        assert "photo_b64" in r.json()

    def test_get_complaint_photo_missing(self, client):
        cid = TestComplaints.complaint_ids.get("smoking")
        assert cid
        r = client.get(f"{BASE_URL}/api/complaints/{cid}/photo", timeout=15)
        assert r.status_code == 404

    def test_complaint_stats(self, client):
        r = client.get(f"{BASE_URL}/api/complaints/stats", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "total" in d and d["total"] >= 1
        assert "by_category" in d
        assert "by_severity" in d
        assert "by_status" in d
        assert "smoking" in d["by_category"]

    def test_update_status_requires_pin(self, client):
        cid = TestComplaints.complaint_ids.get("smoking")
        r = client.post(f"{BASE_URL}/api/complaints/{cid}/status",
                        json={"status": "resolved"}, timeout=15)
        assert r.status_code == 403

    def test_update_status_with_pin(self, client, admin_headers):
        cid = TestComplaints.complaint_ids.get("smoking")
        r = requests.post(f"{BASE_URL}/api/complaints/{cid}/status",
                          json={"status": "resolved"}, headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        # verify via list
        r2 = client.get(f"{BASE_URL}/api/complaints?category=smoking", timeout=15)
        item = next((x for x in r2.json() if x["id"] == cid), None)
        assert item and item["status"] == "resolved"

    def test_update_status_not_found(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/complaints/YS-NOPE-123456/status",
                          json={"status": "resolved"}, headers=admin_headers, timeout=15)
        assert r.status_code == 404

# ── Admin Auth ───
class TestAdmin:
    def test_admin_auth_correct(self, client):
        r = client.post(f"{BASE_URL}/api/admin/auth", json={"pin": ADMIN_PIN}, timeout=15)
        assert r.status_code == 200 and r.json().get("ok") is True

    def test_admin_auth_wrong(self, client):
        r = client.post(f"{BASE_URL}/api/admin/auth", json={"pin": "0000"}, timeout=15)
        assert r.status_code == 403

    def test_sms_log_requires_pin(self, client):
        r = client.get(f"{BASE_URL}/api/admin/sms-log", timeout=15)
        assert r.status_code == 403

    def test_sms_log_with_pin(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/sms-log", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)
        assert len(logs) >= 1
        assert "recipients" in logs[0]
        assert "message" in logs[0]

# ── SOS ───
def test_sos(client):
    r = client.post(f"{BASE_URL}/api/sos", json={
        "lat": 23.25, "lng": 77.41, "note": "TEST_sos", "user_name": "TEST_User",
        "user_phone": "9876543210"
    }, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    assert "id" in d
    assert any("RPF" in s for s in d.get("sms_to", []))

# ── AI Tip ───
def test_ai_tip(client):
    r = client.post(f"{BASE_URL}/api/ai/tip", json={
        "prompt": "Give one safety tip for a woman travelling alone at night by train.",
        "max_tokens": 60
    }, timeout=60)
    assert r.status_code == 200
    assert "text" in r.json()
    assert len(r.json()["text"]) > 0
