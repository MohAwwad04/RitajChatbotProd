import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchCapabilities, type Capabilities } from './api/capabilities'
import { ChatbotPage } from './components/chatbot/ChatbotPage'
import { DashboardPage } from './components/dashboard/DashboardPage'
import { Header } from './components/layout/Header'
import { MobileNav } from './components/layout/MobileNav'
import { Sidebar } from './components/layout/Sidebar'
import { StatusPanel } from './components/layout/StatusPanel'
import { aboutViews, views } from './data/dashboard'
import { LangContext, dict, type Lang } from './i18n'
import type { ViewId } from './types'
import './styles/global.css'
import './styles/chatbot.css'

// The shell the dashboard components were written for but never mounted: until
// now App rendered ChatbotPage alone, so Sidebar, Header, MobileNav, the four
// dashboard panels and the notifications drawer were unreachable code. They
// have been rebuilt around what the backend actually exposes (/capabilities)
// and are wired up here.
function App() {
  const [lang, setLang] = useState<Lang>('ar')
  const [view, setView] = useState<ViewId>('home')
  const [darkMode, setDarkMode] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [statusOpen, setStatusOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)

  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  // Flip the document direction/language with the UI language.
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dict[lang].dir
  }, [lang])

  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    fetchCapabilities(controller.signal)
      .then(setCapabilities)
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setCapabilities(null)
        setError(cause instanceof Error ? cause.message : 'unreachable')
      })
    return () => controller.abort()
  }, [reloadToken])

  const value = useMemo(() => ({ lang, setLang, s: dict[lang] }), [lang])
  const s = dict[lang]

  const askWith = useCallback((question?: string) => {
    if (question) setPendingQuestion(question)
    setView('ask')
  }, [])

  const navigate = useCallback((next: ViewId) => {
    // Privacy is the served policy page, shared with the extension, so it is a
    // real navigation rather than a client-side route.
    if (next === 'privacy') {
      window.open('/privacy', '_blank', 'noopener')
      return
    }
    setView(next)
    setMobileMenuOpen(false)
  }, [])

  const title = useMemo(() => {
    const all = [...views(s), ...aboutViews(s)]
    return all.find((item) => item.id === view)?.label ?? s.view_home
  }, [s, view])

  if (view === 'ask') {
    return (
      <LangContext.Provider value={value}>
        <ChatbotPage
          darkMode={darkMode}
          onToggleTheme={() => setDarkMode((current) => !current)}
          onBack={() => setView('home')}
          pendingQuestion={pendingQuestion}
          onPendingConsumed={() => setPendingQuestion(null)}
        />
      </LangContext.Provider>
    )
  }

  return (
    <LangContext.Provider value={value}>
      <div className={`app-shell ${darkMode ? 'theme-dark' : ''} ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`} dir={s.dir}>
        <Sidebar
          collapsed={sidebarCollapsed}
          mobileOpen={mobileMenuOpen}
          active={view}
          onNavigate={navigate}
          onClose={() => setMobileMenuOpen(false)}
        />
        <div className="workspace">
          {/* Persistent, above everything, and it removes itself the moment a
              verified corpus is published — because it is driven by the corpus
              manifest, not by a hard-coded flag someone has to remember. */}
          {capabilities?.corpus?.verified === false && (
            <div className="corpus-warning" role="status">
              <strong>{s.corpus_unverified_title}</strong>
              {s.corpus_unverified}
            </div>
          )}
          <Header
            title={title}
            darkMode={darkMode}
            onToggleTheme={() => setDarkMode((current) => !current)}
            onToggleSidebar={() => setSidebarCollapsed((current) => !current)}
            onOpenMobileMenu={() => setMobileMenuOpen(true)}
            query={query}
            onQueryChange={setQuery}
            onToggleStatus={() => setStatusOpen((current) => !current)}
            capabilities={capabilities}
            error={error}
            searchable={view === 'home' || view === 'topics'}
          />
          <DashboardPage
            view={view}
            capabilities={capabilities}
            error={error}
            query={query}
            onNavigate={navigate}
            onAsk={askWith}
            onRetry={() => setReloadToken((token) => token + 1)}
          />
        </div>
        <MobileNav active={view} onNavigate={navigate} />
        <StatusPanel
          open={statusOpen}
          onClose={() => setStatusOpen(false)}
          capabilities={capabilities}
          error={error}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
        {statusOpen && (
          <button className="panel-backdrop" onClick={() => setStatusOpen(false)} aria-label={s.aria_close_panel} />
        )}
      </div>
    </LangContext.Provider>
  )
}

export default App
