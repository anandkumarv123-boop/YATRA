# Yatra Sathi v2 — Smart Rail Travel Companion

## Original Problem Statement
Started as a women-safety HTML app. User progressively expanded to a **universal passenger Smart Rail Companion** with:
- Food On Journey (IRCTC + Zomato + Station + Local vendors)
- Rail Home Foods (self-employment ecosystem for housewives/home cooks)
- Station Hub intelligence (all amenities + AI smart routing)
- Yatra AI assistant (Claude-powered chat, India-focused)
- Live train tracking with animated progress
- KYC verification
- Photo evidence upload
- Admin dashboard with PIN
- SMS dispatch simulation to RPF / IRCTC / Helpdesk
- Auto-takeover complaint portal (cleanliness/alcohol/smoking/food/beggars)
- Flipkart-style premium UI for all passengers

## Architecture
- **Backend**: FastAPI on port 8001 (`/app/backend/server.py`), MongoDB
- **Frontend**: Single static HTML (`/app/frontend/public/app.html`, ~1130 lines); React App.js redirects `/` → `/app.html`
- **AI**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via `emergentintegrations` + Emergent LLM key
- **DB Collections**: complaints, kyc, sos_events, sms_log, food_orders, home_cooks, home_food_menu

## v2 Endpoints
### Food Ordering
- `GET /api/food/vendors?station=X&category=Y&veg=true|false`
- `GET /api/food/menu/{vendor_id}` (10 items: thali, biryani, dosa, paneer, family combo, diabetic, baby food, senior meal, salad, late-night maggi)
- `GET /api/food/recommendations?station=X&diet=Y` (6 sections + Claude AI tip)
- `POST /api/food/order` (with PNR/train/coach/seat/station)
- `GET /api/food/order/{id}` (live tracking: preparing→cooking→packed→out_for_delivery→delivered)

### Rail Home Foods
- `POST /api/home-foods/cook` (register)
- `GET /api/home-foods/cooks?station=X&city=Y` (auto-seeds demo cooks)
- `POST /api/home-foods/menu` (cook adds item)
- `GET /api/home-foods/menu/{cook_id}` (auto-seeds menu)
- `GET /api/home-foods/insights/{cook_id}` (AI sales coach via Claude)

### Station & Train
- `GET /api/station/{code}/hub` (NDLS, CSTM, HWH, MAS, TVC, BPL, BCT, ERS, ADI + AI route)
- `GET /api/stations/search?q=`
- `GET /api/pnr/{pnr}` (deterministic mock)
- `GET /api/train/{train_no}/live` (animated route, coaches, ETA)

### Yatra AI Chat
- `POST /api/ai/chat` (Claude Haiku, India-focused railway assistant)

### V1 retained
- `POST /api/kyc`, complaints, SOS, admin, AI tip — all working

## Frontend Pages (12)
Home (Flipkart layout) · Food · Home Foods (Customer/Cook tabs) · Live Trains · PNR · Station Hub · Yatra AI Chat · SOS · AI Detect · Crowd · Complaints · Hotels · Admin

## Testing
- **v2 backend**: 43/43 pytest tests passing (KYC, complaints, admin, SOS, AI tip, food vendors/menu/recommendations/order/tracking, home cook register/list/menu/insights, station hub, PNR, train live, AI chat)
- **v2 frontend**: Home/Food/Home-Foods/Trains/PNR/Station Hub/Yatra AI Chat all visually verified with correct testids and live data

## Fixes after iteration 2 testing
- Added data-testid on all 8 home quick-grid tiles
- Added data-testid=`banner-yatra-ai` for consistency
- Fixed `Trending Near You` + `Home Kitchens` slow-paint race with retry after 2.5s
- Added empty-items validation to POST /api/food/order

## Backlog
- P1: Real Twilio/MSG91 SMS dispatch (currently simulated)
- P1: Voice input for Yatra AI (Whisper STT)
- P1: Photo storage → S3/GridFS
- P2: Real IRCTC eCatering API integration
- P2: Map view of nearby cooks/stations
- P2: Hindi/Tamil/Telugu language support
- P3: Push notifications for SOS + order updates
- P3: Cook earnings withdrawal flow (UPI integration)

## Test Credentials
- Admin PIN: `1234` (env `ADMIN_PIN`)
- KYC: any 2+ char name, 10-digit phone, 4-digit Aadhaar
- PNR test: `1234567890` returns Mumbai Rajdhani
- Train test: `12951` returns animated live route
- Station hub test: `NDLS`, `CSTM`, `HWH`, `MAS`, `BPL`, `TVC`, `BCT`, `ERS`, `ADI`
