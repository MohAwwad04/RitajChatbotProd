import { aboutViews, mobileViews, views } from '../../data/dashboard'
import { useI18n } from '../../i18n'
import type { ViewId } from '../../types'

// Built from the same view registry as the sidebar, so the phone bar can never
// offer a tab the rail does not have (or, as before, five tabs — Home, Courses,
// Calendar, Messages, My account — of which none had a screen behind it).
export function MobileNav({
  active,
  onNavigate,
}: {
  active: ViewId
  onNavigate: (view: ViewId) => void
}) {
  const { s } = useI18n()
  const all = [...views(s), ...aboutViews(s)]
  const items = mobileViews
    .map((id) => all.find((view) => view.id === id))
    .filter((view): view is NonNullable<typeof view> => Boolean(view))

  return (
    <nav className="mobile-nav" aria-label={s.aria_sidebar}>
      {items.map((item) => {
        const Icon = item.icon
        return (
          <button
            key={item.id}
            className={active === item.id ? 'is-active' : ''}
            onClick={() => onNavigate(item.id)}
          >
            <Icon size={20} />
            <span>{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
