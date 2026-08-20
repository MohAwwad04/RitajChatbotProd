import { ArrowUpLeft, ArrowUpRight, MessageSquareText } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'
import { SectionHeader } from '../ui/SectionHeader'

// Replaces QuickActions, whose six tiles ("Grades — this term's results",
// "Financial record — payments and balance", "3 unread messages") linked to
// nothing and named data the assistant refuses to look at.
//
// These four are questions the backend is *designed* to answer: public,
// procedural, and matching the candidate sources in data/sources.yaml. Until a
// corpus is published the assistant will still abstain, so the panel says so
// rather than letting a student read the refusal as a malfunction.
export function AskPanel({
  capabilities,
  onAsk,
}: {
  capabilities: Capabilities | null
  onAsk: (question: string) => void
}) {
  const { s, lang } = useI18n()
  const Arrow = lang === 'ar' ? ArrowUpLeft : ArrowUpRight
  const willAbstain = capabilities !== null && capabilities.topics.length === 0

  return (
    <section className="content-card quick-actions-card">
      <SectionHeader title={s.ask_title} eyebrow={s.ask_eyebrow} />
      <div className="quick-grid">
        {s.suggestions.map((question) => (
          <button className="quick-action" key={question} onClick={() => onAsk(question)}>
            <span className="quick-action__icon"><MessageSquareText size={21} /></span>
            <span className="quick-action__copy"><strong>{question}</strong></span>
            <Arrow className="quick-action__arrow" size={18} />
          </button>
        ))}
      </div>
      <p className="panel-note">{willAbstain ? s.ask_abstain_note : s.ask_hint}</p>
    </section>
  )
}
