import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'
import type { ViewId } from '../../types'
import { AskPanel } from './AskPanel'
import { LimitsPanel } from './LimitsPanel'
import { NavigationPanel } from './NavigationPanel'
import { StatsGrid } from './StatsGrid'
import { TopicsPanel } from './TopicsPanel'
import { WelcomeHero } from './WelcomeHero'

type Props = {
  // `ask` renders the chat and `privacy` opens the served policy page, so
  // neither reaches this component; anything unrecognised falls back to home.
  view: ViewId
  capabilities: Capabilities | null
  error: string | null
  query: string
  onNavigate: (view: ViewId) => void
  onAsk: (question?: string) => void
  onRetry: () => void
}

// The home surface. Four panels, each backed by /capabilities or by a control
// that exists in the backend — there is deliberately no panel here that would
// need a student record to fill.
export function DashboardPage({ view, capabilities, error, query, onNavigate, onAsk, onRetry }: Props) {
  const { s } = useI18n()

  if (error) {
    return (
      <div className="dashboard">
        <div className="panel-empty panel-empty--page">
          <strong>{s.status_unreachable}</strong>
          <p>{s.error_connect}</p>
          <button className="secondary-button" onClick={onRetry}>{s.status_retry}</button>
        </div>
      </div>
    )
  }

  if (view === 'topics') {
    return (
      <div className="dashboard">
        <TopicsPanel capabilities={capabilities} query={query} />
      </div>
    )
  }

  if (view === 'open') {
    return (
      <div className="dashboard">
        <NavigationPanel capabilities={capabilities} />
      </div>
    )
  }

  if (view === 'status') {
    return (
      <div className="dashboard">
        <StatsGrid capabilities={capabilities} />
        <LimitsPanel />
      </div>
    )
  }

  return (
    <div className="dashboard">
      <WelcomeHero
        capabilities={capabilities}
        onAsk={() => onAsk()}
        onTopics={() => onNavigate('topics')}
      />
      <StatsGrid capabilities={capabilities} />
      <div className="dashboard-grid">
        <div className="dashboard-grid__main">
          <AskPanel capabilities={capabilities} onAsk={onAsk} />
          <TopicsPanel capabilities={capabilities} query={query} />
        </div>
        <div className="dashboard-grid__side">
          <NavigationPanel capabilities={capabilities} />
          <LimitsPanel />
        </div>
      </div>
      <footer className="page-footer">
        <span>{s.footer_note}</span>
      </footer>
    </div>
  )
}
