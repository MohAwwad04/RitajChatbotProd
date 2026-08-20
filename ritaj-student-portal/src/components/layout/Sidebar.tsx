import { ChevronLeft, ChevronRight } from 'lucide-react'
import { aboutViews, views } from '../../data/dashboard'
import { useI18n } from '../../i18n'
import type { NavigationItem, ViewId } from '../../types'
import { Brand } from '../ui/Brand'

type Props = {
  collapsed: boolean
  mobileOpen: boolean
  active: ViewId
  onNavigate: (view: ViewId) => void
  onClose: () => void
}

function NavGroup({
  label,
  items,
  active,
  collapsed,
  onNavigate,
}: {
  label?: string
  items: NavigationItem[]
  active: ViewId
  collapsed: boolean
  onNavigate: (view: ViewId) => void
}) {
  const { s, lang } = useI18n()
  const Chevron = lang === 'ar' ? ChevronLeft : ChevronRight
  return (
    <div className="nav-group">
      {label && !collapsed && <span className="nav-group__label">{label}</span>}
      <nav aria-label={label ?? s.aria_sidebar}>
        {items.map((item) => {
          const Icon = item.icon
          return (
            <button
              className={`nav-item ${active === item.id ? 'is-active' : ''}`}
              key={item.id}
              onClick={() => onNavigate(item.id)}
              title={collapsed ? item.label : undefined}
            >
              <Icon size={20} strokeWidth={1.8} />
              {!collapsed && <span>{item.label}</span>}
              {!collapsed && active !== item.id && <Chevron className="nav-item__arrow" size={15} />}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

// The rail no longer offers Grades, Financial record, Messages, Profile or a
// Log out button: this product has no account to sign out of, and offering
// those destinations implied a portal behind them. Every entry below routes to
// a view that exists.
export function Sidebar({ collapsed, mobileOpen, active, onNavigate, onClose }: Props) {
  const { s } = useI18n()
  const navigate = (view: ViewId) => {
    onNavigate(view)
    onClose()
  }

  return (
    <>
      <button
        className={`sidebar-backdrop ${mobileOpen ? 'is-visible' : ''}`}
        onClick={onClose}
        aria-label={s.aria_close_panel}
      />
      <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'is-open' : ''}`}>
        <div className="sidebar__top"><Brand compact={collapsed} /></div>
        <div className="sidebar__body">
          <NavGroup items={views(s)} active={active} collapsed={collapsed} onNavigate={navigate} />
          <NavGroup
            label={s.nav_group_about}
            items={aboutViews(s)}
            active={active}
            collapsed={collapsed}
            onNavigate={navigate}
          />
        </div>
        <div className="sidebar__footer">
          {!collapsed && <p className="sidebar__note">{s.unofficial}</p>}
        </div>
      </aside>
    </>
  )
}
