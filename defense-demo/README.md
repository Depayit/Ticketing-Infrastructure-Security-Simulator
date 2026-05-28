# TTM Defense Demo — Swiss Cheese + Akamai Simulation

Mock ticketing platform demonstrating **Edge/CDN**, **Queue-it priority queue**, **Akamai Bot Manager** (sensor + cookies + bot score), **AI fraud**, and **3DS** against `ttm-bot-2026`.

## Quick Start (Docker)

```bash
cd defense-demo
docker compose -f docker-compose.defense.yml up --build
```

| URL | หน้า | Defense Layer |
|-----|------|---------------|
| http://localhost:8090/ | Waiting Room (TTM UI) | Edge + WAF + Akamai + Queue-it |
| http://localhost:8090/?demo=1 | Demo เร็ว (~8s countdown) | ทั้งหมด |
| http://localhost:8090/seats | เลือกที่นั่ง | AI (Telemetry → Fraud Engine) |
| http://localhost:8090/checkout | ชำระเงิน + 3DS | Payment/3DS |
| http://localhost:8090/admin | Live Audit Dashboard | ทุก layer |

**Event:** 2026-27 JACOB WORLD TOUR IN BANGKOK (`demo-concert-2026`)

## Defense Stack (สเปกจำลอง TTM)

### Edge & Network Layer
- **CDN headers**: `X-CDN-Edge`, `X-Cache-Status`, `X-AZ-Zone` (Multi-AZ: `az-bkk-1/2/3`)
- **Global Anti-DDoS**: cluster-wide RPS cap (`EDGE_DDOS_GLOBAL_RPS`, default 800)
- **WAF**: datacenter IP block, burst, per-route rate limits

### Traffic Control — Queue-it
- Virtual Waiting Room UI + GraphQL `queueStatus`
- **Randomized queue position** (display inflated by bot score)
- **Priority admission**: Redis ZSET sorted by bot score (ต่ำ = ผ่านก่อน)

### Akamai Bot Manager (จำลอง)
| รายการ | รายละเอียด |
|--------|------------|
| Bot Score | 0–100 (0 = มนุษย์แท้) |
| Cookies | `_abck`, `ak_bmsc` (HttpOnly), `bm_sv` (request count) |
| Sensor | `akamai-sensor.js` → >100 signals → PRNG shuffle + substitution → `POST /api/sensor` |
| Challenge | score ≥ 55 → `_abck` status `-1` → modal → `POST /api/challenge/pass` |
| Queue tie-in | score ต่ำ = priority สูง, score สูง = คิวช้า + challenge |

### AI + 3DS (เดิม)
- Telemetry mouse/scroll → Fraud Engine (รวม bot_score จาก Akamai)
- Mock 3DS OTP: `123456`

## User Flow

1. โหลดหน้า Waiting Room → **Akamai Sensor** inject + ส่ง `sensor_data`
2. Server ถอดรหัส → ตั้ง cookies → แสดง Bot Score
3. Join Queue → เข้า ZSET ตาม priority
4. ถ้า challenge → กด Complete Challenge → ลด score → เข้าคิวต่อ
5. Admitted → token → Seat map → Checkout

## API (Akamai)

```http
POST /api/sensor
{ "sensor_data": "<encrypted>", "session_id": "...", "fingerprint": "..." }

POST /api/challenge/pass
Headers: x-session-id: <uuid>
```

## Red Team (ttm-bot)

```json
{
  "graphql_url": "http://defense-gateway:8090/graphql/v2",
  "event_id": "demo-concert-2026"
}
```

บอทที่ไม่ส่ง sensor / ไม่มี telemetry → Bot Score สูง → คิวช้า / challenge / AI block

## Bot bypass lockdown (ปิด GraphQL)

| Variable | Default | ความหมาย |
|----------|---------|----------|
| `GRAPHQL_ENABLED` | `false` | ปิด `/graphql/v2` — บอทยิง GraphQL ข้ามคิวไม่ได้ |
| `BOT_BYPASS_BLOCK` | `true` | บล็อก API ที่มี header บอท (`apollographql-client-name`, `x-ttm-version`) และ API ที่ไม่มี sensor session |

เบราว์เซอร์จริงใช้ `/api/funnel/*` หลังส่ง Akamai sensor แล้วเท่านั้น

## Env

| Variable | Default | ความหมาย |
|----------|---------|----------|
| `BOT_CHALLENGE_THRESHOLD` | 55 | ต้อง challenge |
| `BOT_SCORE_ADMIT_MAX` | 75 | ไม่ admit ถ้า score สูงกว่านี้ |
| `ADMISSION_RATE` | 50 | admission window |
| `EDGE_DDOS_GLOBAL_RPS` | 800 | global RPS cap |

## Disable AI Layer

`AI_LAYER_ENABLED=false` on fraud-engine service.

See [CASE_STUDY.md](CASE_STUDY.md) for scenarios.
