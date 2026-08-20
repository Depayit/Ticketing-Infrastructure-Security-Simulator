# Ticketing Infrastructure Security Simulator

A distributed security research platform designed to study large-scale ticketing systems, queue protection mechanisms, fraud detection controls, and automation-driven attacks in a controlled environment.

---

## Overview

Modern ticketing platforms face increasing challenges from automated purchasing systems, proxy networks, session farming, and large-scale bot operations.

This project provides a comprehensive research environment for analyzing both offensive automation techniques and defensive security controls commonly found in high-demand ticketing infrastructures (such as ThaiTicketMajor, Queue-it, and Akamai Bot Manager).

The platform features a dual-architecture design:
1. **Defensive Security Stack**: Multi-layer defense simulation including rate limiting, virtual waiting rooms, AI behavioral anomaly detection, and 3D-Secure 2.0 payment verification.
2. **Offensive Automation Engine**: Multi-worker orchestrator simulating stealth headless browser automation, session management, and proxy rotation.

---

## Key Features

### 🛡️ Multi-Layer Defense Simulation
* **Layer 1: Edge & Rate Limiting**: IP-based rate limiting, proxy reputation checks, and header validation via Gateway (`:8090`).
* **Layer 2: Virtual Waiting Room**: Priority queue simulation (`:8091`) with token validation and configurable countdown modes (`?demo=1`).
* **Layer 3: AI Behavioral Telemetry**: Real-time mouse movement, click cadence, and timing anomaly detection powered by an `IsolationForest` ML Engine (`:8094`).
* **Layer 4: 3D-Secure 2.0 Payment Gateway**: Simulated OTP payment verification (`:8093`) with mock OTP (`123456`) and fraud scoring.

### 🤖 Distributed Automation Research
* **Multi-Worker Execution Model**: Distributed workers (`worker/`) coordinated via Redis and FastAPI Manager (`:8080`).
* **Stealth Evasion Mechanics**: Headless browser automation with fingerprint masking (WebGL, Canvas, User-Agent, Navigator overrides).
* **Proxy Rotator Service**: Dynamic proxy pool management and request distribution (`:8001`).
* **Queue-it & CAPTCHA Solver Integration**: Automated session handling and challenge verification flows.

### 📊 Real-Time Monitoring & Dashboards
* **Defense Live Audit Dashboard**: Real-time EventSource/WebSocket stream of blocked requests and fraud scores at `http://localhost:8090/admin`.
* **Offense Control Dashboard**: React + TypeScript frontend (`:5173`) for monitoring active workers, task assignments, and success metrics.
* **Telegram Notification Bot**: Real-time alerts for successful ticket reservations and system events.

### 📚 Interactive Visual Documentation Portal
* Complete offline-ready HTML documentation suite included in `docs-html/` featuring architecture diagrams, defense mechanics, operation guides, case studies, and OSINT reports.

---

## System Architecture

```text
                               +-----------------------------+
                               |  Offense Worker Dashboard   |
                               |    (React + Vite :5173)     |
                               +--------------+--------------+
                                              |
                                              v
                               +-----------------------------+
                               |     Manager Orchestrator    |
                               |       (FastAPI :8080)       |
                               +--------------+--------------+
                                              |
                     +------------------------+------------------------+
                     |                        |                        |
                     v                        v                        v
              +--------------+         +--------------+         +--------------+
              |  Worker #1   |         |  Worker #N   |         | Proxy Rotator|
              |  (Playwright)|         |  (Playwright)|         |   (:8001)    |
              +-------+------+         +-------+------+         +-------+------+
                      |                        |                        |
                      +------------------------+------------------------+
                                              |
                                              v
                               +-----------------------------+
                               |        Redis Cluster        |
                               |     (Coordination Hub)      |
                               +--------------+--------------+
                                              |
                                              v
====================================== DEFENSE SIMULATOR ======================================
                                              |
                                              v
                               +-----------------------------+
                               |       Defense Gateway       |
                               |      (FastAPI :8090)        |
                               +--------------+--------------+
                                              |
          +-----------------------------------+-----------------------------------+
          |                                   |                                   |
          v                                   v                                   v
+------------------+                +------------------+                +------------------+
|  Queue Service   |                |   Seat Service   |                | Payment Service  |
|     (:8091)      |                |     (:8092)      |                |     (:8093)      |
+------------------+                +--------+---------+                +--------+---------+
                                             |                                   |
                                             +-----------------+-----------------+
                                                               |
                                                               v
                                                    +--------------------+
                                                    | Fraud Engine (ML)  |
                                                    |  (IsolationForest) |
                                                    |      (:8094)       |
                                                    +--------------------+
```

---

## Service Endpoints & Port Reference

| Service / View | Port / URL | Description & Defense Layers |
| :--- | :--- | :--- |
| **Waiting Room (TTM Target UI)** | `http://localhost:8090/` | Edge WAF + Akamai Sensor + Queue-it Virtual Waiting Room |
| **Demo Mode Countdown** | `http://localhost:8090/?demo=1` | Accelerated ~8s countdown test environment |
| **Interactive Seat Map** | `http://localhost:8090/seats` | AI Behavioral Telemetry & IsolationForest ML Engine |
| **Checkout & 3DS Payment** | `http://localhost:8090/checkout` | 3D-Secure Payment Gateway (Mock OTP: `123456`) |
| **Defense Live Audit Dashboard** | `http://localhost:8090/admin` | Real-time IP/AI/3DS block event stream |
| **Offense Worker Dashboard** | `http://localhost:5173/` | Worker management and ticketing attack orchestration |
| **Manager API & Control Panel** | `http://localhost:8080/` | Central task distribution and system health monitoring |
| **Proxy Rotator Service** | `http://localhost:8001/` | Dynamic proxy pool status and rotation API |

---

## Environment Configuration Reference

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `REDIS_URL` | `redis://redis:6379/0` | Connection string for Redis coordination broker |
| `PROXY_ROTATOR_URL` | `http://proxy-rotator:8080` | URL for proxy pool rotator service |
| `FRAUD_ENGINE_URL` | `http://fraud-engine:8094` | Endpoint for IsolationForest ML fraud scoring |
| `AI_LAYER_ENABLED` | `true` | Toggle AI behavioral anomaly detection engine |
| `THREE_DS_OTP` | `123456` | Mock OTP code for 3D-Secure payment authorization |

---

## Documentation Suite

Detailed interactive guides are provided in the [`docs-html/`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/) directory:

* [`docs-html/index.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/index.html) - Documentation Portal Home
* [`docs-html/architecture.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/architecture.html) - System Architecture & Component Mapping
* [`docs-html/defense.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/defense.html) - Multi-Layer Defense Controls & Telemetry Specification
* [`docs-html/offense.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/offense.html) - Offensive Automation Mechanics & Evasion Design
* [`docs-html/operation-guide.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/operation-guide.html) - Operations & Deployment Guide
* [`docs-html/case-study.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/case-study.html) - High-Demand Concert Ticketing Case Study
* [`docs-html/management.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/management.html) - Manager & Worker Control Reference
* [`docs-html/osint-report.html`](file:///c:/dev/Ticketing-Infrastructure-Security-Simulator/docs-html/osint-report.html) - Threat Intelligence & OSINT Analysis

---

## Quick Start Guide

### 1. Prerequisites
* [Docker](https://www.docker.com/) & Docker Compose
* [Node.js](https://nodejs.org/) (v18+ for local frontend dashboard)
* [Python 3.11+](https://www.python.org/)

### 2. Start Defense & Manager Infrastructure
```bash
# 1. Start Manager, Redis, Proxy Rotator, and Worker pool
docker compose up -d --build

# 2. Start Defense Simulation Stack (Gateway, Queue, Seats, Payment, Fraud Engine)
docker compose -f defense-demo/docker-compose.defense.yml up -d --build
```

### 3. Start Offense Worker Dashboard (Frontend)
```bash
cd frontend
npm install
npm run dev
```
Access the Offense Dashboard at `http://localhost:5173/` and the Defense Admin Panel at `http://localhost:8090/admin`.

---

## Technology Stack

* **Backend Services**: Python 3.11, FastAPI, Uvicorn, GQL, HTTPX, Redis
* **Machine Learning**: Scikit-Learn (IsolationForest), Joblib, NumPy
* **Automation**: Playwright, Chromium, Asyncio, 2Captcha API
* **Frontend**: React, TypeScript, Vite, TailwindCSS, Lucide Icons
* **Infrastructure**: Docker, Docker Compose, Redis Pub/Sub, WebSockets / SSE

---

## Security Research & Educational Disclaimer

This project is intended exclusively for security research, defensive testing, and educational purposes in authorized local environments.

Users are solely responsible for ensuring compliance with applicable laws, regulations, and platform terms of service. Do not run offensive automation tools against third-party production infrastructures without authorization.

---

## Author

**Jacob (Depayit)**  
Cybersecurity Researcher | Security Automation | Distributed Systems | AI Security
