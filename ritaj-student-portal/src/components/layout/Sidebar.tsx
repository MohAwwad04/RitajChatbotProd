import { ChevronLeft, LogOut } from 'lucide-react'
import { footerLinks, mainNavigation, serviceNavigation } from '../../data/dashboard'
import { Brand } from '../ui/Brand'

type Props = {
  collapsed: boolean
  mobileOpen: boolean
  active: string
  onNavigate: (label: string) => void
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
  items: typeof mainNavigation
  active: string
  collapsed: boolean
  onNavigate: (label: string) => void
}) {
  return (
    <div className="nav-group">
      {label && !collapsed && <span className="nav-group__label">{label}</span>}
      <nav aria-label={label ?? 'التنقل الرئيسي'}>
        {items.map((item) => {
          const Icon = item.icon
          return (
            <button
              className={`nav-item ${active === item.label ? 'is-active' : ''}`}
              key={item.label}
              onClick={() => onNavigate(item.label)}
              title={collapsed ? item.label : undefined}
            >
              <Icon size={20} strokeWidth={1.8} />
              {!collapsed && <span>{item.label}</span>}
              {!collapsed && item.badge && <b>{item.badge}</b>}
              {!collapsed && active !== item.label && <ChevronLeft className="nav-item__arrow" size={15} />}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

export function Sidebar({ collapsed, mobileOpen, active, onNavigate, onClose }: Props) {
  const navigate = (label: string) => {
    onNavigate(label)
    onClose()
  }

  return (
    <>
      <button className={`sidebar-backdrop ${mobileOpen ? 'is-visible' : ''}`} onClick={onClose} aria-label="إغلاق القائمة" />
      <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'is-open' : ''}`}>
        <div className="sidebar__top"><Brand compact={collapsed} /></div>
        <div className="sidebar__body">
          <NavGroup items={mainNavigation} active={active} collapsed={collapsed} onNavigate={navigate} />
          <NavGroup label="الخدمات" items={serviceNavigation} active={active} collapsed={collapsed} onNavigate={navigate} />
        </div>
        <div className="sidebar__footer">
          {footerLinks.map((item) => {
            const Icon = item.icon
            return (
              <button key={item.label} title={collapsed ? item.label : undefined} onClick={() => navigate(item.label)}>
                <Icon size={19} />{!collapsed && <span>{item.label}</span>}
              </button>
            )
          })}
          <button className="logout" title={collapsed ? 'تسجيل الخروج' : undefined}>
            <LogOut size={19} />{!collapsed && <span>تسجيل الخروج</span>}
          </button>
        </div>
      </aside>
    </>
  )
}
