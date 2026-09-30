# Ticket Defense Demo — Swiss Cheese + Akamai Simulation

Isolated ticketing Defense Lab demonstrating **Edge/WAF**, a **Waiting Room**, **Akamai-style Bot Manager simulation** (sensor + cookies + Bot Score), **fraud scoring**, and **mock 3DS**. It does not connect to a real ticketing platform.

See [WORKFLOW.md](WORKFLOW.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [GLOSSARY.md](GLOSSARY.md) for the route, service map, and terminology.

The admin Event Config dialog switches Workflow Profiles A–D at runtime. Profiles A/B/D enforce mock Login Gates and C/D enable server checked form CAPTCHA. Login accepts any nonempty password for a valid email and creates a separate Auth Session; it is a lab identity only.

The buyer UI uses the fictional Defense Live brand and one real crowd photograph across the waiting room, member check, seat selection, and checkout. Event-specific poster artwork has been removed. The seating diagram is illustrative. See [frontend/ASSETS.md](frontend/ASSETS.md) for the photo source and license. The checkout remains a simulation and does not take real payments.

## Quick Start (Docker)

```bash
cd defense-bot
docker compose -f docker-compose.defense.yml up --build
```

For a Linux server installation that can be controlled over SSH from another device, see [REMOTE_CLI.md](REMOTE_CLI.md). It adds a `defense-demo` command for starting the lab and running tests.

| URL | หน้า | Defense Layer |
|-----|------|---------------|
| http://localhost:8090/ | Waiting Room (Ticket UI) | Edge + WAF + Akamai + Queue-it |
| http://localhost:8090/?demo=1 | Demo เร็ว (~8s countdown) | ทั้งหมด |
| http://localhost:8090/seats | เลือกที่นั่ง | AI (Telemetry → Fraud Engine) |
| http://localhost:8090/checkout | ชำระเงิน + 3DS | Payment/3DS |
| http://localhost:8090/admin | Live Audit Dashboard | ทุก layer |
| http://localhost:8090/login | Mock Login Gate | Auth Session |
| http://localhost:8090/captcha | Form CAPTCHA | Server checked challenge |

**Event:** BANGKOK LIVE EXPERIENCE 2026 (`demo-concert-2026`)

## Defense Stack (สเปกจำลอง Ticket)

### Edge & Network Layer
- **CDN headers**: `X-CDN-Edge`, `X-Cache-Status`, `X-AZ-Zone` (Multi-AZ: `az-bkk-1/2/3`)
- **Global Anti-DDoS**: cluster-wide RPS cap (`EDGE_DDOS_GLOBAL_RPS`, default 800)
- **WAF**: datacenter IP block, burst, per-route rate limits

### Traffic Control — Waiting Room
- Virtual Waiting Room UI + funnel `queue-status` (`/graphql/v2` is disabled by default)
- Redis sorted waiting list with atomic FIFO or Bot Score priority admission, capped by `ADMISSION_RATE` per second
- `off` mode admits without rate limiting; queue tokens remain bound to IP and Sensor Session
- A configurable soft-open period admits at 25% of the normal rate after sale start

### Akamai Bot Manager (จำลอง)
| รายการ | รายละเอียด |
|--------|------------|
| Bot Score | 0–100 (0 = มนุษย์แท้) |
| Cookies | `_abck`, `ak_bmsc` (HttpOnly), `bm_sv` (request count) |
| Sensor | `akamai-sensor.js` → >100 signals → PRNG shuffle + substitution → `POST /api/sensor` |
| Challenge | score ≥ 55 → `_abck` status `-1` → modal → `POST /api/challenge/pass` |
| Queue tie-in | `priority_score` จัดลำดับคะแนนต่ำก่อน; sensor challenge เป็นอีกขั้นหนึ่ง |

### AI + 3DS (เดิม)
- Telemetry mouse/scroll → Fraud Engine (รวม bot_score จาก Akamai)
- Mock 3DS OTP: `123456`

## User Flow

1. โหลดหน้า Waiting Room → **Akamai Sensor** inject + ส่ง `sensor_data`
2. Server ถอดรหัส → ตั้ง cookies → แสดง Bot Score
3. Join Waiting Room → FIFO หรือ score priority admission
4. ถ้า challenge → กด Complete Challenge → ลด score → เข้าคิวต่อ
5. Admitted → token → Seat map → Checkout

## API (Akamai)

```http
POST /api/sensor
{ "sensor_data": "<encrypted>", "session_id": "...", "fingerprint": "..." }

POST /api/challenge/pass
Headers: x-session-id: <uuid>
```

## Red Team (Ticket-bot)

```json
{
  "graphql_url": "http://defense-gateway:8090/graphql/v2",
  "event_id": "demo-concert-2026"
}
```

คำขอที่ไม่มี sensor / telemetry อาจเจอ sensor gate หรือ fraud block; `priority_score` จัดลำดับตาม Bot Score

## Bot bypass lockdown (ปิด GraphQL)

| Variable | Default | ความหมาย |
|----------|---------|----------|
| `GRAPHQL_ENABLED` | `false` | ปิด `/graphql/v2` — บอทยิง GraphQL ข้ามคิวไม่ได้ |
| `BOT_BYPASS_BLOCK` | `true` | บล็อก API ที่มี header บอท (`apollographql-client-name`, `x-Ticket-version`) และ API ที่ไม่มี sensor session |

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

## Test and observe

```bash
docker compose -f docker-compose.defense.yml --profile test run --rm --build lab-tests
docker compose -f docker-compose.defense.yml up -d --build gateway
docker compose -f docker-compose.defense.yml --profile test run --rm --build lab-smoke
docker compose -f docker-compose.defense.yml --profile loadgen run --rm --build bot-loadgen
docker compose -f docker-compose.defense.yml --profile observability up -d
```

The load generator only accepts the local lab gateway and defaults to one actor per scenario. Set `SCENARIO_PACK=medium|large` or `LOADGEN_COUNT` for a bounded larger run. JSON results go to `reports/`. Prometheus is at `http://localhost:9090`, Grafana at `http://localhost:3000`, and raw metrics at `/metrics`. See [SCENARIOS.md](SCENARIOS.md) and [AFTER_ACTION_REPORT.md](AFTER_ACTION_REPORT.md).
