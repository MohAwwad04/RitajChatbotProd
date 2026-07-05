import { ArrowLeft, CalendarPlus, Info, Sparkles } from 'lucide-react'

export function WelcomeHero() {
  return (
    <section className="welcome-hero">
      <div className="welcome-hero__content">
        <span className="hero-label"><Sparkles size={15} /> الدورة الصيفية 2025/2026</span>
        <h1>صباح الخير، براء</h1>
        <p>موعد تسجيلك غداً. راجع خطتك الدراسية والرسوم المطلوبة قبل بدء التسجيل.</p>
        <div className="hero-actions">
          <button className="primary-button"><CalendarPlus size={18} /> الاستعداد للتسجيل <ArrowLeft size={17} /></button>
          <button className="ghost-button"><Info size={18} /> تفاصيل الرسوم</button>
        </div>
      </div>
      <div className="semester-orbit" aria-label="التقدم في الفصل 72 بالمئة">
        <svg viewBox="0 0 220 170" role="img">
          <path className="orbit-track" d="M16 146 C48 35, 165 12, 204 123" />
          <path className="orbit-value" pathLength="100" d="M16 146 C48 35, 165 12, 204 123" />
          <circle cx="167" cy="55" r="7" />
        </svg>
        <div className="semester-orbit__value"><strong>72%</strong><span>من الفصل</span></div>
        <small>48 يوماً حتى النهاية</small>
      </div>
    </section>
  )
}
