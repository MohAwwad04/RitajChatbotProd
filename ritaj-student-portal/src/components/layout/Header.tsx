import { Activity, Languages, Menu, Moon, Search, Sun } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'
import { Brand } from '../ui/Brand'

type Props = {
  title: string
  darkMode: boolean
  onToggleTheme: () => void
  onToggleSidebar: () => void
  onOpenMobileMenu: () => void
  query: string
  onQueryChange: (value: string) => void
  onToggleStatus: () => void
  capabilities: Capabilities | null
  error: string | null
  searchable: boolean
}

// The profile chip is gone. It rendered a fabricated student ("براء سعيد ·
// طالب بكالوريوس") on a product with no accounts, no session and no name — the
// same name field the roadmap removed from the chat for exactly that reason.
// The topbar now carries only controls that do something: menu, a search that
// filters the approved-topic list, language, theme, and service status.
export function Header({
  title,
  darkMode,
  onToggleTheme,
  onToggleSidebar,
  onOpenMobileMenu,
  query,
  onQueryChange,
  onToggleStatus,
  capabilities,
  error,
  searchable,
}: Props) {
  const { s, lang, setLang } = useI18n()
  const statusTone = error ? 'is-error' : capabilities?.ready ? 'is-ok' : 'is-pending'

  return (
    <header className="topbar">
      <div className="topbar__start">
        <button className="icon-button desktop-only" onClick={onToggleSidebar} aria-label={s.aria_menu}>
          <Menu size={21} />
        </button>
        <button className="icon-button mobile-only" onClick={onOpenMobileMenu} aria-label={s.aria_menu}>
          <Menu size={21} />
        </button>
        <div className="mobile-only"><Brand compact /></div>
        <div className="page-title">
          <span>{s.portal_label}</span>
          <strong>{title}</strong>
        </div>
      </div>

      {searchable ? (
        <label className="search-box">
          <Search size={19} />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={s.search_placeholder}
          />
        </label>
      ) : (
        <span />
      )}

      <div className="topbar__actions">
        <button
          className="icon-button"
          onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
          aria-label={s.aria_lang}
          title={s.aria_lang}
        >
          <Languages size={19} />
        </button>
        <button className="icon-button" onClick={onToggleTheme} aria-label={s.aria_toggle_theme}>
          {darkMode ? <Sun size={19} /> : <Moon size={19} />}
        </button>
        <button
          className={`icon-button status-button ${statusTone}`}
          onClick={onToggleStatus}
          aria-label={s.aria_status}
          title={s.status_title}
        >
          <Activity size={19} /><i />
        </button>
      </div>
    </header>
  )
}
