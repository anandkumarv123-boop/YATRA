# Yatra Sathi — Women Safety AI Platform

## Original Problem Statement
User shared a single-file HTML app ("Yatra Sathi") for Indian Railway women-safety with SOS, AI detection, crowd heat maps, train tracking, reviews and hotels. Asked to **finish in this session** by adding:
- Auto alerting for non-cleanliness issues
- Authority takeover when complaint reported on portal for:
  - Alcohol consumption inside train
  - Smoking in train bathroom
  - Food quality issues (IRCTC pantry)
  - Beggars / unauthorized vendors
- Best UI
- KYC verification
- Photo upload for evidence
- Admin dashboard
- SMS to RPF (simulated)

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`) on port 8001, MongoDB storage
- **Frontend**: Single static HTML (`/app/frontend/public/app.html`); React App.js redirects `/` → `/app.html`
- **AI**: Emergent LLM key with Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via `emergentintegrations` for auto-categorization + safety tips
- **Database**: MongoDB collections: `complaints`, `kyc`, `sos_events`, `sms_log`

## User Personas
- **Woman traveller** (primary): Files complaints, uses SOS, KYC verified
- **RPF / IRCTC admin** (secondary): Logs in via PIN, manages complaints, views SMS log

## Core Requirements (static)
- One-tap SOS with GPS + audio evidence
- Complaint portal with auto-takeover by authority
- AI Claude-powered severity + action recommendation
- Photo evidence upload (downscaled to 900px, JPEG q=0.75)
- KYC verification (name, phone, Aadhaar last 4)
- Admin dashboard with PIN auth, stats, SMS log
- Live crowd heat maps + AI safety tips for reviews/hotels

## What's Been Implemented (Jan 2026)
### Backend Endpoints
- `POST /api/kyc` — KYC submission with validation
- `POST /api/complaints` — submit complaint, AI auto-categorize, simulated SMS dispatch
- `GET /api/complaints?category=...` — list (photo_b64 excluded for perf)
- `GET /api/complaints/{id}/photo` — fetch photo on demand
- `POST /api/complaints/{id}/status` — admin status update (requires X-Admin-Pin header)
- `GET /api/complaints/stats` — aggregate stats
- `POST /api/admin/auth` — PIN validation
- `GET /api/admin/sms-log` — admin-only SMS dispatch log
- `POST /api/sos` — logs SOS event + auto-creates RPF SMS log
- `POST /api/ai/tip` — Claude proxy for review/hotel safety tips
- `GET /api/health`

### Frontend Pages
- Home (with stats, 6 feature cards including new Report Issue)
- Complaint Portal (6 categories, photo upload, AI takeover banner)
- AI Detection (live mic monitor, simulated motion/stress sensors)
- Crowd Heat (live updating station + coach occupancy)
- SOS (3-sec hold, KYC-aware, GPS share)
- Reviews (with Claude AI safety analysis box)
- Safe Hotels (10 cities, Claude AI city tip)
- **Admin Dashboard** (PIN gated, stats, SMS log, complaint management)

### Auto-Takeover Categories
| Category | Severity | Authority | SMS To |
|----------|----------|-----------|--------|
| Cleanliness | medium | Cleaning Supervisor + Coach Attendant | +91-9717641527, +91-139 |
| Alcohol | high | RPF / TTE | +91-182, +91-139 |
| Smoking | high | RPF (Sec 167 fine) | +91-182, +91-1512 |
| Food | medium | IRCTC + Pantry Manager | +91-1800-111-321, +91-139 |
| Beggars | high | RPF / GRP | +91-182, +91-1512 |
| Other | medium | Railway Helpdesk | +91-139 |

## Testing Status
- **Backend**: 22/22 pytest tests passed (KYC, complaints, photo, admin auth, SMS, SOS, AI tip)
- **Frontend**: 9/9 Playwright flows passed (KYC modal, user bar reveal, 8-button bottom nav fixed, complaint submission with AI summary, admin PIN unlock + dashboard, SOS 3-sec hold)

## Backlog / Next Tasks
- P1: Move photo storage to S3/GridFS for scale
- P1: Convert admin PIN auth → session token + httponly cookie
- P2: Real SMS dispatch via Twilio / MSG91
- P2: Map view for SOS / complaint hotspots
- P2: Multi-language support (Hindi, Tamil, Telugu)
- P3: Push notifications for SOS recipients
- P3: Refactor app.html into modular JS/CSS

## Test Credentials
- Admin PIN: `1234` (overridable via `ADMIN_PIN` env var)
