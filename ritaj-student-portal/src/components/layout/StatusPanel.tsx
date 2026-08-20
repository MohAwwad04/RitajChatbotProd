import { CircleAlert, CircleCheck, CircleDashed, RotateCw, X } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'

type Props = {
  open: boolean
  onClose: () => void
  capabilities: Capabilities | null
  error: string | null
  onRetry: () => void
}

// Replaces NotificationsPanel, which showed three invented notifications
// ("your registration slot opens tomorrow", "a payment was added to your
// account", "your advisor approved your plan") to a product that has no student
// account to notify anyone about. What a student can usefully be told instead is
// whether the assistant is able to answer at all right now.
export function StatusPanel({ open, onClose, capabilities, error, onRetry }: Props) {
  const { s } = useI18n()

  const state = error
    ? { icon: CircleAlert, tone: 'is-error', text: s.status_unreachable }
    : !capabilities
      ? { icon: CircleDashed, tone: 'is-pending', text: s.status_loading }
      : capabilities.ready
        ? { icon: CircleCheck, tone: 'is-ok', text: s.status_ready }
        : { icon: CircleAlert, tone: 'is-pending', text: s.status_not_ready }
  const StateIcon = state.icon

  return (
    <aside className={`notifications-panel ${open ? 'is-open' : ''}`} aria-hidden={!open}>
      <div className="notifications-panel__head">
        <div>
          <span className="eyebrow">{s.status_eyebrow}</span>
          <h2>{s.status_title}</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label={s.aria_close_panel}>
          <X size={20} />
        </button>
      </div>

      <div className={`status-line ${state.tone}`}>
        <StateIcon size={20} />
        <strong>{state.text}</strong>
      </div>

      <dl className="status-facts">
        <div>
          <dt>{s.status_corpus_version}</dt>
          <dd>{capabilities?.corpus.version ?? s.status_none}</dd>
        </div>
        <div>
          <dt>{s.status_documents}</dt>
          <dd>{capabilities?.corpus.documents ?? 0}</dd>
        </div>
        <div>
          <dt>{s.status_chunks}</dt>
          <dd>{capabilities?.corpus.chunks ?? 0}</dd>
        </div>
        <div>
          <dt>{s.stat_topics}</dt>
          <dd>{capabilities?.topics.length ?? 0}</dd>
        </div>
        <div>
          <dt>{s.stat_destinations}</dt>
          <dd>{capabilities?.navigation.length ?? 0}</dd>
        </div>
      </dl>

      {capabilities && !capabilities.ready && <p className="panel-note">{s.status_abstain_note}</p>}

      <button className="secondary-button full-button" onClick={onRetry}>
        <RotateCw size={16} /> {s.status_retry}
      </button>
    </aside>
  )
}
