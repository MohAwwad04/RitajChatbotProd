import { BookOpenCheck, Compass, Database, Hourglass } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'

// Four numbers about the *service*, replacing four about a student that the
// service has never been able to read (GPA 3.42, 108 credit hours, 5 courses,
// 240 JD outstanding). Each of these comes from /capabilities, so it is either
// true of this deployment or it is not shown.
export function StatsGrid({ capabilities }: { capabilities: Capabilities | null }) {
  const { s } = useI18n()

  const stats = [
    {
      key: 'topics',
      label: s.stat_topics,
      value: capabilities ? String(capabilities.topics.length) : '—',
      suffix: s.unit_topic,
      meta: s.stat_topics_meta,
      icon: BookOpenCheck,
    },
    {
      key: 'pending',
      label: s.stat_pending,
      value: capabilities ? String(capabilities.pending_topics) : '—',
      suffix: s.unit_page,
      meta: s.stat_pending_meta,
      icon: Hourglass,
    },
    {
      key: 'destinations',
      label: s.stat_destinations,
      value: capabilities ? String(capabilities.navigation.length) : '—',
      suffix: s.unit_destination,
      meta: s.stat_destinations_meta,
      icon: Compass,
    },
    {
      key: 'corpus',
      label: s.stat_corpus,
      value: capabilities?.corpus.version ?? s.stat_corpus_none,
      suffix: '',
      meta: capabilities?.corpus.version
        ? `${capabilities.corpus.documents ?? 0} · ${s.status_documents}`
        : s.stat_corpus_meta_none,
      icon: Database,
    },
  ]

  return (
    <section className="stats-grid" aria-label={s.status_title}>
      {stats.map((stat) => {
        const Icon = stat.icon
        return (
          <article className="stat-card" key={stat.key}>
            <div className="stat-card__icon"><Icon size={21} /></div>
            <div className="stat-card__copy">
              <span>{stat.label}</span>
              <strong>{stat.value} {stat.suffix && <small>{stat.suffix}</small>}</strong>
            </div>
            <div className="stat-card__meta">{stat.meta}</div>
          </article>
        )
      })}
    </section>
  )
}
