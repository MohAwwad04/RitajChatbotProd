import { ArrowUpLeft } from 'lucide-react'
import { quickActions } from '../../data/dashboard'
import { SectionHeader } from '../ui/SectionHeader'

export function QuickActions({ query }: { query: string }) {
  const normalizedQuery = query.trim().toLowerCase()
  const visibleActions = quickActions.filter((action) => `${action.label} ${action.description}`.toLowerCase().includes(normalizedQuery))

  return (
    <section className="content-card quick-actions-card">
      <SectionHeader title="الوصول السريع" eyebrow="خدماتك الأكثر استخداماً" />
      <div className="quick-grid">
        {visibleActions.map((action) => {
          const Icon = action.icon
          return (
            <button className="quick-action" key={action.label}>
              <span className="quick-action__icon"><Icon size={21} /></span>
              <span className="quick-action__copy"><strong>{action.label}</strong><small>{action.description}</small></span>
              {action.badge ? <b className="count-badge">{action.badge}</b> : <ArrowUpLeft className="quick-action__arrow" size={18} />}
            </button>
          )
        })}
        {visibleActions.length === 0 && <p className="empty-state">لا توجد خدمات مطابقة لـ “{query}”.</p>}
      </div>
    </section>
  )
}
