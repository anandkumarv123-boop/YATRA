from fastapi import FastAPI, APIRouter, HTTPException, Header
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")

# ─── Models ────────────────────────────────────────────────
class KYCCreate(BaseModel):
    full_name: str
    phone: str
    aadhaar_last4: str
    email: Optional[str] = None

class KYC(BaseModel):
    id: str
    full_name: str
    phone: str
    aadhaar_last4: str
    email: Optional[str] = None
    verified: bool = True
    timestamp: str

class ComplaintCreate(BaseModel):
    category: str
    description: str
    train_no: Optional[str] = None
    coach: Optional[str] = None
    station: Optional[str] = None
    location: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_phone: Optional[str] = None
    photo_b64: Optional[str] = None  # base64 image (data URL or raw)

class Complaint(BaseModel):
    id: str
    category: str
    description: str
    train_no: Optional[str] = None
    coach: Optional[str] = None
    station: Optional[str] = None
    location: Optional[str] = None
    reporter_name: Optional[str] = "Anonymous"
    reporter_phone: Optional[str] = None
    has_photo: bool = False
    severity: str = "medium"
    ai_summary: str = ""
    action_taken: str = ""
    assigned_to: str = ""
    sms_sent_to: List[str] = []
    status: str = "open"
    timestamp: str

class StatusUpdate(BaseModel):
    status: str  # acknowledged | resolved | open

class SOSEvent(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    note: Optional[str] = ""
    user_name: Optional[str] = None
    user_phone: Optional[str] = None

# ─── AI Helper ────────────────
async def call_claude(prompt: str, max_tokens: int = 200, system: str = "You are a women safety assistant for Indian Railways. Be concise, practical."):
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ.get('EMERGENT_LLM_KEY')
        if not key:
            return None
        chat = LlmChat(
            api_key=key,
            session_id=f"yatra-{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("anthropic", "claude-haiku-4-5-20251001")
        resp = await chat.send_message(UserMessage(text=prompt))
        return resp.strip() if resp else None
    except Exception as e:
        logging.error(f"Claude error: {e}")
        return None

# ─── Routes ────────────────────────────────────────────────
@api_router.get("/")
async def root():
    return {"message": "Yatra Sathi API", "status": "ok"}

@api_router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

# ── KYC ───
@api_router.post("/kyc", response_model=KYC)
async def submit_kyc(payload: KYCCreate):
    if not re.fullmatch(r"\d{10}", payload.phone):
        raise HTTPException(400, "Invalid phone (must be 10 digits)")
    if not re.fullmatch(r"\d{4}", payload.aadhaar_last4):
        raise HTTPException(400, "Aadhaar last 4 must be 4 digits")
    if len(payload.full_name.strip()) < 2:
        raise HTTPException(400, "Name too short")
    rec = KYC(
        id=f"KYC-{uuid.uuid4().hex[:8].upper()}",
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        aadhaar_last4=payload.aadhaar_last4,
        email=payload.email,
        verified=True,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    await db.kyc.insert_one(rec.model_dump())
    return rec

# ── Complaints ───
CATEGORY_META = {
    "cleanliness": {"severity": "medium", "auth": "Railway Cleaning Supervisor + Coach Attendant", "code": "CLN", "sms": ["+91-9717641527 (Cleaning Cell)", "+91-139 (Helpdesk)"]},
    "alcohol": {"severity": "high", "auth": "RPF / TTE", "code": "ALC", "sms": ["+91-182 (RPF Helpline)", "+91-139 (Helpdesk)"]},
    "smoking": {"severity": "high", "auth": "RPF (Sec 167 - Indian Railways Act, fine ₹100-₹500)", "code": "SMK", "sms": ["+91-182 (RPF Helpline)", "+91-1512 (Security)"]},
    "food": {"severity": "medium", "auth": "IRCTC Food Quality + Pantry Manager", "code": "FUD", "sms": ["+91-1800-111-321 (IRCTC)", "+91-139 (Helpdesk)"]},
    "beggars": {"severity": "high", "auth": "RPF / GRP", "code": "BEG", "sms": ["+91-182 (RPF Helpline)", "+91-1512 (Security)"]},
    "other": {"severity": "medium", "auth": "Railway Helpdesk 139", "code": "OTH", "sms": ["+91-139 (Helpdesk)"]},
}

@api_router.post("/complaints", response_model=Complaint)
async def create_complaint(payload: ComplaintCreate):
    cat = payload.category.lower()
    meta = CATEGORY_META.get(cat, CATEGORY_META["other"])
    cid = f"YS-{meta['code']}-{uuid.uuid4().hex[:6].upper()}"

    prompt = (
        f"A woman traveller filed this railway complaint.\n"
        f"Category: {cat}\n"
        f"Train: {payload.train_no or 'N/A'} | Coach: {payload.coach or 'N/A'} | Station: {payload.station or 'N/A'}\n"
        f"Description: {payload.description}\n\n"
        f"Respond ONLY in compact JSON: {{\"severity\":\"low|medium|high|critical\","
        f"\"summary\":\"one-line summary (<20 words)\","
        f"\"action\":\"specific action authority should take (<25 words)\"}}"
    )
    ai_resp = await call_claude(prompt, max_tokens=180)
    severity = meta["severity"]
    summary = payload.description[:120]
    action = f"Forwarded to {meta['auth']} for immediate action."
    if ai_resp:
        try:
            start = ai_resp.find('{'); end = ai_resp.rfind('}')
            if start >= 0 and end > start:
                parsed = json.loads(ai_resp[start:end+1])
                severity = parsed.get("severity", severity).lower()
                summary = parsed.get("summary", summary)
                action = parsed.get("action", action)
        except Exception:
            pass

    # Log simulated SMS dispatch
    sms_log = {
        "complaint_id": cid,
        "recipients": meta["sms"],
        "message": f"YATRA SATHI ALERT [{severity.upper()}]: {cat.upper()} reported. Train {payload.train_no or 'NA'}, Coach {payload.coach or 'NA'}. Action: {action[:80]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "dispatched"
    }
    await db.sms_log.insert_one(sms_log)

    complaint = Complaint(
        id=cid, category=cat, description=payload.description,
        train_no=payload.train_no, coach=payload.coach, station=payload.station,
        location=payload.location,
        reporter_name=payload.reporter_name or "Anonymous",
        reporter_phone=payload.reporter_phone,
        has_photo=bool(payload.photo_b64),
        severity=severity, ai_summary=summary, action_taken=action,
        assigned_to=meta["auth"],
        sms_sent_to=meta["sms"],
        status="acknowledged",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    doc = complaint.model_dump()
    if payload.photo_b64:
        doc["photo_b64"] = payload.photo_b64[:2_000_000]  # cap ~2MB
    await db.complaints.insert_one(doc)
    return complaint

@api_router.get("/complaints", response_model=List[Complaint])
async def list_complaints(category: Optional[str] = None, limit: int = 50):
    q = {}
    if category and category != "all":
        q["category"] = category.lower()
    # exclude photo_b64 from list for performance
    docs = await db.complaints.find(q, {"_id": 0, "photo_b64": 0}).sort("timestamp", -1).to_list(limit)
    return docs

@api_router.get("/complaints/{cid}/photo")
async def get_complaint_photo(cid: str):
    doc = await db.complaints.find_one({"id": cid}, {"_id": 0, "photo_b64": 1})
    if not doc or not doc.get("photo_b64"):
        raise HTTPException(404, "No photo")
    return {"photo_b64": doc["photo_b64"]}

@api_router.post("/complaints/{cid}/status")
async def update_status(cid: str, body: StatusUpdate, x_admin_pin: Optional[str] = Header(None)):
    if x_admin_pin != ADMIN_PIN:
        raise HTTPException(403, "Invalid admin PIN")
    res = await db.complaints.update_one({"id": cid}, {"$set": {"status": body.status}})
    if res.matched_count == 0:
        raise HTTPException(404, "Complaint not found")
    return {"ok": True, "id": cid, "status": body.status}

@api_router.get("/complaints/stats")
async def complaint_stats():
    pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    raw = await db.complaints.aggregate(pipeline).to_list(100)
    by_category = {r["_id"]: r["count"] for r in raw}
    pipeline2 = [{"$group": {"_id": "$severity", "count": {"$sum": 1}}}]
    raw2 = await db.complaints.aggregate(pipeline2).to_list(100)
    by_severity = {r["_id"]: r["count"] for r in raw2}
    pipeline3 = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    raw3 = await db.complaints.aggregate(pipeline3).to_list(100)
    by_status = {r["_id"]: r["count"] for r in raw3}
    total = await db.complaints.count_documents({})
    return {"total": total, "by_category": by_category, "by_severity": by_severity, "by_status": by_status}

# ── Admin ───
class AdminAuth(BaseModel):
    pin: str

@api_router.post("/admin/auth")
async def admin_auth(body: AdminAuth):
    if body.pin != ADMIN_PIN:
        raise HTTPException(403, "Invalid PIN")
    return {"ok": True}

@api_router.get("/admin/sms-log")
async def sms_log(x_admin_pin: Optional[str] = Header(None), limit: int = 30):
    if x_admin_pin != ADMIN_PIN:
        raise HTTPException(403, "Invalid admin PIN")
    docs = await db.sms_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs

# ── AI Tips Proxy ───
class TipReq(BaseModel):
    prompt: str
    max_tokens: int = 100

@api_router.post("/ai/tip")
async def ai_tip(req: TipReq):
    txt = await call_claude(req.prompt, max_tokens=req.max_tokens)
    if not txt:
        return {"text": "Always choose well-lit coaches, share seat number with family, trust your instincts."}
    return {"text": txt}

# ── SOS ───
@api_router.post("/sos")
async def log_sos(event: SOSEvent):
    rec = {
        "id": str(uuid.uuid4()),
        "lat": event.lat, "lng": event.lng, "note": event.note,
        "user_name": event.user_name, "user_phone": event.user_phone,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.sos_events.insert_one(rec)
    # Also log SMS dispatch for SOS
    sms = {
        "complaint_id": rec["id"], "type": "SOS",
        "recipients": ["+91-182 (RPF)", "+91-1512 (Security)", "+91-100 (Police)"],
        "message": f"🚨 SOS: {event.user_name or 'Anonymous'} ({event.user_phone or 'NA'}) needs help. GPS: {event.lat},{event.lng}",
        "timestamp": rec["timestamp"], "status": "dispatched"
    }
    await db.sms_log.insert_one(sms)
    return {"ok": True, "id": rec["id"], "sms_to": sms["recipients"]}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"], allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
