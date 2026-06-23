import asyncio
import hashlib
import json
import logging
import os
import random
import time
from typing import Dict, List, Optional
import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import redis

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("proxy_rotator")

app = FastAPI(title="Ticket Proxy Rotator Service")

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# ── Redis Key Schema Constants ───────────────────────────────────────────────
KEY_RAW_PROXIES = "ticket:proxies:raw"         # Set of raw proxy URLs
KEY_ACTIVE_PROXIES = "ticket:proxies:active"   # Set of healthy active proxy URLs
KEY_DEAD_PROXIES = "ticket:proxies:dead"       # Set of dead/unhealthy proxy URLs
LEASE_TTL = 45                              # Lease TTL in seconds

def get_proxy_hash(proxy: str) -> str:
    return hashlib.md5(proxy.encode("utf-8")).hexdigest()

def get_meta_key(proxy: str) -> str:
    return f"ticket:proxies:meta:{get_proxy_hash(proxy)}"

def get_lease_key(proxy: str) -> str:
    return f"ticket:proxies:lease:{get_proxy_hash(proxy)}"

# ── Health Checker Implementation ────────────────────────────────────────────

# Hosting providers and Datacenters keywords to exclude (IP ไทยจริง, ไม่ใช่ datacenter)
DATACENTER_KEYWORDS = [
    "amazon", "aws", "google", "gcp", "azure", "microsoft", "digitalocean",
    "linode", "vultr", "hetzner", "ovh", "datacenter", "hosting", "server",
    "cloud", "choopa", "m247", "leaseweb", "zenlayer", "cogent", "he.net",
    "cloudflare", "fastly", "shinjiru", "contabo", "interserver", "hostinger",
    "path.net", "ovh", "dedipath", "kamatera", "scaleway", "i3d", "equinix"
]

async def check_single_proxy(proxy: str):
    """
    Checks a single proxy:
    - Target: http://ip-api.com/json
    - Must respond within 3.5s
    - Country code must be TH (Thailand)
    - Must not belong to a known hosting/cloud provider
    """
    meta_key = get_meta_key(proxy)
    start_time = time.time()
    
    # Pre-populate metadata structure
    meta = {
        "proxy": proxy,
        "ip": "Unknown",
        "country": "Unknown",
        "countryCode": "Unknown",
        "isp": "Unknown",
        "org": "Unknown",
        "is_datacenter": False,
        "latency": 9.9,
        "status": "dead",
        "error": "",
        "last_checked": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        # Check through proxy with 3.5s timeout
        # Using HTTP endpoint of ip-api for faster connection (no SSL handshake overhead)
        async with httpx.AsyncClient(proxy=proxy, timeout=3.5) as client:
            resp = await client.get("http://ip-api.com/json?fields=status,message,country,countryCode,isp,org,as,query")
            
            latency = time.time() - start_time
            meta["latency"] = round(latency, 3)

            if resp.status_code != 200:
                raise Exception(f"HTTP Status {resp.status_code}")
                
            data = resp.json()
            if data.get("status") == "fail":
                raise Exception(f"IP API returned fail: {data.get('message', 'unknown')}")

            meta["ip"] = data.get("query", "Unknown")
            meta["country"] = data.get("country", "Unknown")
            meta["countryCode"] = data.get("countryCode", "Unknown")
            meta["isp"] = data.get("isp", "Unknown")
            meta["org"] = data.get("org", "Unknown")

            # Validate Thailand geo-targeting
            # if meta["countryCode"] != "TH":
            #     raise Exception(f"Non-TH IP: Located in {meta['countryCode']} ({meta['country']})")

            # Validate Latency < 3.5s
            if latency >= 3.5:
                raise Exception(f"High latency: {latency:.2f}s (required < 3.5s)")

            # Validate Not Datacenter
            isp_lower = meta["isp"].lower()
            org_lower = meta["org"].lower()
            as_lower = data.get("as", "").lower()
            
            is_dc = False
            for kw in DATACENTER_KEYWORDS:
                if kw in isp_lower or kw in org_lower or kw in as_lower:
                    is_dc = True
                    break
            
            meta["is_datacenter"] = is_dc
            if is_dc:
                raise Exception(f"Datacenter detected: {meta['isp']} / {meta['org']}")

            # All checks passed!
            meta["status"] = "active"
            
            # Save metadata & update active pools
            r.set(meta_key, json.dumps(meta))
            r.sadd(KEY_ACTIVE_PROXIES, proxy)
            r.srem(KEY_DEAD_PROXIES, proxy)
            
    except Exception as e:
        latency = time.time() - start_time
        meta["latency"] = round(latency, 3)
        meta["status"] = "dead"
        meta["error"] = str(e)
        
        # Save dead metadata & update pools
        r.set(meta_key, json.dumps(meta))
        r.srem(KEY_ACTIVE_PROXIES, proxy)
        r.sadd(KEY_DEAD_PROXIES, proxy)

async def run_health_checker():
    """Background task that runs the health checks continuously."""
    semaphore = asyncio.Semaphore(15) # Concurrent worker limit for checks
    last_saved_at = None
    
    while True:
        try:
            # Sync raw proxies list from general config
            cfg_str = r.get("ticket:config")
            if cfg_str:
                cfg = json.loads(cfg_str)
                current_saved_at = cfg.get("_saved_at")
                
                # If timestamp is new or different, perform full synchronization
                if current_saved_at != last_saved_at:
                    logger.info(f"Main config updated (saved_at={current_saved_at}). Syncing proxy list...")
                    config_proxies = cfg.get("proxies", [])
                    
                    # Clear raw proxies and rebuild pool
                    r.delete(KEY_RAW_PROXIES)
                    for p in config_proxies:
                        p = p.strip()
                        if not p:
                            continue
                        if "{session}" in p:
                            for i in range(1, 41):
                                expanded_p = p.replace("{session}", f"ticketsess{i:03d}")
                                r.sadd(KEY_RAW_PROXIES, expanded_p)
                        else:
                            r.sadd(KEY_RAW_PROXIES, p)
                            
                    last_saved_at = current_saved_at
            
            raw_proxies = r.smembers(KEY_RAW_PROXIES)
            if raw_proxies:
                logger.info(f"Starting health check for {len(raw_proxies)} proxies...")
                
                async def worker(proxy: str):
                    async with semaphore:
                        await check_single_proxy(proxy)

                tasks = [worker(proxy) for proxy in raw_proxies]
                await asyncio.gather(*tasks)
                
                active_count = r.scard(KEY_ACTIVE_PROXIES)
                dead_count = r.scard(KEY_DEAD_PROXIES)
                logger.info(f"Health check round completed: {active_count} active, {dead_count} dead.")
            else:
                logger.info("No raw proxies to check.")
                
        except Exception as e:
            logger.error(f"Error in health checker loop: {e}")
            
        # Run every 25-35 seconds (jittered)
        sleep_time = random.uniform(25, 35)
        await asyncio.sleep(sleep_time)

@app.on_event("startup")
async def startup_event():
    # Start the health checker background loop
    asyncio.create_task(run_health_checker())

# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/proxies/upload")
async def upload_proxies(request: Request):
    """
    Upload a list of proxies. Supports both static lists and rotating gateways using {session}.
    Supports optional session_count (default 30).
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    proxies_list = body.get("proxies", [])
    session_count = body.get("session_count", 30)
    
    if not isinstance(proxies_list, list):
        raise HTTPException(status_code=400, detail="Proxies field must be a list of strings")

    added_count = 0
    # Clear old raw set to upload new ones
    r.delete(KEY_RAW_PROXIES)
    
    # We also sync to config's "proxies" list for backward compatibility
    # so we don't break existing setups
    for p in proxies_list:
        p = p.strip()
        if not p:
            continue
        
        # If it contains {session}, expand it into session-based proxies
        if "{session}" in p:
            for s in range(1, session_count + 1):
                sess_proxy = p.replace("{session}", f"Ticket{random.randint(100000, 999999)}")
                r.sadd(KEY_RAW_PROXIES, sess_proxy)
                added_count += 1
        else:
            r.sadd(KEY_RAW_PROXIES, p)
            added_count += 1

    # Also update ticket:config so the main dashboard Setup page aligns
    cfg_str = r.get("ticket:config")
    if cfg_str:
        cfg = json.loads(cfg_str)
        cfg["proxies"] = proxies_list
        r.set("ticket:config", json.dumps(cfg))

    # Trigger async re-check of newly uploaded proxies
    asyncio.create_task(run_health_checker())

    return {"status": "success", "message": f"Uploaded and expanded into {added_count} raw proxies."}

@app.post("/api/proxies/acquire")
async def acquire_proxies(request: Request):
    """
    Acquire unique active proxies for a specific worker.
    Uses a lease mechanism to prevent duplicate assignments across workers.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    worker_id = body.get("worker_id")
    count = body.get("count", 5)

    if not worker_id:
        raise HTTPException(status_code=400, detail="worker_id is required")

    active_proxies = list(r.smembers(KEY_ACTIVE_PROXIES))
    
    # 1. Find existing valid leases held by this worker
    assigned_proxies = []
    
    # Filter only those that are still in active_proxies and leased to us
    for p in active_proxies:
        lease_val = r.get(get_lease_key(p))
        if lease_val == worker_id:
            assigned_proxies.append(p)
            # Renew the lease TTL
            r.expire(get_lease_key(p), LEASE_TTL)

    # 2. If we need more, find free active proxies (no lease key exists)
    needed = count - len(assigned_proxies)
    if needed > 0:
        free_proxies = []
        for p in active_proxies:
            if p not in assigned_proxies:
                lease_val = r.get(get_lease_key(p))
                if not lease_val:
                    free_proxies.append(p)
        
        # Shuffle to avoid all workers competing for the exact same subset
        random.shuffle(free_proxies)
        
        to_assign = free_proxies[:needed]
        for p in to_assign:
            # Set lease key in Redis with TTL
            r.set(get_lease_key(p), worker_id, ex=LEASE_TTL)
            assigned_proxies.append(p)

    # 3. If there are literally no free active proxies left in the pool,
    # fallback to return whatever is active (allowing duplication only as a last resort)
    if len(assigned_proxies) < count and active_proxies:
        logger.warning(f"Worker {worker_id} requested {count} proxies but only {len(assigned_proxies)} unique ones available. Falling back to shared allocation.")
        needed = count - len(assigned_proxies)
        shared_pool = [p for p in active_proxies if p not in assigned_proxies]
        if not shared_pool:
            shared_pool = active_proxies
        random.shuffle(shared_pool)
        assigned_proxies.extend(shared_pool[:needed])

    return {"status": "success", "worker_id": worker_id, "proxies": assigned_proxies}

@app.get("/api/proxies/status")
async def get_proxies_status():
    """Retrieve full proxy status stats & metadata list."""
    raw_list = list(r.smembers(KEY_RAW_PROXIES))
    active_list = list(r.smembers(KEY_ACTIVE_PROXIES))
    dead_list = list(r.smembers(KEY_DEAD_PROXIES))
    
    meta_list = []
    # Build list from raw proxies
    for p in raw_list:
        meta_str = r.get(get_meta_key(p))
        if meta_str:
            meta = json.loads(meta_str)
            # Add lease info
            lease_val = r.get(get_lease_key(p))
            meta["leased_to"] = lease_val if lease_val else None
            # Hide proxy password in response
            obfuscated_p = p
            if "@" in p and "://" in p:
                parts = p.split("@")
                proto_cred = parts[0]
                host_port = parts[1]
                if ":" in proto_cred:
                    proto_parts = proto_cred.split(":")
                    obfuscated_p = f"{proto_parts[0]}://{proto_parts[1].split('//')[-1]}:****@{host_port}"
            meta["proxy_masked"] = obfuscated_p
            meta_list.append(meta)
            
    # Sort metadata by status (active first) then latency
    meta_list.sort(key=lambda x: (x.get("status") != "active", x.get("latency", 9.9)))

    return {
        "raw_count": len(raw_list),
        "active_count": len(active_list),
        "dead_count": len(dead_list),
        "proxies": meta_list
    }

# ── Elegant HTML Dashboard ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ticket Proxy Rotator & Health Checker</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-gradient: radial-gradient(circle at top left, #0e1118, #05070a);
                --card-bg: rgba(17, 24, 39, 0.7);
                --card-border: rgba(255, 255, 255, 0.08);
                --emerald-glow: 0 0 20px rgba(16, 185, 129, 0.25);
                --red-glow: 0 0 20px rgba(239, 68, 68, 0.25);
                --cyan-glow: 0 0 20px rgba(6, 182, 212, 0.25);
            }
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }
            body {
                font-family: 'Outfit', sans-serif;
                background: var(--bg-gradient);
                color: #e2e8f0;
                min-height: 100vh;
                padding: 2rem 1.5rem;
                overflow-x: hidden;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2.5rem;
                flex-wrap: wrap;
                gap: 1rem;
            }
            .logo-section h1 {
                font-size: 2.25rem;
                font-weight: 800;
                background: linear-gradient(135deg, #10b981 0%, #06b6d4 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: -0.025em;
            }
            .logo-section p {
                color: #64748b;
                font-size: 0.875rem;
                margin-top: 0.25rem;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2.5rem;
            }
            .stat-card {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 20px;
                padding: 1.75rem;
                position: relative;
                overflow: hidden;
                backdrop-filter: blur(12px);
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            .stat-card:hover {
                transform: translateY(-2px);
            }
            .stat-card.active { box-shadow: var(--emerald-glow); border-color: rgba(16, 185, 129, 0.2); }
            .stat-card.dead { box-shadow: var(--red-glow); border-color: rgba(239, 68, 68, 0.2); }
            .stat-card.total { box-shadow: var(--cyan-glow); border-color: rgba(6, 182, 212, 0.2); }
            
            .stat-title {
                color: #94a3b8;
                font-size: 0.875rem;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .stat-value {
                font-size: 3rem;
                font-weight: 800;
                margin-top: 0.5rem;
                line-height: 1;
            }
            .stat-card.active .stat-value { color: #10b981; }
            .stat-card.dead .stat-value { color: #ef4444; }
            .stat-card.total .stat-value { color: #06b6d4; }
            
            .stat-badge {
                position: absolute;
                top: 1.75rem;
                right: 1.75rem;
                width: 10px;
                height: 10px;
                border-radius: 50%;
            }
            .stat-card.active .stat-badge { background-color: #10b981; box-shadow: 0 0 10px #10b981; }
            .stat-card.dead .stat-badge { background-color: #ef4444; box-shadow: 0 0 10px #ef4444; }
            .stat-card.total .stat-badge { background-color: #06b6d4; box-shadow: 0 0 10px #06b6d4; }

            .main-content {
                display: grid;
                grid-template-columns: 1fr;
                gap: 2rem;
            }
            @media (min-width: 1024px) {
                .main-content {
                    grid-template-columns: 350px 1fr;
                }
            }

            .panel {
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: 24px;
                padding: 2rem;
                backdrop-filter: blur(12px);
            }
            .panel-title {
                font-size: 1.25rem;
                font-weight: 700;
                margin-bottom: 1.5rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            
            textarea {
                width: 100%;
                height: 180px;
                background: rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                color: #f8fafc;
                font-family: 'JetBrains Mono', monospace;
                padding: 1rem;
                font-size: 0.85rem;
                resize: none;
                margin-bottom: 1rem;
                outline: none;
                transition: border-color 0.2s;
            }
            textarea:focus {
                border-color: #10b981;
            }
            
            .btn {
                width: 100%;
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 0.85rem;
                font-weight: 600;
                font-size: 0.95rem;
                cursor: pointer;
                transition: opacity 0.2s, transform 0.1s;
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 0.5rem;
            }
            .btn:hover { opacity: 0.95; }
            .btn:active { transform: scale(0.98); }
            
            .sessions-input-group {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 1rem;
            }
            .sessions-input-group label {
                font-size: 0.85rem;
                color: #94a3b8;
                white-space: nowrap;
            }
            .sessions-input-group input {
                flex: 1;
                background: rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: white;
                padding: 0.4rem 0.75rem;
                font-size: 0.9rem;
                outline: none;
            }
            
            .table-container {
                overflow-x: auto;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                text-align: left;
                font-size: 0.9rem;
            }
            th {
                color: #64748b;
                font-weight: 600;
                padding: 1rem;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            td {
                padding: 1rem;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
                vertical-align: middle;
            }
            tr:hover td {
                background: rgba(255, 255, 255, 0.02);
            }
            
            .proxy-code {
                font-family: 'JetBrains Mono', monospace;
                color: #38bdf8;
                font-size: 0.8rem;
            }
            .badge-active {
                background: rgba(16, 185, 129, 0.15);
                color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.2);
                padding: 0.25rem 0.6rem;
                border-radius: 9999px;
                font-size: 0.75rem;
                font-weight: 600;
            }
            .badge-dead {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                border: 1px solid rgba(239, 68, 68, 0.2);
                padding: 0.25rem 0.6rem;
                border-radius: 9999px;
                font-size: 0.75rem;
                font-weight: 600;
            }
            
            .latency-fast { color: #10b981; font-weight: 600; }
            .latency-medium { color: #f59e0b; font-weight: 600; }
            .latency-slow { color: #ef4444; font-weight: 600; }
            
            .flag-icon {
                margin-right: 0.4rem;
                font-size: 1.1rem;
                vertical-align: middle;
            }
            
            .text-muted { color: #64748b; font-size: 0.75rem; }
            .error-log {
                color: #f87171;
                font-size: 0.75rem;
                font-family: 'JetBrains Mono', monospace;
                max-width: 250px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                cursor: help;
            }
            
            .leased-badge {
                background: rgba(6, 182, 212, 0.15);
                color: #22d3ee;
                border: 1px solid rgba(6, 182, 212, 0.2);
                padding: 0.15rem 0.4rem;
                border-radius: 4px;
                font-size: 0.7rem;
                font-family: 'JetBrains Mono', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="logo-section">
                    <h1>🇹🇭 Ticket Proxy Rotator & Health Checker</h1>
                    <p>Production-Grade Residential & ISP Proxy Manager for Ticket Platform</p>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span id="checking-indicator" class="badge-active" style="display:none; animation: pulse 1.5s infinite;">⚡ checking...</span>
                    <button class="btn" style="padding: 0.5rem 1rem; width: auto; font-size: 0.85rem;" onclick="loadStats()">🔄 Refresh</button>
                </div>
            </header>

            <div class="stats-grid">
                <div class="stat-card active">
                    <div class="stat-badge"></div>
                    <div class="stat-title">Active Proxies (TH ISP)</div>
                    <div class="stat-value" id="count-active">0</div>
                </div>
                <div class="stat-card dead">
                    <div class="stat-badge"></div>
                    <div class="stat-title">Dead / Filtered</div>
                    <div class="stat-value" id="count-dead">0</div>
                </div>
                <div class="stat-card total">
                    <div class="stat-badge"></div>
                    <div class="stat-title">Total Pool</div>
                    <div class="stat-value" id="count-total">0</div>
                </div>
            </div>

            <div class="main-content">
                <!-- Left panel: Upload -->
                <div class="panel">
                    <div class="panel-title">📥 Upload Proxies</div>
                    <p style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 1.25rem; line-height: 1.5;">
                        Paste proxies (one per line). Format: <br>
                        <code>http://user:pass@host:port</code><br><br>
                        For rotating residential gateways, use <code>{session}</code> in the username to auto-generate multiple sessions:<br>
                        <code>http://user-session-{session}:pass@gate.oxylabs.io:8000</code>
                    </p>
                    <textarea id="proxies-input" placeholder="http://user:pass@1.1.1.1:8000&#10;http://user-session-{session}:pass@gate.soax.com:9000"></textarea>
                    
                    <div class="sessions-input-group">
                        <label for="session-count">Session Pool Size:</label>
                        <input type="number" id="session-count" value="40" min="1" max="200">
                    </div>

                    <button class="btn" onclick="uploadProxies()">
                        💾 Save & Start Health Checks
                    </button>
                </div>

                <!-- Right panel: Table status -->
                <div class="panel" style="padding: 1.5rem;">
                    <div class="panel-title">🔍 Proxy Pool Monitor</div>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Proxy (Obfuscated)</th>
                                    <th>Status</th>
                                    <th>Exit IP</th>
                                    <th>ISP / Organization</th>
                                    <th>Latency</th>
                                    <th>Lease</th>
                                    <th>Last Check</th>
                                </tr>
                            </thead>
                            <tbody id="proxy-rows">
                                <tr>
                                    <td colspan="7" style="text-align: center; color: #64748b; padding: 3rem;">
                                        Loading proxy pool metadata...
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <script>
            async function loadStats() {
                document.getElementById('checking-indicator').style.display = 'inline-block';
                try {
                    const res = await fetch('/api/proxies/status');
                    const data = await res.json();
                    
                    document.getElementById('count-active').innerText = data.active_count;
                    document.getElementById('count-dead').innerText = data.dead_count;
                    document.getElementById('count-total').innerText = data.raw_count;
                    
                    const rowsContainer = document.getElementById('proxy-rows');
                    rowsContainer.innerHTML = '';
                    
                    if (data.proxies.length === 0) {
                        rowsContainer.innerHTML = `
                            <tr>
                                <td colspan="7" style="text-align: center; color: #64748b; padding: 3rem;">
                                    No proxies in pool. Paste some on the left.
                                </td>
                            </tr>
                        `;
                        return;
                    }
                    
                    data.proxies.forEach(meta => {
                        const row = document.createElement('tr');
                        
                        // Status badge
                        const statusBadge = meta.status === 'active' 
                            ? '<span class="badge-active">ACTIVE</span>' 
                            : '<span class="badge-dead">DEAD</span>';
                            
                        // Latency class
                        let latClass = 'latency-fast';
                        if (meta.latency >= 2.5) latClass = 'latency-slow';
                        else if (meta.latency >= 1.0) latClass = 'latency-medium';
                        
                        const latencyHtml = meta.status === 'active'
                            ? `<span class="${latClass}">${meta.latency}s</span>`
                            : `<span class="text-muted">—</span>`;
                            
                        // Error title if any
                        const errorHtml = meta.error 
                            ? `<div class="error-log" title="${meta.error.replace(/"/g, '&quot;')}">⚠ ${meta.error}</div>`
                            : '';
                            
                        // Country code Flag
                        const flag = meta.countryCode !== 'Unknown' 
                            ? `<span class="flag-icon">${meta.countryCode === 'TH' ? '🇹🇭' : '🌐'}</span>`
                            : '';
                            
                        // Lease details
                        const leaseHtml = meta.leased_to 
                            ? `<span class="leased-badge">${meta.leased_to}</span>`
                            : `<span class="text-muted">—</span>`;

                        row.innerHTML = `
                            <td>
                                <span class="proxy-code">${meta.proxy_masked}</span>
                                ${errorHtml}
                            </td>
                            <td>${statusBadge}</td>
                            <td>${flag}${meta.ip}</td>
                            <td>
                                <div style="font-weight:500;">${meta.isp}</div>
                                <div class="text-muted" style="font-size:0.7rem;">${meta.org}</div>
                            </td>
                            <td>${latencyHtml}</td>
                            <td>${leaseHtml}</td>
                            <td class="text-muted" style="font-family:'JetBrains Mono';">${meta.last_checked.split(' ')[1]}</td>
                        `;
                        rowsContainer.appendChild(row);
                    });
                } catch (e) {
                    console.error("Failed to load proxy statistics", e);
                } finally {
                    setTimeout(() => {
                        document.getElementById('checking-indicator').style.display = 'none';
                    }, 500);
                }
            }

            async function uploadProxies() {
                const text = document.getElementById('proxies-input').value;
                const countVal = parseInt(document.getElementById('session-count').value) || 40;
                
                const list = text.split('\\n')
                    .map(line => line.trim())
                    .filter(line => line && !line.startsWith('#'));
                    
                if (list.length === 0) {
                    alert("Please enter at least one valid proxy URL");
                    return;
                }
                
                try {
                    const res = await fetch('/api/proxies/upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ proxies: list, session_count: countVal })
                    });
                    
                    if (res.ok) {
                        alert("Proxies uploaded successfully! Starting background health check.");
                        document.getElementById('proxies-input').value = '';
                        loadStats();
                    } else {
                        const err = await res.text();
                        alert("Upload failed: " + err);
                    }
                } catch (e) {
                    alert("Failed to connect to proxy rotator API: " + e);
                }
            }

            // Load stats immediately and then refresh every 10 seconds
            loadStats();
            setInterval(loadStats, 10000);
        </script>
    </body>
    </html>
    """
    return html_content
