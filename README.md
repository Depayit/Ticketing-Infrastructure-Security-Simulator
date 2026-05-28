# TTM 2026 Concert Ticket Bot
บอทกดบัตรคอนเสิร์ต ThaiTicketMajor ปี 2026 เวอร์ชัน Production
**เทคโนโลยีหลัก**: GraphQL + Queue-it Bypass + Auto CAPTCHA Solver (2Captcha) + Docker Swarm + FastAPI Dashboard + TypeScript React
---
## คุณสมบัติ
- ใช้ **GraphQL API** โดยตรง (เร็วและมีประสิทธิภาพสูง)
- รองรับ **Queue-it Bypass** + Auto Solve Turnstile CAPTCHA
- มี **Manager/Worker Architecture** แยกชัดเจน
- Dashboard แบบ Real-time (React + TypeScript + Tailwind)
- Auto Stop เมื่อมีเครื่องใดเครื่องหนึ่งซื้อสำเร็จ (ผ่าน Redis)
- Telegram Notification ทันทีเมื่อได้บัตร
- บันทึก Order ลง Database
- รองรับการรันหลายสิบถึงหลายร้อย instances พร้อมกัน
- Deploy ด้วย Docker Swarm + Ansible
---
## Tech Stack
- **Backend**: Python 3.11, FastAPI, gql, httpx, Redis
- **Frontend**: React + TypeScript + TailwindCSS + Vite
- **Infrastructure**: Docker, Docker Swarm, Redis
- **CAPTCHA Solver**: 2Captcha (รองรับ Turnstile)
- **Notification**: Telegram Bot
---
## โครงสร้างโปรเจกต์
TTM-BOT-2026/ ├── manager/ # Dashboard + Control Panel ├── worker/ # บอทหลัก (GraphQL Bot) ├── frontend/ # โค้ด React TypeScript ├── docker-compose.yml ├── ansible-deploy.yml ├── README.md └── MANUAL.txt # คู่มือการใช้งานฉบับละเอียด



---
## การติดตั้งด่วน (Quick Start)
1. Clone โปรเจกต์
2. แก้ไขไฟล์ `config.json` ในโฟลเดอร์ `worker/` และ `manager/`
3. รันคำสั่ง:
   ```bash
   docker compose up -d --build
เข้าใช้งาน Dashboard ได้ที่ http://your-ip:8080
ดูรายละเอียดการติดตั้งและการใช้งานแบบละเอียดได้ที่ไฟล์ MANUAL.txt

คำเตือน
บอทนี้มีไว้เพื่อการศึกษาและทดสอบทางเทคนิคเท่านั้น
การใช้บอทอาจผิดเงื่อนไขการใช้งานของ ThaiTicketMajor
ผู้ใช้ต้องรับผิดชอบเองทั้งหมด
