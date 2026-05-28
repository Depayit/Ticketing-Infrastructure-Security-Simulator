# Bot Connector — ระบบเชื่อมต่อ Bot ภายนอก

API Gateway ให้ Bot ที่พัฒนาจากที่อื่นเข้ามาทดสอบใน **Defense Demo Sandbox** ได้

## เริ่มใช้งาน

```bash
# รัน stack หลัก (มี bot-connector แล้ว)
docker compose up --build -d bot-connector manager

# ต้องมี defense-demo รันอยู่ด้วย
cd defense-demo
docker compose -f docker-compose.defense.yml up -d
```

| Service | URL |
|---------|-----|
| Bot Connector | http://localhost:8100 |
| API Docs | http://localhost:8100/docs |
| Sandbox | http://localhost:8090 |

## Quick Start

### 1. ลงทะเบียน Bot

```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8100/api/v1/register" `
  -ContentType "application/json" `
  -Body '{"name":"My External Bot","description":"v1.0"}'
```

เก็บ `api_key` ที่ได้

### 2. สร้าง Session ทดสอบ

```powershell
$headers = @{ "X-API-Key" = "ttm_YOUR_KEY" }
Invoke-RestMethod -Method POST -Uri "http://localhost:8100/api/v1/sessions" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"event_id":"demo-concert-2026"}'
```

### 3. ทดสอบ GraphQL

```powershell
$body = '{"query":"query { queueStatus(eventId: \"demo-concert-2026\") { status token } }"}'
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8100/api/v1/sessions/sess-XXXX/graphql" `
  -Headers $headers -ContentType "application/json" -Body $body
```

### 4. ตัวอย่าง Python

```bash
pip install httpx
python bot-connector/examples/external_bot_client.py --scenario B
python bot-connector/examples/external_bot_client.py --scenario C
```

## API หลัก

| Method | Path | คำอธิบาย |
|--------|------|----------|
| POST | `/api/v1/register` | ลงทะเบียน Bot → ได้ api_key |
| GET | `/api/v1/sandbox/info` | ข้อมูล sandbox + test scenarios |
| POST | `/api/v1/sessions` | สร้าง session ทดสอบ |
| POST | `/api/v1/sessions/{id}/graphql` | Proxy GraphQL ไป sandbox |
| POST | `/api/v1/sessions/{id}/telemetry/simulate-human` | จำลองพฤติกรรมมนุษย์ |
| POST | `/api/v1/sessions/{id}/3ds/verify` | ยืนยัน OTP (default: 123456) |
| WS | `/api/v1/ws/sessions/{id}?api_key=...` | Real-time session logs |

## Test Scenarios

| ID | ชื่อ | ผลที่คาดหวัง |
|----|------|-------------|
| A | IP burst | 429 RATE_LIMIT_BURST |
| B | API-only bot | 403 FRAUD_DETECTED |
| C | Human-like | ผ่าน AI layer |
| D | 3DS only | ติด OTP ถ้าหลุด AI |

## เชื่อม Bot ที่มีอยู่

Bot ภายนอกใช้ Connector แทนการยิงตรงไป sandbox:

```python
CONNECTOR = "http://localhost:8100"
HEADERS = {"X-API-Key": "ttm_...", "Content-Type": "application/json"}

# 1. สร้าง session
session = requests.post(f"{CONNECTOR}/api/v1/sessions", headers=HEADERS, json={...}).json()

# 2. ยิง GraphQL ผ่าน connector (ใส่ x-session-id ให้อัตโนมัติ)
requests.post(
    f"{CONNECTOR}/api/v1/sessions/{session['session']['session_id']}/graphql",
    headers=HEADERS,
    json={"query": "...", "variables": {...}},
)
```

## Environment Variables

| Variable | Default |
|----------|---------|
| `REDIS_URL` | `redis://redis:6379/0` |
| `SANDBOX_GATEWAY_URL` | `http://host.docker.internal:8090` |
| `SANDBOX_EVENT_ID` | `demo-concert-2026` |
| `CONNECTOR_PORT` | `8100` |
