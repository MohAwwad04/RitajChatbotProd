import { BookOpen, CalendarDays, House, Mail, UserRound } from 'lucide-react'

const items = [
  { label: 'الرئيسية', icon: House },
  { label: 'المساقات', icon: BookOpen },
  { label: 'التقويم', icon: CalendarDays },
  { label: 'الرسائل', icon: Mail },
  { label: 'حسابي', icon: UserRound },
]

export function MobileNav({ active, onNavigate }: { active: string; onNavigate: (label: string) => void }) {
  return (
    <nav className="mobile-nav" aria-label="التنقل السريع">
      {items.map((item) => {
        const Icon = item.icon
        const isActive = active === item.label || (item.label === 'التقويم' && active === 'التقويم الأكاديمي')
        return <button key={item.label} className={isActive ? 'is-active' : ''} onClick={() => onNavigate(item.label)}><Icon size={20} /><span>{item.label}</span></button>
      })}
    </nav>
  )
}
