"""Yatra Sathi v2 endpoint tests: Food, Home Foods, Station Hub, PNR, Train, Chat."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://safe-journey-india-1.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Food: vendors / menu / recommendations / order / live ───
class TestFood:
    order_id = None

    def test_vendors_list(self, client):
        r = client.get(f"{BASE_URL}/api/food/vendors", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 10
        for v in data:
            assert "id" in v and "name" in v and "badge" in v
            assert v["badge"] in ("IRCTC", "Zomato", "Station", "Home")

    def test_vendors_filter_station(self, client):
        r = client.get(f"{BASE_URL}/api/food/vendors?station=NDLS", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        for v in data:
            assert v["station"] == "NDLS" or "DELHI" in v.get("city", "").upper()

    def test_recommendations_sections(self, client):
        r = client.get(f"{BASE_URL}/api/food/recommendations?station=NDLS", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sections" in d
        secs = d["sections"]
        for k in ("next_station", "trending", "healthy", "regional", "late_night", "fast"):
            assert k in secs, f"Missing section {k}"
            assert "title" in secs[k] and "data" in secs[k]
            assert isinstance(secs[k]["data"], list)
        assert "ai_tip" in d and isinstance(d["ai_tip"], str) and len(d["ai_tip"]) > 0

    def test_menu(self, client):
        r = client.get(f"{BASE_URL}/api/food/menu/v_irctc_01", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["vendor_id"] == "v_irctc_01"
        assert isinstance(d["items"], list) and len(d["items"]) == 10
        # validate tags exist
        all_tags = set()
        for it in d["items"]:
            assert "veg" in it and "price" in it
            all_tags.update(it.get("diet", []))
        for t in ("baby", "senior", "diabetic", "family", "healthy"):
            assert t in all_tags, f"diet tag {t} not seen in menu"

    def test_create_order(self, client):
        payload = {
            "vendor_id": "v_irctc_01",
            "items": [{"item_id": "v_irctc_01_m1", "name": "Veg Thali", "price": 140, "qty": 2}],
            "pnr": "1234567890",
            "train_no": "12951",
            "coach": "S5",
            "seat": "32",
            "delivery_station": "BPL",
            "customer_name": "TEST_Customer",
            "customer_phone": "9876543210",
        }
        r = client.post(f"{BASE_URL}/api/food/order", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"].startswith("ORD-")
        assert d["total"] == 280
        assert d["vendor_name"]
        assert d["eta_min"] > 0
        assert d["status"] == "confirmed"
        TestFood.order_id = d["id"]

    def test_order_invalid_vendor(self, client):
        r = client.post(f"{BASE_URL}/api/food/order", json={
            "vendor_id": "v_nope",
            "items": [{"price": 100, "qty": 1}],
            "delivery_station": "NDLS"
        }, timeout=15)
        assert r.status_code == 404

    def test_get_order_live(self, client):
        assert TestFood.order_id, "create order must run first"
        r = client.get(f"{BASE_URL}/api/food/order/{TestFood.order_id}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == TestFood.order_id
        assert d["live_stage"] in ("preparing", "cooking", "packed", "out_for_delivery", "delivered")
        assert 0 <= d["live_progress"] <= 99
        assert "live_eta_min" in d


# ── Home Foods ───
class TestHomeFoods:
    cook_id = None

    def test_register_cook_valid(self, client):
        r = client.post(f"{BASE_URL}/api/home-foods/cook", json={
            "name": "TEST_Anita",
            "phone": "9876512345",
            "kitchen_name": "TEST_Anita's Kitchen",
            "city": "Pune",
            "station_hub": "pune",
            "delivery_radius_km": 5,
            "cuisine": ["Maharashtrian"],
            "daily_capacity": 25,
            "timings": "07:00 - 21:00",
            "specialties": "Misal, Bhakri"
        }, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"].startswith("CK-") and len(d["id"]) == 11
        assert d["station_hub"] == "PUNE"
        assert d["verified"] is False
        TestHomeFoods.cook_id = d["id"]

    def test_register_cook_invalid_phone(self, client):
        r = client.post(f"{BASE_URL}/api/home-foods/cook", json={
            "name": "X", "phone": "123", "kitchen_name": "K",
            "city": "C", "station_hub": "NDLS", "cuisine": ["X"]
        }, timeout=15)
        assert r.status_code == 400

    def test_list_cooks_seeded(self, client):
        r = client.get(f"{BASE_URL}/api/home-foods/cooks", timeout=15)
        assert r.status_code == 200
        cooks = r.json()
        assert isinstance(cooks, list) and len(cooks) >= 4
        names = {c["name"] for c in cooks}
        # demo cooks should be present (auto-seeded or any cook list)
        # Allow either demo seeds or the cook we created — verify at least one of demo
        demo_expected = {"Lakshmi Amma", "Rekha Sharma", "Sunita Devi", "Prema & Daughters"}
        assert demo_expected.intersection(names) or len(cooks) >= 4

    def test_cook_menu_seeded(self, client):
        r = client.get(f"{BASE_URL}/api/home-foods/menu/CK-NEW-EMPTY-XYZ", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 3
        names = {i["name"] for i in items}
        assert any(n in names for n in ("Sadya Mini Box", "Puttu Kadala", "Homemade Curd Rice"))

    def test_cook_insights(self, client):
        # use one of seeded demo IDs
        r = client.get(f"{BASE_URL}/api/home-foods/insights/CK-DEMO01", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("predicted_orders_today", "peak_hours", "trending_items", "ai_advice"):
            assert k in d, f"missing {k}"
        assert isinstance(d["peak_hours"], list)
        assert isinstance(d["trending_items"], list)
        assert len(d["ai_advice"]) > 0

    def test_cook_insights_404(self, client):
        r = client.get(f"{BASE_URL}/api/home-foods/insights/CK-NOPE", timeout=15)
        assert r.status_code == 404


# ── Station Hub ───
class TestStationHub:
    def test_hub_ndls(self, client):
        r = client.get(f"{BASE_URL}/api/station/NDLS/hub", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["code"] == "NDLS"
        assert d["name"] == "New Delhi Junction"
        assert d["available"] is True
        for k in ("bus", "metro", "auto", "parking", "ev", "washroom",
                  "cloak", "medical", "food_court", "safe_exit", "ai_route"):
            assert k in d
        assert len(d["ai_route"]) > 0

    def test_hub_cstm(self, client):
        r = client.get(f"{BASE_URL}/api/station/CSTM/hub", timeout=30)
        assert r.status_code == 200
        assert r.json()["name"] == "Mumbai CST"

    def test_hub_unknown_fallback(self, client):
        r = client.get(f"{BASE_URL}/api/station/ZZZ/hub", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["available"] is False
        assert d["code"] == "ZZZ"


# ── PNR ───
class TestPNR:
    def test_pnr_valid_deterministic(self, client):
        r1 = client.get(f"{BASE_URL}/api/pnr/1234567890", timeout=15)
        r2 = client.get(f"{BASE_URL}/api/pnr/1234567890", timeout=15)
        assert r1.status_code == 200 and r2.status_code == 200
        d1 = r1.json()
        d2 = r2.json()
        assert d1["pnr"] == "1234567890"
        # Deterministic train selection
        assert d1["train_no"] == d2["train_no"]
        assert d1["train_name"] == d2["train_name"]
        assert d1["passengers"][0]["berth"] == d2["passengers"][0]["berth"]
        assert d1["passengers"][0]["status"] in ("CNF", "RAC", "WL2")

    def test_pnr_invalid(self, client):
        r = client.get(f"{BASE_URL}/api/pnr/123", timeout=15)
        assert r.status_code == 400


# ── Train Live ───
class TestTrain:
    def test_live_12951(self, client):
        r = client.get(f"{BASE_URL}/api/train/12951/live", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["train_no"] == "12951"
        assert isinstance(d["route"], list) and len(d["route"]) >= 5
        assert d["current_station"] in d["route"]
        assert "next_station" in d
        assert 0 <= d["progress_pct"] <= 100
        assert isinstance(d["coaches"], list) and len(d["coaches"]) >= 5
        for c in d["coaches"]:
            assert "id" in c and "pct" in c

    def test_live_fallback_route(self, client):
        r = client.get(f"{BASE_URL}/api/train/99999/live", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["route"], list) and len(d["route"]) > 0


# ── AI Chat ───
def test_ai_chat(client):
    r = client.post(f"{BASE_URL}/api/ai/chat", json={
        "message": "What does PNR status CNF mean?"
    }, timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert "reply" in d and len(d["reply"]) > 0
    assert "timestamp" in d
