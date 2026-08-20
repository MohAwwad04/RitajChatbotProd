import { ExternalLink, FileWarning, Inbox, RefreshCw } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'
import { SectionHeader } from '../ui/SectionHeader'

// Replaces CoursesPanel, which listed three invented courses with instructors,
// rooms and progress bars. This lists the approved Ritaj pages the assistant may
// answer from — the honest equivalent of "what is in here" — and links each one
// to its canonical page so a student can check the assistant against the source.
export function TopicsPanel({
  capabilities,
  query,
}: {
  capabilities: Capabilities | null
  query: string
}) {
  const { s } = useI18n()
  const needle = query.trim().toLowerCase()
  const topics = (capabilities?.topics ?? []).filter((topic) =>
    `${topic.title} ${topic.url}`.toLowerCase().includes(needle),
  )
  const pending = capabilities?.pending_topics ?? 0

  return (
    <section className="content-card topics-card">
      <SectionHeader title={s.topics_title} eyebrow={s.topics_eyebrow} />

      {capabilities && capabilities.topics.length === 0 ? (
        // The empty state is the most important state this component has: today
        // it is the only one that renders. It must read as a deliberate policy,
        // not as a broken fetch.
        <div className="panel-empty">
          <span className="panel-empty__icon"><Inbox size={22} /></span>
          <strong>{s.topics_empty_title}</strong>
          <p>{s.topics_empty_body}</p>
          {pending > 0 && (
            <small>
              {pending} {pending === 1 ? s.topics_pending_note : s.topics_pending_note_plural}
            </small>
          )}
        </div>
      ) : (
        <div className="topics-list">
          {topics.map((topic) => (
            <article className="topic-row" key={topic.id}>
              <span className={`lang-chip ${topic.language}`}>{topic.language.toUpperCase()}</span>
              <div className="topic-row__title">
                <strong>{topic.title}</strong>
                <small dir="ltr">{topic.url}</small>
              </div>
              <div className="topic-row__meta">
                {topic.stale ? (
                  <span className="pill pill--warn"><FileWarning size={13} /> {s.topics_stale}</span>
                ) : (
                  <span className="pill"><RefreshCw size={13} /> {s.topics_refresh} · {topic.refresh}</span>
                )}
              </div>
              <a
                className="icon-button subtle"
                href={topic.url}
                target="_blank"
                rel="noreferrer noopener"
                aria-label={`${s.topics_open}: ${topic.title}`}
              >
                <ExternalLink size={18} />
              </a>
            </article>
          ))}
          {capabilities && topics.length === 0 && (
            <p className="empty-state">{s.topics_none_matching}</p>
          )}
          {!capabilities && <p className="empty-state">{s.status_loading}</p>}
        </div>
      )}
    </section>
  )
}
