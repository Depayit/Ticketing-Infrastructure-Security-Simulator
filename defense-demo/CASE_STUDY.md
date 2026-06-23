# Defense Demo Case Study — Ticket High-Demand Event

## Overall Risk: **สูง (High)**

High-Demand Event มี Financial Incentive สูง → เป้าหมายหลักของ Scalper Bots และ DDoS

## Swiss Cheese Model — 3 Layers

| Layer | ตรวจจับ | ไม่จับ |
|-------|---------|--------|
| **IP** | Basic bot, burst, datacenter IP | Residential proxy |
| **AI** | API-only, token→lock <1s, ไม่มี mouse/scroll | Human-assisted scalper |
| **3DS** | Carding, stolen card | บัตร scalper จริง |

## Architecture (Decoupled)

```
Queue Service → Seat Service (Redis pessimistic lock) → Payment Service (3DS) → DB commit
         ↑                    ↑                              ↑
    IP Gateway            AI Fraud Engine                 3DS OTP
```

## Red Team vs Blue Team Demo

### Scenario A — Basic Bot → IP Layer
```bash
# Burst >15 req/5s → 429 RATE_LIMIT_BURST
for i in {1..20}; do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8090/graphql/v2 \
  -H "Content-Type: application/json" \
  -d '{"query":"query { queueStatus(eventId: \"demo-concert-2026\") { status token } }"}'; done
```

### Scenario B — Ticket-bot Worker → AI Layer
1. ตั้ง `graphql_url` ใน worker config เป็น `http://defense-gateway:8090/graphql/v2`
2. ตั้ง `event_id` เป็น `demo-concert-2026`
3. รัน worker — bot ยิง GraphQL ตรงไม่มี telemetry → **403 FRAUD_DETECTED**

Attack signature จาก `worker/bot.py`:
- `_token_warmup_loop` → token พร้อมล่วงหน้า
- `_purchase_wave_custom` → concurrent addToCart
- ไม่มี mouse/scroll events

### Scenario C — Human Flash Crowd → ผ่านทุก Layer
1. เปิด http://localhost:8090/
2. รอผ่าน Waiting Room → Seat Map
3. เลื่อน/ hover / คลิกที่นั่ง (telemetry ส่งอัตโนมัติ)
4. Checkout → กรอก OTP `123456` → commit สำเร็จ

### Scenario D — Bot หลุด AI → 3DS Layer
```bash
# ปิด AI Layer
AI_LAYER_ENABLED=false docker compose -f docker-compose.defense.yml up
```
Bot lock ได้ แต่ checkout ติด 3DS redirect → ไม่ commit → seat release

## Admin Dashboard

http://localhost:8090/admin — Live audit feed แยกตาม layer (ip / ai / 3ds)

## วิธีรัน

```bash
cd defense-demo
docker compose -f docker-compose.defense.yml up --build
```
## Key Files

| File | Role |
|------|------|
| `gateway/rules.py` | WAF + rate limit + burst + token-IP binding |
| `fraud-engine/main.py` | Hybrid rule + IsolationForest scoring |
| `seat-service/main.py` | Pessimistic lock + fraud gate |
| `payment-service/main.py` | Mock 3DS + carding detection |
| `frontend/telemetry.js` | Behavioral biometrics SDK |

