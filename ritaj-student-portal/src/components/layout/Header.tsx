import { Bell, ChevronDown, Menu, Moon, Search, Sun } from 'lucide-react'
import { Brand } from '../ui/Brand'

type Props = {
  darkMode: boolean
  onToggleTheme: () => void
  onToggleSidebar: () => void
  onOpenMobileMenu: () => void
  query: string
  onQueryChange: (value: string) => void
  onToggleNotifications: () => void
}

export function Header({
  darkMode,
  onToggleTheme,
  onToggleSidebar,
  onOpenMobileMenu,
  query,
  onQueryChange,
  onToggleNotifications,
}: Props) {
  return (
    <header className="topbar">
      <div className="topbar__start">
        <button className="icon-button desktop-only" onClick={onToggleSidebar} aria-label="طي القائمة الجانبية"><Menu size={21} /></button>
        <button className="icon-button mobile-only" onClick={onOpenMobileMenu} aria-label="فتح القائمة"><Menu size={21} /></button>
        <div className="mobile-only"><Brand compact /></div>
        <div className="page-title">
          <span>بوابة الطالب</span>
          <strong>الرئيسية</strong>
        </div>
      </div>

      <label className="search-box">
        <Search size={19} />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="ابحث في البوابة..." />
        <kbd>⌘ K</kbd>
      </label>

      <div className="topbar__actions">
        <button className="icon-button" onClick={onToggleTheme} aria-label="تبديل المظهر">
          {darkMode ? <Sun size={19} /> : <Moon size={19} />}
        </button>
        <button className="icon-button notification-button" onClick={onToggleNotifications} aria-label="التنبيهات">
          <Bell size={19} /><i />
        </button>
        <button className="profile-chip">
          <span className="avatar">ب</span>
          <span><strong>براء سعيد</strong><small>طالب بكالوريوس</small></span>
          <ChevronDown size={15} />
        </button>
      </div>
    </header>
  )
}
