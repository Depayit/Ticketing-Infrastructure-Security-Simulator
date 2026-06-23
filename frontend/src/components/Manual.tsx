import React from 'react';

const Manual: React.FC = () => {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 sm:p-8 max-w-4xl mx-auto text-zinc-300">
      <h1 className="text-2xl font-bold text-white mb-2">คู่มือการใช้งานบอทกดบัตร ThaiTicketMajor 2026 (Production Version)</h1>
      <p className="text-sm text-zinc-500 mb-8">วันที่สร้าง: 24 พฤษภาคม 2026 | เวอร์ชัน: 2.0 (Manager/Worker + Dashboard + GraphQL + Auto CAPTCHA)</p>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">1. คำเตือนสำคัญ</h2>
        <ul className="list-disc pl-5 space-y-2">
          <li>บอทนี้ใช้สำหรับการศึกษาระบบอัตโนมัติและการพัฒนาเท่านั้น</li>
          <li>การใช้บอทอาจผิดเงื่อนไขการใช้งานของ ThaiTicketMajor</li>
          <li>ผู้ใช้งานต้องรับผิดชอบเองทั้งหมด</li>
          <li>ควรใช้ Residential Proxy ไทยคุณภาพสูงเท่านั้น</li>
          <li>แนะนำให้ทดสอบกับ event เล็ก ๆ ก่อน</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">2. ความต้องการของระบบ</h2>
        <ul className="list-disc pl-5 space-y-2">
          <li>Docker + Docker Compose (แนะนำ Docker Swarm สำหรับหลายเครื่อง)</li>
          <li>Python 3.11+</li>
          <li>Redis (สำหรับ coordination ระหว่าง worker)</li>
          <li>2Captcha / CapMonster API Key</li>
          <li>Telegram Bot Token + Chat ID</li>
          <li>Residential Proxy ไทย (ยิ่งมากยิ่งดี อย่างน้อย 20-50 ตัว)</li>
          <li>VPS หลายเครื่อง (แนะนำ 5-20 เครื่อง) สำหรับ production</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">3. โครงสร้างโฟลเดอร์</h2>
        <pre className="bg-zinc-950 p-4 rounded-lg overflow-x-auto text-sm text-emerald-300 border border-zinc-800">
{`TTM-BOT-2026/
├── manager/
│   ├── main.py
│   ├── config.json
│   ├── Dockerfile
│   └── static/                  ← ไฟล์ React ที่ build แล้ว
├── worker/
│   ├── bot.py
│   ├── config.json
│   └── Dockerfile
├── frontend/                     ← โฟลเดอร์พัฒนา React (TypeScript)
├── docker-compose.yml
├── ansible-deploy.yml
├── README.md
└── redis.conf`}
        </pre>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">4. การติดตั้ง (Step by Step)</h2>
        <div className="space-y-6">
          <div>
            <h3 className="text-lg font-medium text-white mb-2">ขั้นตอนที่ 1: ติดตั้งบนเครื่อง Manager</h3>
            <ol className="list-decimal pl-5 space-y-2">
              <li>สร้างโฟลเดอร์โปรเจกต์และคัดลอกไฟล์ทั้งหมดตามโครงสร้าง</li>
              <li>เข้าไปที่โฟลเดอร์ <code>frontend</code> แล้วรัน:<br/>
                <code className="bg-zinc-950 px-2 py-1 rounded text-emerald-300 mt-1 inline-block">npm install && npm run build</code>
              </li>
              <li>คัดลอกโฟลเดอร์ <code>dist/</code> ไปวางที่ <code>manager/static/</code></li>
            </ol>
          </div>
          <div>
            <h3 className="text-lg font-medium text-white mb-2">ขั้นตอนที่ 2: ตั้งค่า config</h3>
            <p className="mb-2 font-medium">worker/config.json</p>
            <pre className="bg-zinc-950 p-4 rounded-lg overflow-x-auto text-sm text-emerald-300 border border-zinc-800 mb-4">
{`{
  "event_id": "ttm-bkk-blackpink-world-tour-2026",
  "telegram_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID",
  "captcha_key": "YOUR_2CAPTCHA_KEY",
  "redis_url": "redis://redis:6379/0",
  "proxies": ["http://user:pass@proxy1:8000", "http://user:pass@proxy2:8000"],
  "profiles": [
    {
      "fullname": "ชื่อ นามสกุล",
      "email": "email@gmail.com",
      "phone": "0812345678",
      "id_card": "1234567890123",
      "card": {"number": "4111111111111111", "exp": "1228", "cvv": "123"}
    }
  ],
  "ticket_priorities": ["VIP", "GA", "Standing"]
}`}
            </pre>
            <p className="mb-2 font-medium">manager/config.json (ส่วนใหญ่ใช้ Redis เป็นหลัก)</p>
          </div>
          <div>
            <h3 className="text-lg font-medium text-white mb-2">ขั้นตอนที่ 3: รันด้วย Docker</h3>
            <pre className="bg-zinc-950 p-4 rounded-lg overflow-x-auto text-sm text-emerald-300 border border-zinc-800">
{`cd TTM-BOT-2026
docker compose up -d --build

# หรือใช้ Swarm:
docker stack deploy -c docker-compose.yml ttm-bot`}
            </pre>
          </div>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">5. การใช้งาน</h2>
        <div className="space-y-4">
          <div>
            <h3 className="font-medium text-white">ผ่าน Dashboard:</h3>
            <ul className="list-disc pl-5 space-y-1">
              <li>เปิดเบราว์เซอร์เข้า <code>http://YOUR_MANAGER_IP:8080</code></li>
              <li>กดปุ่ม "START ALL WORKERS" เพื่อเริ่มบอททุกเครื่อง</li>
              <li>กด "STOP ALL WORKERS" เพื่อหยุดทันที</li>
              <li>สามารถดู Log แบบเรียลไทม์ได้</li>
            </ul>
          </div>
          <div>
            <h3 className="font-medium text-white">ผ่าน Telegram:</h3>
            <ul className="list-disc pl-5 space-y-1">
              <li>เมื่อมี worker สำเร็จจะแจ้งเตือนอัตโนมัติ</li>
              <li>สามารถใช้คำสั่ง <code>/start</code> และ <code>/stop</code> ผ่าน Central Controller (ถ้าเปิดใช้งาน)</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">6. คำแนะนำสำคัญ (Best Practices)</h2>
        <ol className="list-decimal pl-5 space-y-2">
          <li>ใช้ Residential Proxy ไทยคุณภาพสูงเท่านั้น (หมุนทุก 5-15 วินาที)</li>
          <li>ควรมี Proxy อย่างน้อย 1 ตัวต่อ 1-2 worker</li>
          <li>ใช้ Profile + Card หมุนเวียน (ยิ่งมากยิ่งดี)</li>
          <li>เปิดบอทก่อนเวลาเปิดขายประมาณ 30-60 วินาที</li>
          <li>ใช้หลาย VPS (กระจายไปหลาย Provider และหลายประเทศ)</li>
          <li>Monitor Dashboard + Telegram อย่างใกล้ชิด</li>
          <li>GraphQL Endpoint อาจเปลี่ยนทุก event ใหญ่ ควร capture ใหม่ก่อนวันขาย</li>
          <li>Queue-it + Turnstile CAPTCHA เป็นจุดสำคัญที่สุด — ต้องมี Solver ที่เร็ว</li>
          <li>อย่าใช้ Datacenter Proxy จะถูกบล็อกทันที</li>
          <li>เมื่อมี worker สำเร็จ ระบบจะหยุดทุกเครื่องอัตโนมัติผ่าน Redis</li>
        </ol>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">7. การแก้ปัญหา (Troubleshooting)</h2>
        <ul className="list-disc pl-5 space-y-2">
          <li><span className="text-white font-medium">Error "Connection refused"</span> → เช็ค Redis และ Proxy</li>
          <li><span className="text-white font-medium">CAPTCHA ไม่แก้</span> → ตรวจสอบ API Key ของ 2Captcha</li>
          <li><span className="text-white font-medium">Worker ไม่ขึ้นใน Dashboard</span> → เช็ค Redis connection</li>
          <li><span className="text-white font-medium">ถูก Block</span> → เปลี่ยน Proxy + Profile ชุดใหม่</li>
          <li><span className="text-white font-medium">Queue ไม่ผ่าน</span> → เพิ่มเวลา poll หรือปรับ solver</li>
        </ul>
      </section>

      <section className="mb-8">
        <h2 className="text-xl font-semibold text-emerald-400 mb-4 border-b border-zinc-800 pb-2">8. การอัปเดต & คำแนะนำเพิ่มเติม</h2>
        <ul className="list-disc pl-5 space-y-2">
          <li>Endpoint และ Mutation ของ ThaiTicketMajor เปลี่ยนบ่อย</li>
          <li>ควร capture GraphQL จาก Chrome DevTools ทุกครั้งก่อน event ใหญ่</li>
          <li>อัปเดต User-Agent และ Header ให้ตรงกับปี 2026</li>
          <li>รันบนเครื่องที่มีความเร็วอินเทอร์เน็ตสูงและ latency ต่ำ</li>
          <li>ใช้ tmux หรือ Docker Swarm สำหรับความเสถียร</li>
          <li>เก็บ log ทุกครั้งที่รัน</li>
          <li>ทดสอบระบบหลายครั้งก่อน event จริง</li>
        </ul>
      </section>

      <div className="mt-12 text-center text-sm text-zinc-500 border-t border-zinc-800 pt-8">
        <p>พัฒนาเพื่อการศึกษาและทดสอบระบบอัตโนมัติ | ใช้งานด้วยความระมัดระวัง</p>
        <p className="mt-1">พัฒนาโดย Jacob Nuttapong | เวอร์ชัน: 2026.05 Production Grade</p>
      </div>
    </div>
  );
};

export default Manual;
