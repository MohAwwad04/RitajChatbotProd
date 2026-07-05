import { CalendarClock, CheckCheck, CircleDollarSign, X } from 'lucide-react'

export function NotificationsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <aside className={`notifications-panel ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <div className="notifications-panel__head">
        <div><span className="eyebrow">آخر التحديثات</span><h2>التنبيهات</h2></div>
        <button className="icon-button" onClick={onClose} aria-label="إغلاق التنبيهات"><X size={20} /></button>
      </div>
      <div className="notification-entry is-new">
        <span><CalendarClock size={19} /></span>
        <div><strong>اقترب موعد التسجيل</strong><p>يفتح تسجيل الدورة الصيفية غداً الساعة 9:00 صباحاً.</p><small>منذ 12 دقيقة</small></div>
      </div>
      <div className="notification-entry is-new">
        <span><CircleDollarSign size={19} /></span>
        <div><strong>تحديث السجل المالي</strong><p>تمت إضافة دفعة جديدة إلى حسابك.</p><small>منذ ساعتين</small></div>
      </div>
      <div className="notification-entry">
        <span><CheckCheck size={19} /></span>
        <div><strong>تم اعتماد طلبك</strong><p>وافق المرشد الأكاديمي على خطتك للفصل القادم.</p><small>أمس</small></div>
      </div>
      <button className="text-button panel-link">عرض كل التنبيهات</button>
    </aside>
  )
}
