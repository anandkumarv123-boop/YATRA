"""Yatra Sathi — Full Backend (Food, Home Foods, Station Hub, Yatra AI, Complaints, SOS, KYC)"""
from fastapi import FastAPI, APIRouter, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging, uuid, json, re, random
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

STATIC_DIR = ROOT_DIR / "static"

app = FastAPI(title="Yatra Sathi API")
api_router = APIRouter(prefix="/api")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")

# ─── AI Helper ────────────────
async def call_claude(prompt: str, max_tokens: int = 200, system: str = "You are Yatra AI — a calm, helpful, India-focused railway travel assistant. Be concise."):
    try:
        import anthropic
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key: return None
        client = anthropic.AsyncAnthropic(api_key=key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else None
        return text.strip() if text else None
    except Exception as e:
        logging.error(f"Claude error: {e}")
        return None

# ═══════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════
class KYCCreate(BaseModel):
    full_name: str; phone: str; aadhaar_last4: str; email: Optional[str] = None

class ComplaintCreate(BaseModel):
    category: str; description: str
    train_no: Optional[str] = None; coach: Optional[str] = None; station: Optional[str] = None
    location: Optional[str] = None; reporter_name: Optional[str] = None
    reporter_phone: Optional[str] = None; photo_b64: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str

class SOSEvent(BaseModel):
    lat: Optional[float] = None; lng: Optional[float] = None; note: Optional[str] = ""
    user_name: Optional[str] = None; user_phone: Optional[str] = None

class FoodOrderCreate(BaseModel):
    vendor_id: str
    items: List[Dict[str, Any]]  # [{item_id, name, price, qty}]
    pnr: Optional[str] = None
    train_no: Optional[str] = None
    coach: Optional[str] = None
    seat: Optional[str] = None
    delivery_station: str
    customer_name: Optional[str] = "Guest"
    customer_phone: Optional[str] = None
    special_instructions: Optional[str] = ""

class HomeCookCreate(BaseModel):
    name: str
    phone: str
    kitchen_name: str
    city: str
    station_hub: str  # nearest station code
    delivery_radius_km: int = 5
    cuisine: List[str]
    daily_capacity: int = 20
    timings: str = "07:00 - 22:00"
    specialties: Optional[str] = ""

class HomeCookMenuItem(BaseModel):
    cook_id: str
    name: str
    price: float
    description: str
    veg: bool = True
    photo_b64: Optional[str] = None
    diet_tags: List[str] = []  # baby, senior, diabetic, jain, low-oil
    available_qty: int = 10

class ChatMsg(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None

class AdminAuth(BaseModel):
    pin: str

class TipReq(BaseModel):
    prompt: str; max_tokens: int = 100

# ═══════════════════════════════════════════════════════════
# STATIC DATA — Food Vendors, Stations, Cooks
# ═══════════════════════════════════════════════════════════
FOOD_VENDORS = [
    # IRCTC partners
    {"id":"v_irctc_01","name":"IRCTC eCatering","logo":"🍱","type":"IRCTC","station":"NDLS","city":"Delhi","rating":4.3,"hygiene":"A+","prep_min":18,"delivery_success":94,"veg_pct":70,"tags":["Hygienic","Verified","Govt Partner"],"badge":"IRCTC"},
    {"id":"v_irctc_02","name":"RailRestro","logo":"🍛","type":"IRCTC","station":"BPL","city":"Bhopal","rating":4.5,"hygiene":"A+","prep_min":15,"delivery_success":96,"veg_pct":60,"tags":["Hygienic","Verified"],"badge":"IRCTC"},
    {"id":"v_irctc_03","name":"Comesum Café","logo":"☕","type":"IRCTC","station":"CSTM","city":"Mumbai","rating":4.4,"hygiene":"A","prep_min":12,"delivery_success":92,"veg_pct":50,"tags":["Quick","Hot"],"badge":"IRCTC"},
    # Zomato train
    {"id":"v_zom_01","name":"Zomato — Behrouz Biryani","logo":"🍚","type":"Zomato","station":"NDLS","city":"Delhi","rating":4.6,"hygiene":"A+","prep_min":22,"delivery_success":89,"veg_pct":30,"tags":["Premium","Royal"],"badge":"Zomato"},
    {"id":"v_zom_02","name":"Zomato — Faasos Wraps","logo":"🌯","type":"Zomato","station":"BCT","city":"Mumbai","rating":4.2,"hygiene":"A","prep_min":14,"delivery_success":91,"veg_pct":55,"tags":["Wraps","Quick"],"badge":"Zomato"},
    {"id":"v_zom_03","name":"Zomato — Sweet Truth","logo":"🍰","type":"Zomato","station":"HWH","city":"Kolkata","rating":4.7,"hygiene":"A+","prep_min":10,"delivery_success":95,"veg_pct":100,"tags":["Dessert","Celebrate"],"badge":"Zomato"},
    # Station vendors
    {"id":"v_stn_01","name":"Sai Annapurna","logo":"🥘","type":"Station","station":"BPL","city":"Bhopal","rating":4.2,"hygiene":"A","prep_min":8,"delivery_success":88,"veg_pct":100,"tags":["Pure Veg","Local"],"badge":"Station"},
    {"id":"v_stn_02","name":"Trivandrum Kerala Café","logo":"🥥","type":"Station","station":"TVC","city":"Trivandrum","rating":4.6,"hygiene":"A+","prep_min":12,"delivery_success":93,"veg_pct":70,"tags":["Regional","Kerala"],"badge":"Station"},
    {"id":"v_stn_03","name":"Howrah Bengali Bhog","logo":"🐟","type":"Station","station":"HWH","city":"Kolkata","rating":4.5,"hygiene":"A","prep_min":15,"delivery_success":90,"veg_pct":40,"tags":["Bengali","Authentic"],"badge":"Station"},
    # Local partners
    {"id":"v_loc_01","name":"Ammachi's Tiffin Box","logo":"🏠","type":"Local","station":"ERS","city":"Kochi","rating":4.8,"hygiene":"A+","prep_min":20,"delivery_success":97,"veg_pct":80,"tags":["Homemade","Healthy"],"badge":"Home"},
    {"id":"v_loc_02","name":"Patel Family Kitchen","logo":"🏠","type":"Local","station":"ADI","city":"Ahmedabad","rating":4.7,"hygiene":"A+","prep_min":18,"delivery_success":95,"veg_pct":100,"tags":["Gujarati","Pure Veg"],"badge":"Home"},
    {"id":"v_loc_03","name":"Tamil Amma Mess","logo":"🏠","type":"Local","station":"MAS","city":"Chennai","rating":4.6,"hygiene":"A","prep_min":15,"delivery_success":92,"veg_pct":75,"tags":["South Indian","Home"],"badge":"Home"},
]

def menu_for(vendor_id: str):
    """Returns realistic menu per vendor."""
    base = [
        {"id":vendor_id+"_m1","name":"Veg Thali","price":140,"veg":True,"desc":"Dal, sabzi, 4 roti, rice, salad, pickle, sweet","diet":["family"],"rating":4.4,"prep":15},
        {"id":vendor_id+"_m2","name":"Chicken Biryani","price":220,"veg":False,"desc":"Aromatic basmati with tender chicken & raita","diet":[],"rating":4.6,"prep":18},
        {"id":vendor_id+"_m3","name":"Masala Dosa","price":110,"veg":True,"desc":"Crispy dosa with potato masala & chutney","diet":["light"],"rating":4.5,"prep":10},
        {"id":vendor_id+"_m4","name":"Paneer Butter Masala + Naan","price":190,"veg":True,"desc":"Rich tomato gravy, 2 butter naan","diet":[],"rating":4.5,"prep":15},
        {"id":vendor_id+"_m5","name":"Family Combo (4 ppl)","price":580,"veg":True,"desc":"2 thali + 2 dal-chawal + dessert + water","diet":["family","combo"],"rating":4.7,"prep":22},
        {"id":vendor_id+"_m6","name":"Diabetic-Friendly Meal","price":180,"veg":True,"desc":"Brown rice, low-oil sabzi, sprouts, jowar roti","diet":["diabetic","senior","healthy"],"rating":4.3,"prep":15},
        {"id":vendor_id+"_m7","name":"Baby Food (Mashed Khichdi)","price":80,"veg":True,"desc":"Soft moong khichdi, no spice — under 5 yrs","diet":["baby","light"],"rating":4.6,"prep":10},
        {"id":vendor_id+"_m8","name":"Senior Citizen Soft Meal","price":150,"veg":True,"desc":"Curd rice, dal soup, soft idli, banana","diet":["senior","light"],"rating":4.4,"prep":12},
        {"id":vendor_id+"_m9","name":"Healthy Sprouts Salad","price":120,"veg":True,"desc":"Mixed sprouts, cucumber, pomegranate","diet":["healthy","light","diabetic"],"rating":4.2,"prep":5},
        {"id":vendor_id+"_m10","name":"Late Night Maggi + Tea","price":80,"veg":True,"desc":"Hot maggi noodles + masala chai","diet":["late_night","quick"],"rating":4.1,"prep":7},
    ]
    return base

STATION_HUB_DB = {
    "NDLS":{"name":"New Delhi Junction","platforms":16,"bus":["Kashmere Gate ISBT (3km)","Sarai Kale Khan (8km)"],"metro":["New Delhi Yellow Line — at station"],"auto":"Pre-paid Booth Gate 2","parking":"₹50/hr · 60% full","ev":"3 stations on P1","washroom":"4.2/5","cloak":"Yes · ₹15/day","medical":"Platform 1 + Outside Gate 1","food_court":"P1 & Concourse","crowd":62,"safe_exit":"Gate 2 (Ajmeri side)"},
    "CSTM":{"name":"Mumbai CST","platforms":18,"bus":["BEST Bay outside Gate","Azad Maidan stand"],"metro":["Aqua Line (under construction)"],"auto":"Pre-paid at Gate 1","parking":"₹40/hr · 80% full","ev":"None","washroom":"3.9/5","cloak":"Yes · ₹15/day","medical":"P1 + Outside","food_court":"Concourse","crowd":78,"safe_exit":"North Gate (less crowd)"},
    "HWH":{"name":"Howrah Junction","platforms":23,"bus":["Howrah Bus Stand (200m)"],"metro":["Howrah Metro (East-West) — operational"],"auto":"Pre-paid Bay 4","parking":"₹30/hr · 70% full","ev":"2 chargers Old Complex","washroom":"3.5/5","cloak":"Yes · ₹15/day","medical":"P1","food_court":"New Complex","crowd":85,"safe_exit":"New Complex (south) exit"},
    "MAS":{"name":"Chennai Central","platforms":17,"bus":["CMBT (12km)","Broadway (1km)"],"metro":["Chennai Central Blue Line"],"auto":"Pre-paid Gate 2","parking":"₹40/hr · 55% full","ev":"4 chargers","washroom":"4.0/5","cloak":"Yes · ₹15/day","medical":"P1 + outside","food_court":"Suburban side","crowd":58,"safe_exit":"Suburban exit"},
    "TVC":{"name":"Trivandrum Central","platforms":5,"bus":["Thampanoor (50m)"],"metro":["No metro yet"],"auto":"Outside Gate","parking":"₹25/hr · 40% full","ev":"None","washroom":"4.1/5","cloak":"Yes · ₹15/day","medical":"P1","food_court":"P1","crowd":45,"safe_exit":"East entrance"},
    "BPL":{"name":"Bhopal Junction","platforms":6,"bus":["Habibganj (5km)","Nadra (2km)"],"metro":["Bhopal Metro under construction"],"auto":"Pre-paid Gate 1","parking":"₹25/hr · 50% full","ev":"None","washroom":"4.0/5","cloak":"Yes · ₹15/day","medical":"P1","food_court":"P1 & P4","crowd":55,"safe_exit":"East exit"},
    "BCT":{"name":"Mumbai Central","platforms":7,"bus":["BEST outside"],"metro":["Mumbai Central Red Line"],"auto":"Pre-paid","parking":"₹40/hr · 70% full","ev":"2 chargers","washroom":"4.0/5","cloak":"Yes · ₹15/day","medical":"P1","food_court":"Concourse","crowd":65,"safe_exit":"Suburban exit"},
    "ERS":{"name":"Ernakulam Junction","platforms":6,"bus":["KSRTC (1km)"],"metro":["Kochi Metro — Ernakulam South 800m"],"auto":"Pre-paid","parking":"₹25/hr · 45% full","ev":"1 charger","washroom":"4.2/5","cloak":"Yes · ₹15/day","medical":"P1","food_court":"P1","crowd":52,"safe_exit":"South exit"},
    "ADI":{"name":"Ahmedabad Junction","platforms":12,"bus":["Geeta Mandir (2km)"],"metro":["Ahmedabad Metro Kalupur"],"auto":"Pre-paid","parking":"₹30/hr · 60% full","ev":"3 chargers","washroom":"4.1/5","cloak":"Yes · ₹15/day","medical":"P1","food_court":"P1 & P5","crowd":58,"safe_exit":"East exit"},
}

# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════
@api_router.get("/")
async def root():
    return {"message": "Yatra Sathi API", "version": "2.0"}

@api_router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

# ── KYC ───
@api_router.post("/kyc")
async def submit_kyc(payload: KYCCreate):
    if not re.fullmatch(r"\d{10}", payload.phone): raise HTTPException(400, "Invalid phone")
    if not re.fullmatch(r"\d{4}", payload.aadhaar_last4): raise HTTPException(400, "Aadhaar last 4 must be 4 digits")
    if len(payload.full_name.strip()) < 2: raise HTTPException(400, "Name too short")
    rec = {"id":f"KYC-{uuid.uuid4().hex[:8].upper()}", "full_name":payload.full_name.strip(),
           "phone":payload.phone, "aadhaar_last4":payload.aadhaar_last4, "email":payload.email,
           "verified":True, "timestamp":datetime.now(timezone.utc).isoformat()}
    await db.kyc.insert_one(rec.copy())
    rec.pop("_id", None)
    return rec

# ── Complaints ───
CATEGORY_META = {
    "cleanliness":{"severity":"medium","auth":"Railway Cleaning Supervisor + Coach Attendant","code":"CLN","sms":["+91-9717641527","+91-139"]},
    "alcohol":{"severity":"high","auth":"RPF / TTE","code":"ALC","sms":["+91-182","+91-139"]},
    "smoking":{"severity":"high","auth":"RPF (Sec 167 fine ₹100-₹500)","code":"SMK","sms":["+91-182","+91-1512"]},
    "food":{"severity":"medium","auth":"IRCTC Food Quality + Pantry Manager","code":"FUD","sms":["+91-1800-111-321","+91-139"]},
    "beggars":{"severity":"high","auth":"RPF / GRP","code":"BEG","sms":["+91-182","+91-1512"]},
    "other":{"severity":"medium","auth":"Railway Helpdesk 139","code":"OTH","sms":["+91-139"]},
}

@api_router.post("/complaints")
async def create_complaint(payload: ComplaintCreate):
    cat = payload.category.lower(); meta = CATEGORY_META.get(cat, CATEGORY_META["other"])
    cid = f"YS-{meta['code']}-{uuid.uuid4().hex[:6].upper()}"
    prompt = (f"A traveller filed this railway complaint.\nCategory: {cat}\n"
              f"Train: {payload.train_no or 'N/A'} | Coach: {payload.coach or 'N/A'} | Station: {payload.station or 'N/A'}\n"
              f"Description: {payload.description}\n\nReply ONLY in JSON: "
              f'{{"severity":"low|medium|high|critical","summary":"<20 words","action":"<25 words"}}')
    ai = await call_claude(prompt, 180)
    severity = meta["severity"]; summary = payload.description[:120]
    action = f"Forwarded to {meta['auth']}."
    if ai:
        try:
            start = ai.find('{'); end = ai.rfind('}')
            if start>=0 and end>start:
                p = json.loads(ai[start:end+1])
                severity = p.get("severity",severity).lower()
                summary = p.get("summary",summary); action = p.get("action",action)
        except: pass
    rec = {"id":cid,"category":cat,"description":payload.description,
           "train_no":payload.train_no,"coach":payload.coach,"station":payload.station,
           "location":payload.location,"reporter_name":payload.reporter_name or "Anonymous",
           "reporter_phone":payload.reporter_phone,"has_photo":bool(payload.photo_b64),
           "severity":severity,"ai_summary":summary,"action_taken":action,
           "assigned_to":meta["auth"],"sms_sent_to":meta["sms"],"status":"acknowledged",
           "timestamp":datetime.now(timezone.utc).isoformat()}
    sms = {"complaint_id":cid,"recipients":meta["sms"],
           "message":f"YATRA ALERT [{severity.upper()}]: {cat.upper()} reported. Train {payload.train_no or 'NA'}, Coach {payload.coach or 'NA'}. Action: {action[:80]}",
           "timestamp":rec["timestamp"],"status":"dispatched"}
    await db.sms_log.insert_one(sms)
    doc = rec.copy()
    if payload.photo_b64: doc["photo_b64"] = payload.photo_b64[:2_000_000]
    await db.complaints.insert_one(doc)
    return rec

@api_router.get("/complaints")
async def list_complaints(category: Optional[str]=None, limit: int=50):
    q = {} if not category or category=="all" else {"category":category.lower()}
    docs = await db.complaints.find(q,{"_id":0,"photo_b64":0}).sort("timestamp",-1).to_list(limit)
    return docs

@api_router.get("/complaints/stats")
async def complaint_stats():
    by_c = {r["_id"]:r["count"] for r in await db.complaints.aggregate([{"$group":{"_id":"$category","count":{"$sum":1}}}]).to_list(100)}
    by_s = {r["_id"]:r["count"] for r in await db.complaints.aggregate([{"$group":{"_id":"$severity","count":{"$sum":1}}}]).to_list(100)}
    by_st = {r["_id"]:r["count"] for r in await db.complaints.aggregate([{"$group":{"_id":"$status","count":{"$sum":1}}}]).to_list(100)}
    return {"total":await db.complaints.count_documents({}),"by_category":by_c,"by_severity":by_s,"by_status":by_st}

@api_router.get("/complaints/{cid}/photo")
async def get_complaint_photo(cid: str):
    doc = await db.complaints.find_one({"id":cid},{"_id":0,"photo_b64":1})
    if not doc or not doc.get("photo_b64"): raise HTTPException(404,"No photo")
    return {"photo_b64":doc["photo_b64"]}

@api_router.post("/complaints/{cid}/status")
async def update_status(cid: str, body: StatusUpdate, x_admin_pin: Optional[str]=Header(None)):
    if x_admin_pin != ADMIN_PIN: raise HTTPException(403,"Invalid admin PIN")
    res = await db.complaints.update_one({"id":cid},{"$set":{"status":body.status}})
    if res.matched_count==0: raise HTTPException(404,"Not found")
    return {"ok":True,"id":cid,"status":body.status}

# ── Admin ───
@api_router.post("/admin/auth")
async def admin_auth(body: AdminAuth):
    if body.pin != ADMIN_PIN: raise HTTPException(403,"Invalid PIN")
    return {"ok":True}

@api_router.get("/admin/sms-log")
async def sms_log(x_admin_pin: Optional[str]=Header(None), limit: int=50):
    if x_admin_pin != ADMIN_PIN: raise HTTPException(403,"Invalid admin PIN")
    return await db.sms_log.find({},{"_id":0}).sort("timestamp",-1).to_list(limit)

# ── AI Tip & Chat (Yatra AI) ───
@api_router.post("/ai/tip")
async def ai_tip(req: TipReq):
    txt = await call_claude(req.prompt, req.max_tokens)
    return {"text": txt or "Stay alert. Share live location. Trust your instincts. Helpline: 139."}

@api_router.post("/ai/chat")
async def yatra_chat(msg: ChatMsg):
    context_str = ""
    if msg.context:
        context_str = f"\nUser context: {json.dumps(msg.context)[:400]}"
    full = (f"User: {msg.message}{context_str}\n\nReply in 2-3 short sentences. "
            f"Be practical and India-railway focused. If asked about PNR, food, delays, platforms, safety — give clear actions.")
    txt = await call_claude(full, 220,
        system="You are Yatra AI — calm, fast, helpful Indian-railway travel assistant for ALL passengers. Friendly, no fluff. Use simple language.")
    if not txt:
        txt = "I'm here to help! Ask me about PNR status, delays, food, platforms, hotels, or safety — anything about your train journey."
    return {"reply": txt, "timestamp": datetime.now(timezone.utc).isoformat()}

# ── SOS ───
@api_router.post("/sos")
async def log_sos(event: SOSEvent):
    rec = {"id":str(uuid.uuid4()),"lat":event.lat,"lng":event.lng,"note":event.note,
           "user_name":event.user_name,"user_phone":event.user_phone,
           "timestamp":datetime.now(timezone.utc).isoformat()}
    await db.sos_events.insert_one(rec)
    await db.sms_log.insert_one({"complaint_id":rec["id"],"type":"SOS",
        "recipients":["+91-182 (RPF)","+91-1512 (Security)","+91-100 (Police)"],
        "message":f"🚨 SOS: {event.user_name or 'Anonymous'} ({event.user_phone or 'NA'}) needs help. GPS: {event.lat},{event.lng}",
        "timestamp":rec["timestamp"],"status":"dispatched"})
    return {"ok":True,"id":rec["id"],"sms_to":["+91-182","+91-1512","+91-100"]}

# ═══════════════════════════════════════════════════════════
# FOOD ORDERING
# ═══════════════════════════════════════════════════════════
@api_router.get("/food/vendors")
async def food_vendors(station: Optional[str]=None, category: Optional[str]=None, veg: Optional[bool]=None):
    data = list(FOOD_VENDORS)
    if station:
        st = station.upper()
        data = [v for v in data if v["station"]==st or st in v.get("city","").upper()]
    if veg is not None:
        data = [v for v in data if (v["veg_pct"]>=70) == veg]
    if category:
        c = category.lower()
        if c=="late_night": data = [v for v in data if v["prep_min"]<=15]
        elif c=="fast": data = [v for v in data if v["prep_min"]<=12]
        elif c=="trending": data = sorted(data, key=lambda x:-x["rating"])[:6]
        elif c=="hygienic": data = [v for v in data if v["hygiene"]=="A+"]
    return data

@api_router.get("/food/menu/{vendor_id}")
async def food_menu(vendor_id: str):
    return {"vendor_id":vendor_id,"items":menu_for(vendor_id)}

@api_router.get("/food/recommendations")
async def food_recs(station: Optional[str]=None, diet: Optional[str]=None, travel_hours: Optional[int]=None):
    """AI-aware recommendations (mocked logic + Claude tip)."""
    vendors = list(FOOD_VENDORS)
    if station: vendors = [v for v in vendors if v["station"]==station.upper()] or vendors
    # Build sections
    next_stn = sorted(vendors, key=lambda x: x["prep_min"])[:4]
    trending = sorted(vendors, key=lambda x: -x["rating"])[:4]
    healthy = [v for v in vendors if "Healthy" in v["tags"] or "Home" in v["tags"] or v["hygiene"]=="A+"][:4]
    regional = [v for v in vendors if v["type"]=="Local" or "Regional" in v["tags"]][:4]
    late = sorted(vendors, key=lambda x: x["prep_min"])[:4]
    fast = [v for v in vendors if v["prep_min"]<=12][:4]
    # AI tip
    tip = await call_claude(
        f"In 25 words, suggest one smart food choice for a train passenger at {station or 'an Indian station'}, diet preference {diet or 'any'}, travel duration {travel_hours or 'unknown'} hours.",
        80, system="You are Yatra AI food advisor. Be practical.")
    return {"sections":{
        "next_station":{"title":"🚉 Order at Next Station","data":next_stn},
        "trending":{"title":"🔥 Trending Near Your Train","data":trending},
        "healthy":{"title":"🥗 Healthy Travel Meals","data":healthy},
        "regional":{"title":"🌶️ Regional Special Foods","data":regional},
        "late_night":{"title":"🌙 Late Night Available","data":late},
        "fast":{"title":"⚡ Fast Delivery Before Departure","data":fast},
    },"ai_tip": tip or "Choose hygiene-rated kitchens for long journeys. Drink only sealed water. Avoid heavy meals for night trains."}

@api_router.post("/food/order")
async def food_order(payload: FoodOrderCreate):
    if not payload.items: raise HTTPException(400, "Cart is empty")
    vendor = next((v for v in FOOD_VENDORS if v["id"]==payload.vendor_id), None)
    if not vendor: raise HTTPException(404,"Vendor not found")
    total = sum(i.get("price",0)*i.get("qty",1) for i in payload.items)
    eta_min = vendor["prep_min"] + random.randint(2,8)  # prep + buffer
    oid = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    rec = {"id":oid,"vendor_id":payload.vendor_id,"vendor_name":vendor["name"],
           "items":payload.items,"total":total,"pnr":payload.pnr,
           "train_no":payload.train_no,"coach":payload.coach,"seat":payload.seat,
           "delivery_station":payload.delivery_station,
           "customer_name":payload.customer_name,"customer_phone":payload.customer_phone,
           "instructions":payload.special_instructions,
           "status":"confirmed","eta_min":eta_min,
           "status_history":[{"status":"confirmed","time":datetime.now(timezone.utc).isoformat()}],
           "timestamp":datetime.now(timezone.utc).isoformat()}
    await db.food_orders.insert_one(rec.copy())
    rec.pop("_id", None)
    return rec

@api_router.get("/food/order/{oid}")
async def get_food_order(oid: str):
    doc = await db.food_orders.find_one({"id":oid},{"_id":0})
    if not doc: raise HTTPException(404,"Order not found")
    # Simulate live tracking by adding elapsed time
    started = datetime.fromisoformat(doc["timestamp"])
    elapsed = (datetime.now(timezone.utc)-started).total_seconds()/60
    eta = doc.get("eta_min",20)
    progress = min(99, int(elapsed/eta*100))
    if elapsed < eta*0.2: stage = "preparing"
    elif elapsed < eta*0.6: stage = "cooking"
    elif elapsed < eta*0.9: stage = "packed"
    elif elapsed < eta*1.1: stage = "out_for_delivery"
    else: stage = "delivered"
    doc["live_stage"] = stage
    doc["live_progress"] = progress
    doc["live_eta_min"] = max(0, int(eta - elapsed))
    return doc

# ═══════════════════════════════════════════════════════════
# RAIL HOME FOODS
# ═══════════════════════════════════════════════════════════
@api_router.post("/home-foods/cook")
async def register_cook(payload: HomeCookCreate):
    if not re.fullmatch(r"\d{10}", payload.phone): raise HTTPException(400,"Invalid phone")
    cid = f"CK-{uuid.uuid4().hex[:8].upper()}"
    rec = {"id":cid,"name":payload.name,"phone":payload.phone,"kitchen_name":payload.kitchen_name,
           "city":payload.city,"station_hub":payload.station_hub.upper(),
           "delivery_radius_km":payload.delivery_radius_km,"cuisine":payload.cuisine,
           "daily_capacity":payload.daily_capacity,"timings":payload.timings,
           "specialties":payload.specialties,"verified":False,"rating":0.0,"orders_total":0,
           "earnings_total":0,"hygiene":"PENDING","timestamp":datetime.now(timezone.utc).isoformat()}
    await db.home_cooks.insert_one(rec.copy())
    rec.pop("_id", None)
    return rec

@api_router.get("/home-foods/cooks")
async def list_cooks(station: Optional[str]=None, city: Optional[str]=None, limit: int=20):
    q = {}
    if station: q["station_hub"] = station.upper()
    if city: q["city"] = {"$regex":city,"$options":"i"}
    docs = await db.home_cooks.find(q,{"_id":0}).sort("rating",-1).to_list(limit)
    # Seed demo cooks if empty
    if not docs and not station and not city:
        demos = [
            {"id":"CK-DEMO01","name":"Lakshmi Amma","phone":"9876500001","kitchen_name":"Amma's Kerala Kitchen",
             "city":"Kollam","station_hub":"QLN","delivery_radius_km":4,"cuisine":["Kerala","South Indian"],
             "daily_capacity":40,"timings":"06:00 - 22:00","specialties":"Sadya, Puttu, Appam",
             "verified":True,"rating":4.8,"orders_total":1240,"earnings_total":186000,"hygiene":"A+",
             "timestamp":datetime.now(timezone.utc).isoformat()},
            {"id":"CK-DEMO02","name":"Rekha Sharma","phone":"9876500002","kitchen_name":"Rekha's Rasoi",
             "city":"Lucknow","station_hub":"LKO","delivery_radius_km":6,"cuisine":["North Indian","Awadhi"],
             "daily_capacity":50,"timings":"07:00 - 23:00","specialties":"Biryani, Kebab, Daal",
             "verified":True,"rating":4.7,"orders_total":2100,"earnings_total":315000,"hygiene":"A+",
             "timestamp":datetime.now(timezone.utc).isoformat()},
            {"id":"CK-DEMO03","name":"Sunita Devi","phone":"9876500003","kitchen_name":"Sunita Tiffin Service",
             "city":"Patna","station_hub":"PNBE","delivery_radius_km":5,"cuisine":["Bihari","Pure Veg"],
             "daily_capacity":35,"timings":"06:30 - 21:00","specialties":"Litti Chokha, Sattu",
             "verified":True,"rating":4.6,"orders_total":890,"earnings_total":124000,"hygiene":"A",
             "timestamp":datetime.now(timezone.utc).isoformat()},
            {"id":"CK-DEMO04","name":"Prema & Daughters","phone":"9876500004","kitchen_name":"Tamil Family Kitchen",
             "city":"Madurai","station_hub":"MDU","delivery_radius_km":7,"cuisine":["Tamil","Chettinad"],
             "daily_capacity":60,"timings":"05:00 - 22:30","specialties":"Idiyappam, Chettinad Chicken",
             "verified":True,"rating":4.9,"orders_total":3200,"earnings_total":485000,"hygiene":"A+",
             "timestamp":datetime.now(timezone.utc).isoformat()},
        ]
        await db.home_cooks.insert_many([d.copy() for d in demos])
        return demos
    return docs

@api_router.post("/home-foods/menu")
async def add_cook_menu(item: HomeCookMenuItem):
    rec = {"id":f"HM-{uuid.uuid4().hex[:6].upper()}","cook_id":item.cook_id,
           "name":item.name,"price":item.price,"description":item.description,
           "veg":item.veg,"diet_tags":item.diet_tags,"available_qty":item.available_qty,
           "rating":0.0,"orders":0,"timestamp":datetime.now(timezone.utc).isoformat()}
    if item.photo_b64: rec["photo_b64"] = item.photo_b64[:1_500_000]
    await db.home_food_menu.insert_one(rec.copy())
    rec.pop("_id", None); rec.pop("photo_b64", None)
    return rec

@api_router.get("/home-foods/menu/{cook_id}")
async def cook_menu(cook_id: str):
    docs = await db.home_food_menu.find({"cook_id":cook_id},{"_id":0,"photo_b64":0}).to_list(50)
    if not docs:
        # Seed demo menu
        demos = [
            {"name":"Sadya Mini Box","price":160,"description":"Rice + 6 curries + payasam (banana leaf)","veg":True,"diet_tags":["regional","family"]},
            {"name":"Puttu Kadala","price":110,"description":"Steamed rice cake with black gram curry","veg":True,"diet_tags":["regional","healthy"]},
            {"name":"Homemade Curd Rice","price":90,"description":"Soft curd rice with pickle","veg":True,"diet_tags":["senior","light","baby"]},
            {"name":"Chicken Curry + Appam","price":210,"description":"3 appams with Kerala chicken curry","veg":False,"diet_tags":["regional"]},
        ]
        for d in demos:
            d["id"] = f"HM-{uuid.uuid4().hex[:6].upper()}"; d["cook_id"]=cook_id
            d["rating"]=4.5; d["orders"]=random.randint(30,200); d["available_qty"]=15
            d["timestamp"]=datetime.now(timezone.utc).isoformat()
        await db.home_food_menu.insert_many([d.copy() for d in demos])
        return demos
    return docs

@api_router.get("/home-foods/insights/{cook_id}")
async def cook_insights(cook_id: str):
    """AI-powered sales insights for home cook."""
    cook = await db.home_cooks.find_one({"id":cook_id},{"_id":0})
    if not cook: raise HTTPException(404,"Cook not found")
    # Mock + AI insights
    peak_hours = ["07:30-09:00 (breakfast rush)","12:30-14:00 (lunch peak)","19:00-21:30 (dinner rush)"]
    trending_items = ["Sadya Mini Box","Puttu Kadala","Chicken Curry"]
    predicted_orders_today = random.randint(15, cook.get("daily_capacity",40))
    suggested_prep = {item: random.randint(8,20) for item in trending_items}
    suggested_price = {"Sadya Mini Box":"₹160-170 (peak)","Puttu Kadala":"₹110 (steady)"}
    ai = await call_claude(
        f"As a railway home-food business coach, give 2 practical tips in 30 words for cook {cook.get('kitchen_name','')} at {cook.get('station_hub','')} station serving {', '.join(cook.get('cuisine',[]))} food.",
        100, system="You are a friendly micro-business advisor for Indian home cooks.")
    return {
        "cook_id":cook_id, "kitchen":cook.get("kitchen_name"),
        "predicted_orders_today":predicted_orders_today,
        "peak_hours":peak_hours,
        "trending_items":trending_items,
        "suggested_prep_qty":suggested_prep,
        "suggested_pricing":suggested_price,
        "waste_reduction_tip":"Cook in 2 batches: 60% by 11 AM (lunch rush), 40% by 5 PM (dinner) — saves 18% waste",
        "earnings_this_week": cook.get("earnings_total",0) * 0.18,  # mock 18% of total
        "ai_advice": ai or "Focus on hygiene certification — A+ rated cooks earn 40% more. Offer combo deals during peak train hours."
    }

# ═══════════════════════════════════════════════════════════
# STATION HUB
# ═══════════════════════════════════════════════════════════
@api_router.get("/station/{code}/hub")
async def station_hub(code: str):
    code = code.upper()
    hub = STATION_HUB_DB.get(code)
    if not hub:
        return {"code":code,"name":f"{code} Station","platforms":4,"bus":["Local bus stand"],
                "metro":["Not available"],"auto":"Outside main gate","parking":"₹25/hr",
                "ev":"None","washroom":"3.8/5","cloak":"Yes","medical":"P1","food_court":"P1",
                "crowd":random.randint(35,75),"safe_exit":"Main exit",
                "available":False, "ai_route":"Use main exit, follow signs."}
    # AI smart routing
    ai = await call_claude(
        f"Station: {hub['name']}, crowd level {hub['crowd']}%. Suggest in 25 words the SAFEST and FASTEST exit route at this time of day for a solo passenger with luggage.",
        80)
    return {"code":code, **hub, "available":True,
            "ai_route": ai or f"Take {hub['safe_exit']}. Less crowd, well-lit, easy auto access."}

@api_router.get("/stations/search")
async def search_stations(q: str=""):
    q = q.upper().strip()
    if not q: return list(STATION_HUB_DB.keys())[:10]
    matches = [{"code":k,"name":v["name"]} for k,v in STATION_HUB_DB.items()
               if q in k or q.lower() in v["name"].lower()]
    return matches[:10]

# ═══════════════════════════════════════════════════════════
# PNR & TRAIN TRACKING (mocked)
# ═══════════════════════════════════════════════════════════
@api_router.get("/pnr/{pnr}")
async def pnr_lookup(pnr: str):
    if not re.fullmatch(r"\d{10}", pnr): raise HTTPException(400,"PNR must be 10 digits")
    # Mocked deterministic-ish data from pnr seed
    seed = sum(int(c) for c in pnr)
    trains = [
        {"no":"12951","name":"Mumbai Rajdhani Exp","from":"BCT","to":"NDLS"},
        {"no":"12309","name":"Rajendra Nagar Rajdhani","from":"PNBE","to":"NDLS"},
        {"no":"12245","name":"Howrah Yesvantpur Duronto","from":"HWH","to":"YPR"},
        {"no":"22691","name":"Rajdhani Bengaluru","from":"NZM","to":"SBC"},
        {"no":"12137","name":"Punjab Mail","from":"CSTM","to":"FZR"},
    ]
    t = trains[seed % len(trains)]
    coach = ["S5","B1","A1","S3","B2"][seed%5]
    seat = str(seed%72 + 1)
    statuses = ["CNF","CNF","CNF","RAC","WL2"]
    return {
        "pnr":pnr,"train_no":t["no"],"train_name":t["name"],
        "from_station":t["from"],"to_station":t["to"],
        "doj": (datetime.now()+timedelta(days=seed%7)).strftime("%Y-%m-%d"),
        "passengers":[{"name":"Pax 1","age":seed%60+18,"berth":coach+"-"+seat,"status":statuses[seed%5]}],
        "boarding":t["from"],"class":"3A","chart_prepared":seed%2==0,
    }

@api_router.get("/train/{train_no}/live")
async def train_live(train_no: str):
    """Live train tracking — uses RailRadar API when available, falls back to deterministic mock."""
    rr_key = os.environ.get("RAILRADAR_KEY")
    real_data = None
    if rr_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as cli:
                resp = await cli.get(f"https://api.railradar.org/api/v1/trains/{train_no}",
                                     headers={"x-api-key": rr_key})
                if resp.status_code == 200:
                    rr = resp.json()
                    if rr.get("success") and rr.get("data"):
                        real_data = rr["data"]
        except Exception as e:
            logging.warning(f"RailRadar fetch failed: {e}")

    if real_data:
        train = real_data.get("train", {})
        route_full = real_data.get("route", [])
        # Build halts-only route for visualisation (cap at 12 stops)
        halts = [r for r in route_full if r.get("isHalt") == 1] or route_full[:12]
        if len(halts) > 12:
            # keep first, last, evenly sampled middle
            step = max(1, len(halts)//12)
            halts = [halts[0]] + halts[1:-1:step][:10] + [halts[-1]]
        route_codes = [r.get("stationCode") for r in halts]

        # Determine current position from schedule + current IST time
        # scheduledDeparture is minutes-of-day (0-1440); journey can span multiple days
        now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)  # IST
        now_mins = now.hour * 60 + now.minute
        # Find the halt whose scheduled time is closest to now (within the same day)
        seed = sum(int(c) if c.isdigit() else ord(c) for c in train_no)
        cur_idx = min(len(halts)-1, max(0, seed % len(halts)))
        # Refine using schedule if possible
        best = None
        for i, h in enumerate(halts):
            sched = h.get("scheduledDeparture") or h.get("scheduledArrival") or 0
            diff = abs((sched % 1440) - now_mins)
            if best is None or diff < best[0]:
                best = (diff, i)
        if best:
            cur_idx = best[1]

        next_idx = min(cur_idx + 1, len(halts) - 1)
        total = halts[-1].get("distanceFromSourceKm") or train.get("distanceKm") or 1000
        cur_dist = halts[cur_idx].get("distanceFromSourceKm") or 0
        progress_pct = max(3, min(98, int((cur_dist / total) * 100))) if total else (seed % 90) + 5
        speed = halts[cur_idx].get("speedOnSectionKmph") or train.get("avgSpeedKmph") or (70 + seed % 50)
        delay = max(0, (seed % 18) - 5)
        eta_next = max(2, 15 - (progress_pct % 14))

        coaches_raw = train.get("rakeDetails", "[]")
        try:
            rake = json.loads(coaches_raw) if isinstance(coaches_raw, str) else coaches_raw
        except Exception:
            rake = []
        coaches = []
        seen = set()
        for c in rake or []:
            code = c.get("code", "")
            ctype = c.get("type", "")
            if not code or code in seen or ctype in ("loco-e", "eog", "pc", "gen"):
                continue
            seen.add(code)
            # Realistic crowd by type
            base = {"a1": 30, "a2": 50, "a3": 78, "sleeper": 85}.get(ctype, 60)
            pct = max(15, min(98, base + (sum(ord(x) for x in code) % 20) - 10))
            type_label = {"a1": "AC 1T", "a2": "AC 2T", "a3": "AC 3T", "sleeper": "Sleeper"}.get(ctype, ctype.upper() or "Class")
            coaches.append({"id": code, "type": type_label, "pct": pct})
        if not coaches:
            coaches = [
                {"id":"S1","type":"Sleeper","pct":85+(seed%10)},
                {"id":"S5","type":"Sleeper","pct":40+(seed%15)},
                {"id":"B1","type":"AC 3T","pct":78+(seed%10)},
                {"id":"A1","type":"AC 2T","pct":50+(seed%10)},
            ]

        return {
            "train_no": train_no,
            "train_name": train.get("trainName", f"Train {train_no}"),
            "route": route_codes,
            "current_station": route_codes[cur_idx] if route_codes else "—",
            "next_station": route_codes[next_idx] if next_idx != cur_idx else "Approaching destination",
            "destination": train.get("destinationStationCode") or route_codes[-1] if route_codes else "—",
            "source": train.get("sourceStationCode") or route_codes[0] if route_codes else "—",
            "progress_pct": progress_pct,
            "speed_kmph": round(speed),
            "delay_min": delay,
            "eta_next_min": eta_next,
            "coaches": coaches[:8],
            "platform": (seed % 12) + 1,
            "platform_confidence": 80 + (seed % 15),
            "next_food_station": route_codes[next_idx] if route_codes else "NDLS",
            "data_source": "RailRadar Live",
            "train_type": train.get("type", ""),
            "distance_km": train.get("distanceKm"),
            "total_halts": train.get("totalHalts"),
        }

    # ── Fallback mock ──
    seed = sum(int(c) if c.isdigit() else ord(c) for c in train_no)
    routes = {
        "12951":["BCT","BRC","RTM","KOTA","SWM","JP","NDLS"],
        "12309":["PNBE","DDU","ALD","CNB","ETW","TDL","NDLS"],
        "12245":["HWH","KGP","TATA","ROU","BSP","NGP","BPQ","YPR"],
        "22691":["NZM","JHS","BPL","NGP","BZA","SBC"],
        "12137":["CSTM","BSL","JBP","ITJ","BPL","JHS","NDLS","UMB","LDH","JUC","FZR"],
    }
    route = routes.get(train_no, ["NDLS","CNB","ALD","MGS","PNBE","ASN","HWH"])
    progress_pct = (seed % 90)+5
    cur_idx = int(progress_pct/100 * (len(route)-1))
    next_idx = min(cur_idx+1, len(route)-1)
    delay = max(0, (seed%18)-5)
    speed = 70 + (seed%50)
    eta_next = max(2, 15-(progress_pct % 14))
    coaches = [
        {"id":"S1","type":"Sleeper","pct":85+(seed%10)},
        {"id":"S3","type":"Sleeper","pct":62+(seed%12)},
        {"id":"S5","type":"Sleeper","pct":40+(seed%15)},
        {"id":"S6","type":"Sleeper","pct":35+(seed%10)},
        {"id":"B1","type":"AC 3T","pct":78+(seed%10)},
        {"id":"A1","type":"AC 2T","pct":50+(seed%10)},
        {"id":"H1","type":"AC 1T","pct":30+(seed%10)},
    ]
    return {
        "train_no":train_no,"train_name":f"Train {train_no}","route":route,
        "current_station":route[cur_idx],
        "next_station":route[next_idx] if next_idx!=cur_idx else "Approaching destination",
        "destination":route[-1],"source":route[0],
        "progress_pct":progress_pct,"speed_kmph":speed,"delay_min":delay,
        "eta_next_min":eta_next,"coaches":coaches,
        "platform":(seed%12)+1,"platform_confidence":80+(seed%15),
        "next_food_station":route[next_idx],
        "data_source":"Mocked (RailRadar unavailable)",
    }

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS','*').split(','),
    allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/manifest.json")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    """Catch-all: serve index.html for any non-API route."""
    return FileResponse(str(STATIC_DIR / "index.html"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
