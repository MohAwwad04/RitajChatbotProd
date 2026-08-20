import { ExternalLink, Lock, MousePointerClick, ShieldAlert } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'
import { SectionHeader } from '../ui/SectionHeader'

// Replaces UpcomingEvents (four invented exam dates on date tiles).
//
// These are the reviewed destinations the assistant is allowed to open — the
// same registry the answer path resolves an action id against, and the same one
// the extension re-validates before chrome.tabs.create. Rendering it here means
// a student can see the whole list rather than discovering destinations one
// button at a time, and flipping `enabled: false` withdraws a destination from
// this panel in the same redeploy that withdraws it from chat.
export function NavigationPanel({ capabilities }: { capabilities: Capabilities | null }) {
  const { s, lang } = useI18n()
  const destinations = capabilities?.navigation ?? []
  const pending = capabilities?.pending_navigation ?? 0

  return (
    <section className="content-card destinations-card">
      <SectionHeader title={s.nav_title} eyebrow={s.nav_eyebrow} />

      {capabilities && destinations.length === 0 ? (
        <div className="panel-empty">
          <span className="panel-empty__icon"><ShieldAlert size={22} /></span>
          <strong>{s.nav_empty_title}</strong>
          <p>{s.nav_empty_body}</p>
          {pending > 0 && (
            <small>{pending} {pending === 1 ? s.nav_pending : s.nav_pending_plural}</small>
          )}
        </div>
      ) : (
        <div className="destinations-list">
          {destinations.map((destination) => (
            <a
              className="destination-row"
              key={destination.id}
              href={destination.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              <div>
                <strong>{lang === 'ar' ? destination.label_ar : destination.label_en}</strong>
                <small dir="ltr">{destination.url}</small>
              </div>
              <div className="destination-row__pills">
                {destination.auth_required && (
                  <span className="pill"><Lock size={12} /> {s.nav_auth}</span>
                )}
                <span className="pill"><MousePointerClick size={12} /> {s.nav_confirm}</span>
              </div>
              <ExternalLink size={17} />
            </a>
          ))}
          {!capabilities && <p className="empty-state">{s.status_loading}</p>}
        </div>
      )}
    </section>
  )
}
