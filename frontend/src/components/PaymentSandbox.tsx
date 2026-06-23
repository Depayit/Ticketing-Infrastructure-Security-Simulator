import { useState } from 'react';

type PaymentMethod = 'promptpay' | 'credit' | null;
type Step = 'select' | 'promptpay-qr' | 'credit-form' | 'success';

// SVG Icons as components
const QrIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="4" y="4" width="16" height="16" rx="2" stroke="#1e40af" strokeWidth="2.5" fill="#dbeafe" />
    <rect x="8" y="8" width="8" height="8" rx="1" fill="#1e40af" />
    <rect x="28" y="4" width="16" height="16" rx="2" stroke="#1e40af" strokeWidth="2.5" fill="#dbeafe" />
    <rect x="32" y="8" width="8" height="8" rx="1" fill="#1e40af" />
    <rect x="4" y="28" width="16" height="16" rx="2" stroke="#1e40af" strokeWidth="2.5" fill="#dbeafe" />
    <rect x="8" y="32" width="8" height="8" rx="1" fill="#1e40af" />
    <rect x="28" y="28" width="4" height="4" fill="#1e40af" />
    <rect x="34" y="28" width="4" height="4" fill="#1e40af" />
    <rect x="40" y="28" width="4" height="4" fill="#1e40af" />
    <rect x="28" y="34" width="4" height="4" fill="#1e40af" />
    <rect x="36" y="36" width="8" height="8" rx="1" fill="#1e40af" />
    <rect x="28" y="40" width="4" height="4" fill="#1e40af" />
  </svg>
);

const CreditCardIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="4" y="10" width="40" height="28" rx="4" fill="#1e40af" />
    <rect x="4" y="10" width="40" height="28" rx="4" stroke="#1e3a8a" strokeWidth="1" />
    <rect x="4" y="18" width="40" height="6" fill="#1e3a8a" />
    <rect x="8" y="28" width="14" height="4" rx="1" fill="#93c5fd" />
    <rect x="8" y="34" width="8" height="2" rx="1" fill="#60a5fa" />
    <circle cx="36" cy="31" r="4" fill="#f59e0b" opacity="0.8" />
    <circle cx="32" cy="31" r="4" fill="#ef4444" opacity="0.8" />
  </svg>
);

const PromptPayLogo = () => (
  <svg width="120" height="40" viewBox="0 0 120 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="120" height="40" rx="8" fill="#003b71" />
    <text x="60" y="17" textAnchor="middle" fill="white" fontSize="10" fontWeight="bold" fontFamily="Arial">PromptPay</text>
    <text x="60" y="30" textAnchor="middle" fill="#7dd3fc" fontSize="8" fontFamily="Arial">พร้อมเพย์</text>
  </svg>
);

const CheckIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="32" cy="32" r="30" fill="#10b981" />
    <path d="M20 32L28 40L44 24" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const TicketIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="4" y="8" width="32" height="24" rx="3" fill="#fbbf24" stroke="#f59e0b" strokeWidth="1.5" />
    <line x1="14" y1="8" x2="14" y2="32" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 2" />
    <rect x="18" y="14" width="14" height="2" rx="1" fill="#92400e" />
    <rect x="18" y="19" width="10" height="2" rx="1" fill="#b45309" />
    <rect x="18" y="24" width="12" height="2" rx="1" fill="#b45309" />
    <rect x="7" y="16" width="4" height="8" rx="1" fill="#92400e" />
  </svg>
);

// Fake QR Code SVG
const FakeQRCode = () => (
  <svg width="200" height="200" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Background */}
    <rect width="200" height="200" fill="white" rx="8" />
    
    {/* Top-left position marker */}
    <rect x="12" y="12" width="42" height="42" fill="black" />
    <rect x="16" y="16" width="34" height="34" fill="white" />
    <rect x="22" y="22" width="22" height="22" fill="black" />
    
    {/* Top-right position marker */}
    <rect x="146" y="12" width="42" height="42" fill="black" />
    <rect x="150" y="16" width="34" height="34" fill="white" />
    <rect x="156" y="22" width="22" height="22" fill="black" />
    
    {/* Bottom-left position marker */}
    <rect x="12" y="146" width="42" height="42" fill="black" />
    <rect x="16" y="150" width="34" height="34" fill="white" />
    <rect x="22" y="156" width="22" height="22" fill="black" />
    
    {/* Data modules - random pattern */}
    {[
      [60,12],[66,12],[78,12],[84,12],[96,12],[108,12],[120,12],[132,12],
      [60,18],[72,18],[84,18],[102,18],[114,18],[126,18],[138,18],
      [60,24],[66,24],[78,24],[90,24],[96,24],[108,24],[132,24],
      [60,30],[72,30],[84,30],[96,30],[114,30],[120,30],[138,30],
      [60,36],[66,36],[78,36],[90,36],[102,36],[126,36],[132,36],
      [60,42],[72,42],[84,42],[96,42],[108,42],[120,42],[138,42],
      [60,48],[66,48],[78,48],[90,48],[102,48],[114,48],[132,48],
      [12,60],[18,60],[30,60],[42,60],[60,60],[72,60],[84,60],[96,60],[108,60],[120,60],[138,60],[150,60],[162,60],[174,60],
      [12,66],[24,66],[36,66],[48,66],[66,66],[78,66],[90,66],[102,66],[114,66],[132,66],[144,66],[156,66],[168,66],
      [12,72],[18,72],[30,72],[42,72],[60,72],[72,72],[84,72],[96,72],[108,72],[120,72],[138,72],[150,72],[162,72],[174,72],
      [12,78],[24,78],[36,78],[48,78],[66,78],[78,78],[90,78],[102,78],[120,78],[132,78],[144,78],[162,78],[174,78],
      [12,84],[18,84],[30,84],[42,84],[60,84],[72,84],[84,84],[96,84],[108,84],[126,84],[138,84],[150,84],[168,84],
      [12,90],[24,90],[36,90],[48,90],[66,90],[78,90],[90,90],[102,90],[114,90],[132,90],[144,90],[156,90],[174,90],
      [12,96],[18,96],[30,96],[42,96],[60,96],[72,96],[84,96],[96,96],[108,96],[120,96],[138,96],[150,96],[162,96],[174,96],
      [12,102],[24,102],[36,102],[48,102],[66,102],[78,102],[90,102],[108,102],[120,102],[132,102],[150,102],[162,102],
      [12,108],[18,108],[30,108],[42,108],[60,108],[72,108],[84,108],[96,108],[114,108],[126,108],[138,108],[156,108],[174,108],
      [12,114],[24,114],[42,114],[60,114],[78,114],[90,114],[102,114],[114,114],[132,114],[144,114],[162,114],[174,114],
      [12,120],[18,120],[30,120],[48,120],[66,120],[72,120],[84,120],[96,120],[108,120],[120,120],[138,120],[150,120],[168,120],
      [12,126],[24,126],[36,126],[42,126],[60,126],[78,126],[90,126],[102,126],[114,126],[132,126],[144,126],[156,126],[174,126],
      [12,132],[18,132],[30,132],[48,132],[66,132],[72,132],[84,132],[96,132],[108,132],[126,132],[138,132],[150,132],[162,132],[174,132],
      [12,138],[24,138],[36,138],[42,138],[60,138],[78,138],[90,138],[102,138],[120,138],[132,138],[144,138],[162,138],[174,138],
      [60,144],[66,144],[78,144],[90,144],[102,144],[114,144],[132,144],[150,144],[162,144],
      [60,150],[72,150],[84,150],[96,150],[108,150],[120,150],[138,150],[144,150],[168,150],
      [60,156],[66,156],[78,156],[90,156],[102,156],[114,156],[132,156],[150,156],[162,156],[174,156],
      [60,162],[72,162],[84,162],[96,162],[108,162],[126,162],[138,162],[144,162],[156,162],[168,162],
      [60,168],[66,168],[78,168],[90,168],[102,168],[114,168],[132,168],[150,168],[162,168],[174,168],
      [60,174],[72,174],[84,174],[96,174],[108,174],[120,174],[138,174],[144,174],[162,174],
      [60,180],[66,180],[78,180],[90,180],[114,180],[126,180],[132,180],[150,180],[168,180],[174,180],
    ].map(([x, y], i) => (
      <rect key={i} x={x} y={y} width="6" height="6" fill="black" />
    ))}
    
    {/* PromptPay logo in center */}
    <rect x="72" y="72" width="56" height="56" rx="6" fill="white" />
    <rect x="76" y="76" width="48" height="48" rx="4" fill="#003b71" />
    <text x="100" y="98" textAnchor="middle" fill="white" fontSize="9" fontWeight="bold" fontFamily="Arial">PP</text>
    <text x="100" y="112" textAnchor="middle" fill="#7dd3fc" fontSize="7" fontFamily="Arial">พร้อมเพย์</text>
  </svg>
);

export default function PaymentSandbox() {
  const [selectedPayment, setSelectedPayment] = useState<PaymentMethod>(null);
  const [step, setStep] = useState<Step>('select');
  const [showSummary, setShowSummary] = useState(true);
  const [countdown, setCountdown] = useState(300); // 5 minutes
  const [isProcessing, setIsProcessing] = useState(false);
  
  // Credit card form state
  const [cardNumber, setCardNumber] = useState('');
  const [cardName, setCardName] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvv, setCvv] = useState('');

  // Booking data mockup
  const booking = {
    event: 'LMSY BE MY ROMANCE FAN CON PRESENTED BY หมึกกรุบ',
    venue: 'ICONSIAM HALL, 7th floor ICONSIAM',
    showtime: 'Sat 06 Jun 2026 15:00',
    zone: 'A4',
    seat: 'F-61',
    quantity: 1,
    price: 5000,
    serviceFee: 180,
    ticketProtect: 350,
    total: 5530,
  };

  // Format card number with spaces
  const formatCardNumber = (val: string) => {
    const cleaned = val.replace(/\D/g, '').slice(0, 16);
    return cleaned.replace(/(.{4})/g, '$1 ').trim();
  };

  // Format expiry MM/YY
  const formatExpiry = (val: string) => {
    const cleaned = val.replace(/\D/g, '').slice(0, 4);
    if (cleaned.length > 2) return cleaned.slice(0, 2) + '/' + cleaned.slice(2);
    return cleaned;
  };

  const handleConfirm = () => {
    if (selectedPayment === 'promptpay') {
      setStep('promptpay-qr');
      // Start countdown
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } else if (selectedPayment === 'credit') {
      setStep('credit-form');
    }
  };

  const handleCreditSubmit = () => {
    setIsProcessing(true);
    setTimeout(() => {
      setIsProcessing(false);
      setStep('success');
    }, 2500);
  };

  const handleQrConfirmPaid = () => {
    setIsProcessing(true);
    setTimeout(() => {
      setIsProcessing(false);
      setStep('success');
    }, 2000);
  };

  const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const resetAll = () => {
    setStep('select');
    setSelectedPayment(null);
    setCountdown(300);
    setCardNumber('');
    setCardName('');
    setExpiry('');
    setCvv('');
    setIsProcessing(false);
  };

  // ─── Success Screen ───
  if (step === 'success') {
    return (
      <div className="max-w-lg mx-auto animate-fade-in">
        <style>{`
          @keyframes fade-in { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
          @keyframes scale-in { from { transform: scale(0.5); opacity: 0; } to { transform: scale(1); opacity: 1; } }
          @keyframes confetti { 0% { transform: translateY(0) rotate(0deg); opacity: 1; } 100% { transform: translateY(-100px) rotate(720deg); opacity: 0; } }
          .animate-fade-in { animation: fade-in 0.5s ease-out; }
          .animate-scale-in { animation: scale-in 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        `}</style>
        <div className="bg-white rounded-2xl shadow-xl border border-zinc-100 p-8 text-center">
          <div className="animate-scale-in mb-6 flex justify-center">
            <CheckIcon />
          </div>
          <h2 className="text-2xl font-bold text-zinc-900 mb-2">ชำระเงินสำเร็จ! 🎉</h2>
          <p className="text-zinc-500 mb-6">ระบบได้รับการชำระเงินของคุณเรียบร้อยแล้ว</p>
          
          <div className="bg-emerald-50 rounded-xl p-5 mb-6 text-left border border-emerald-100">
            <div className="flex justify-between mb-2">
              <span className="text-zinc-500 text-sm">หมายเลขคำสั่งซื้อ</span>
              <span className="font-mono font-semibold text-zinc-800 text-sm">TKT-20260603-8821</span>
            </div>
            <div className="flex justify-between mb-2">
              <span className="text-zinc-500 text-sm">จำนวนเงิน</span>
              <span className="font-semibold text-emerald-600 text-sm">฿{booking.total.toLocaleString()}.00</span>
            </div>
            <div className="flex justify-between mb-2">
              <span className="text-zinc-500 text-sm">วิธีชำระเงิน</span>
              <span className="font-semibold text-zinc-800 text-sm">
                {selectedPayment === 'promptpay' ? 'QR PromptPay' : 'บัตรเครดิต/เดบิต'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500 text-sm">สถานะ</span>
              <span className="text-emerald-600 font-semibold text-sm flex items-center gap-1">
                <span className="w-2 h-2 bg-emerald-500 rounded-full inline-block"></span>
                สำเร็จ
              </span>
            </div>
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6">
            <p className="text-amber-800 text-sm font-medium">📧 E-Ticket จะถูกส่งไปที่อีเมลของคุณภายใน 15 นาที</p>
          </div>
          
          <button
            onClick={resetAll}
            className="w-full py-3.5 bg-zinc-900 text-white rounded-xl font-semibold text-base hover:bg-zinc-800 transition-all active:scale-[0.98]"
          >
            กลับหน้าหลัก
          </button>
        </div>
      </div>
    );
  }

  // ─── PromptPay QR Screen ───
  if (step === 'promptpay-qr') {
    return (
      <div className="max-w-lg mx-auto animate-fade-in">
        <style>{`
          @keyframes fade-in { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
          @keyframes pulse-border { 0%, 100% { border-color: #003b71; } 50% { border-color: #38bdf8; } }
          .animate-fade-in { animation: fade-in 0.5s ease-out; }
          .animate-pulse-border { animation: pulse-border 2s ease-in-out infinite; }
        `}</style>
        
        {/* Header */}
        <div className="bg-white rounded-2xl shadow-xl border border-zinc-100 overflow-hidden">
          <div className="bg-gradient-to-r from-[#003b71] to-[#005baa] px-6 py-4 flex items-center gap-3">
            <button onClick={() => setStep('select')} className="text-white/80 hover:text-white transition">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <PromptPayLogo />
          </div>
          
          <div className="p-6">
            {/* Timer */}
            <div className="text-center mb-5">
              <p className="text-zinc-500 text-sm mb-1">กรุณาชำระเงินภายใน</p>
              <div className={`text-3xl font-mono font-bold ${countdown < 60 ? 'text-red-500' : 'text-zinc-800'}`}>
                {formatTime(countdown)}
              </div>
            </div>

            {/* QR Code */}
            <div className="flex justify-center mb-5">
              <div className="p-3 border-4 border-[#003b71] rounded-2xl animate-pulse-border bg-white">
                <FakeQRCode />
              </div>
            </div>

            {/* Amount */}
            <div className="text-center mb-5">
              <p className="text-zinc-500 text-sm mb-1">จำนวนเงินที่ต้องชำระ</p>
              <p className="text-3xl font-bold text-zinc-900">฿{booking.total.toLocaleString()}.00</p>
            </div>

            {/* Instructions */}
            <div className="bg-sky-50 border border-sky-100 rounded-xl p-4 mb-5">
              <p className="text-sky-900 font-semibold text-sm mb-2">📱 วิธีชำระเงิน</p>
              <ol className="text-sky-800 text-sm space-y-1.5 list-decimal list-inside">
                <li>เปิดแอปธนาคารของคุณ</li>
                <li>เลือก "สแกน QR Code"</li>
                <li>สแกน QR Code ด้านบน</li>
                <li>ตรวจสอบจำนวนเงินและยืนยันการชำระ</li>
              </ol>
            </div>

            {/* Mock: Confirm payment button */}
            <button
              onClick={handleQrConfirmPaid}
              disabled={isProcessing}
              className="w-full py-3.5 bg-emerald-500 text-white rounded-xl font-semibold text-base hover:bg-emerald-600 transition-all disabled:opacity-60 disabled:cursor-not-allowed active:scale-[0.98] flex items-center justify-center gap-2"
            >
              {isProcessing ? (
                <>
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  กำลังตรวจสอบ...
                </>
              ) : (
                '✅ ฉันชำระเงินแล้ว (Sandbox)'
              )}
            </button>
            <p className="text-center text-zinc-400 text-xs mt-2">* ปุ่มนี้สำหรับ Sandbox เท่านั้น</p>
          </div>
        </div>
      </div>
    );
  }

  // ─── Credit Card Form Screen ───
  if (step === 'credit-form') {
    return (
      <div className="max-w-lg mx-auto animate-fade-in">
        <style>{`
          @keyframes fade-in { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
          .animate-fade-in { animation: fade-in 0.5s ease-out; }
        `}</style>
        
        <div className="bg-white rounded-2xl shadow-xl border border-zinc-100 overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-zinc-800 to-zinc-900 px-6 py-4 flex items-center gap-3">
            <button onClick={() => setStep('select')} className="text-white/80 hover:text-white transition">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                <rect x="2" y="5" width="24" height="18" rx="3" fill="#3b82f6" />
                <rect x="2" y="10" width="24" height="4" fill="#1e3a8a" />
                <rect x="5" y="17" width="8" height="2" rx="0.5" fill="#93c5fd" />
              </svg>
              <span className="text-white font-semibold text-lg">ชำระด้วยบัตรเครดิต/เดบิต</span>
            </div>
          </div>

          <div className="p-6">
            {/* Card Visual */}
            <div className="relative w-full h-44 bg-gradient-to-br from-slate-700 via-slate-800 to-zinc-900 rounded-2xl p-5 mb-6 overflow-hidden shadow-lg">
              <div className="absolute top-0 right-0 w-40 h-40 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/2" />
              <div className="absolute bottom-0 left-0 w-32 h-32 bg-white/5 rounded-full translate-y-1/2 -translate-x-1/2" />
              
              {/* Chip */}
              <div className="w-10 h-7 bg-gradient-to-br from-amber-300 to-amber-500 rounded-md mb-5 flex items-center justify-center">
                <div className="w-6 h-4 border border-amber-600/40 rounded-sm" />
              </div>
              
              <p className="text-white/90 font-mono text-lg tracking-[0.2em] mb-4">
                {cardNumber || '•••• •••• •••• ••••'}
              </p>
              
              <div className="flex justify-between items-end">
                <div>
                  <p className="text-white/40 text-[10px] uppercase mb-0.5">Card Holder</p>
                  <p className="text-white/80 text-sm font-medium tracking-wider">
                    {cardName || 'YOUR NAME'}
                  </p>
                </div>
                <div>
                  <p className="text-white/40 text-[10px] uppercase mb-0.5">Expires</p>
                  <p className="text-white/80 text-sm font-mono">{expiry || 'MM/YY'}</p>
                </div>
                <div className="flex -space-x-2">
                  <div className="w-7 h-7 bg-red-500/80 rounded-full" />
                  <div className="w-7 h-7 bg-amber-400/80 rounded-full" />
                </div>
              </div>
            </div>

            {/* Form */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-600 mb-1.5">หมายเลขบัตร</label>
                <input
                  type="text"
                  placeholder="0000 0000 0000 0000"
                  value={cardNumber}
                  onChange={(e) => setCardNumber(formatCardNumber(e.target.value))}
                  className="w-full px-4 py-3 border-2 border-zinc-200 rounded-xl text-zinc-800 font-mono text-base bg-zinc-50 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:bg-white outline-none transition-all placeholder:text-zinc-300"
                  maxLength={19}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-zinc-600 mb-1.5">ชื่อบนบัตร</label>
                <input
                  type="text"
                  placeholder="JOHN DOE"
                  value={cardName}
                  onChange={(e) => setCardName(e.target.value.toUpperCase())}
                  className="w-full px-4 py-3 border-2 border-zinc-200 rounded-xl text-zinc-800 text-base bg-zinc-50 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:bg-white outline-none transition-all placeholder:text-zinc-300 tracking-wider"
                />
              </div>
              
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-zinc-600 mb-1.5">วันหมดอายุ</label>
                  <input
                    type="text"
                    placeholder="MM/YY"
                    value={expiry}
                    onChange={(e) => setExpiry(formatExpiry(e.target.value))}
                    className="w-full px-4 py-3 border-2 border-zinc-200 rounded-xl text-zinc-800 font-mono text-base bg-zinc-50 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:bg-white outline-none transition-all placeholder:text-zinc-300"
                    maxLength={5}
                  />
                </div>
                <div className="w-28">
                  <label className="block text-sm font-medium text-zinc-600 mb-1.5">CVV</label>
                  <input
                    type="password"
                    placeholder="•••"
                    value={cvv}
                    onChange={(e) => setCvv(e.target.value.replace(/\D/g, '').slice(0, 3))}
                    className="w-full px-4 py-3 border-2 border-zinc-200 rounded-xl text-zinc-800 font-mono text-base bg-zinc-50 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:bg-white outline-none transition-all placeholder:text-zinc-300 text-center"
                    maxLength={3}
                  />
                </div>
              </div>
            </div>

            {/* Amount */}
            <div className="mt-6 bg-zinc-50 border border-zinc-100 rounded-xl p-4 flex justify-between items-center">
              <span className="text-zinc-500 text-sm">จำนวนเงินที่ต้องชำระ</span>
              <span className="text-xl font-bold text-zinc-900">฿{booking.total.toLocaleString()}.00</span>
            </div>

            {/* Submit */}
            <button
              onClick={handleCreditSubmit}
              disabled={isProcessing || cardNumber.length < 19 || !cardName || expiry.length < 5 || cvv.length < 3}
              className="w-full mt-5 py-3.5 bg-blue-600 text-white rounded-xl font-semibold text-base hover:bg-blue-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98] flex items-center justify-center gap-2"
            >
              {isProcessing ? (
                <>
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  กำลังดำเนินการ...
                </>
              ) : (
                <>🔒 ยืนยันชำระเงิน ฿{booking.total.toLocaleString()}.00</>
              )}
            </button>
            
            <div className="mt-3 flex items-center justify-center gap-1.5 text-zinc-400 text-xs">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0110 0v4" />
              </svg>
              ข้อมูลบัตรถูกเข้ารหัสและปลอดภัย (Sandbox)
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ─── Main: Payment Selection Screen ───
  return (
    <div className="max-w-lg mx-auto">
      <style>{`
        @keyframes fade-in { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slide-up { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fade-in { animation: fade-in 0.5s ease-out; }
        .animate-slide-up { animation: slide-up 0.5s ease-out; }
      `}</style>

      {/* Sandbox Badge */}
      <div className="animate-fade-in mb-4 flex items-center justify-center">
        <span className="bg-amber-100 text-amber-800 text-xs font-bold px-3 py-1.5 rounded-full border border-amber-200 flex items-center gap-1.5">
          🧪 SANDBOX MODE — หน้าทดสอบการชำระเงิน
        </span>
      </div>

      {/* Ticket Pickup Method */}
      <div className="animate-fade-in bg-white rounded-2xl shadow-lg border border-zinc-100 p-5 mb-4">
        <h3 className="text-zinc-800 font-bold text-base mb-3">กรุณาเลือกวิธีการรับบัตร</h3>
        <div className="border-2 border-emerald-400 bg-emerald-50 rounded-xl p-4 flex items-center gap-3 cursor-pointer transition-all">
          <TicketIcon />
          <div>
            <p className="font-semibold text-zinc-800 text-sm">รับบัตรด้วยตนเอง</p>
            <p className="text-zinc-500 text-xs">ที่จุดรับบัตร ณ สถานที่จัดงาน</p>
          </div>
          <div className="ml-auto">
            <div className="w-6 h-6 rounded-full border-2 border-emerald-400 flex items-center justify-center">
              <div className="w-3 h-3 bg-emerald-400 rounded-full" />
            </div>
          </div>
        </div>
      </div>

      {/* Payment Method Selection */}
      <div className="animate-slide-up bg-white rounded-2xl shadow-lg border border-zinc-100 p-5 mb-4" style={{ animationDelay: '0.1s' }}>
        <h3 className="text-zinc-800 font-bold text-base mb-4">กรุณาเลือกวิธีการชำระเงิน</h3>
        <div className="grid grid-cols-2 gap-3">
          {/* Credit Card */}
          <button
            onClick={() => setSelectedPayment('credit')}
            className={`relative rounded-xl p-4 border-2 transition-all duration-200 flex flex-col items-center gap-2 hover:shadow-md active:scale-[0.97] ${
              selectedPayment === 'credit'
                ? 'border-blue-500 bg-blue-50 shadow-md shadow-blue-100'
                : 'border-zinc-200 bg-white hover:border-zinc-300'
            }`}
          >
            {selectedPayment === 'credit' && (
              <div className="absolute top-2 right-2 w-5 h-5 bg-blue-500 rounded-full flex items-center justify-center">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </div>
            )}
            <CreditCardIcon />
            <span className="font-semibold text-zinc-700 text-sm">บัตรเครดิต/เดบิต</span>
          </button>

          {/* QR PromptPay */}
          <button
            onClick={() => setSelectedPayment('promptpay')}
            className={`relative rounded-xl p-4 border-2 transition-all duration-200 flex flex-col items-center gap-2 hover:shadow-md active:scale-[0.97] ${
              selectedPayment === 'promptpay'
                ? 'border-blue-500 bg-blue-50 shadow-md shadow-blue-100'
                : 'border-zinc-200 bg-white hover:border-zinc-300'
            }`}
          >
            {selectedPayment === 'promptpay' && (
              <div className="absolute top-2 right-2 w-5 h-5 bg-blue-500 rounded-full flex items-center justify-center">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </div>
            )}
            <QrIcon />
            <span className="font-semibold text-zinc-700 text-sm">QR PromptPay</span>
          </button>
        </div>
      </div>

      {/* Booking Summary */}
      <div className="animate-slide-up bg-white rounded-2xl shadow-lg border border-zinc-100 overflow-hidden mb-4" style={{ animationDelay: '0.2s' }}>
        <button
          onClick={() => setShowSummary(!showSummary)}
          className="w-full bg-gradient-to-r from-red-500 to-red-600 text-white px-5 py-3 flex items-center justify-between"
        >
          <span className="font-bold text-sm">รายละเอียดการจอง</span>
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`transition-transform duration-200 ${showSummary ? 'rotate-180' : ''}`}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {showSummary && (
          <div className="p-5 space-y-3 text-sm">
            <div className="text-center mb-4">
              <h4 className="font-bold text-zinc-900 text-base leading-tight">{booking.event}</h4>
              <p className="text-zinc-500 text-xs mt-1 flex items-center justify-center gap-1">
                📍 {booking.venue}
              </p>
            </div>

            <div className="bg-zinc-50 rounded-xl p-3 text-center mb-3">
              <p className="text-zinc-500 text-xs">รอบการแสดง</p>
              <p className="text-red-500 font-bold text-sm">{booking.showtime}</p>
            </div>

            <div className="divide-y divide-zinc-100">
              <div className="flex justify-between py-2">
                <span className="text-zinc-500">โซนที่นั่ง</span>
                <span className="font-semibold text-blue-600">{booking.zone}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-zinc-500">เลขที่นั่ง</span>
                <span className="font-semibold text-blue-600">{booking.seat}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-zinc-500">จำนวนที่นั่ง</span>
                <span className="font-semibold text-zinc-800">{booking.quantity}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-zinc-500">ราคาบัตร</span>
                <span className="font-semibold text-zinc-800">{booking.price.toLocaleString()}.00</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-zinc-500">ค่าบริการ (30 บาทต่อใบ + Processing fee 3%)</span>
                <span className="font-semibold text-zinc-800">{booking.serviceFee.toLocaleString()}.00</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-zinc-500">Ticket Protect</span>
                <span className="font-semibold text-zinc-800">{booking.ticketProtect.toLocaleString()}.00</span>
              </div>
              <div className="flex justify-between py-3 text-base">
                <span className="font-bold text-zinc-900">จำนวนเงินที่ต้องชำระ</span>
                <span className="font-bold text-red-500">฿{booking.total.toLocaleString()}.00</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Confirm Button */}
      <div className="animate-slide-up sticky bottom-0 bg-gradient-to-t from-zinc-950 via-zinc-950/95 to-transparent pt-6 pb-4 -mx-4 px-4" style={{ animationDelay: '0.3s' }}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-zinc-500 text-xs">จำนวนเงินที่ต้องชำระ</p>
            <p className="text-white font-bold text-xl">฿{booking.total.toLocaleString()}.00</p>
          </div>
          <button
            onClick={handleConfirm}
            disabled={!selectedPayment}
            className="px-8 py-3.5 bg-gradient-to-r from-red-500 to-red-600 text-white rounded-xl font-bold text-base hover:from-red-600 hover:to-red-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.97] shadow-lg shadow-red-500/20"
          >
            ยืนยันการสั่งซื้อ
          </button>
        </div>
      </div>
    </div>
  );
}
