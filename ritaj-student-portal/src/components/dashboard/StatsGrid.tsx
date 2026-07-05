import { ArrowDownLeft, ArrowUpLeft, BookOpenCheck, CircleDollarSign, Gauge, GraduationCap } from 'lucide-react'

const stats = [
  { label: 'المعدل التراكمي', value: '3.42', suffix: '/ 4.00', meta: '+0.08 هذا الفصل', icon: Gauge, trend: 'up' },
  { label: 'الساعات المنجزة', value: '108', suffix: 'ساعة', meta: 'من أصل 132', icon: GraduationCap, trend: 'up' },
  { label: 'المساقات الحالية', value: '5', suffix: 'مساقات', meta: '15 ساعة معتمدة', icon: BookOpenCheck, trend: 'neutral' },
  { label: 'الرصيد المالي', value: '240', suffix: 'د.أ', meta: 'مستحق قبل التسجيل', icon: CircleDollarSign, trend: 'down' },
]

export function StatsGrid() {
  return (
    <section className="stats-grid" aria-label="ملخص الحساب">
      {stats.map((stat) => {
        const Icon = stat.icon
        return (
          <article className="stat-card" key={stat.label}>
            <div className="stat-card__icon"><Icon size={21} /></div>
            <div className="stat-card__copy"><span>{stat.label}</span><strong>{stat.value} <small>{stat.suffix}</small></strong></div>
            <div className={`stat-card__meta ${stat.trend}`}>
              {stat.trend === 'up' && <ArrowUpLeft size={14} />}
              {stat.trend === 'down' && <ArrowDownLeft size={14} />}
              {stat.meta}
            </div>
          </article>
        )
      })}
    </section>
  )
}
