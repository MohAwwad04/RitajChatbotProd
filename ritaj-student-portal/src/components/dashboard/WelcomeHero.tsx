import { ArrowLeft, ArrowRight, Info, MessageSquareText, Sparkles } from 'lucide-react'
import type { Capabilities } from '../../api/capabilities'
import { useI18n } from '../../i18n'

type Props = {
  capabilities: Capabilities | null
  onAsk: () => void
  onTopics: () => void
}

// The hero used to greet a student by name ("صباح الخير، براء") and tell them
// their registration slot opened tomorrow. Both were invented. What replaces
// them is the one thing the product can say without knowing anything about the
// person reading it: what it does, where its answers come from, and that it is
// not an official university service.
export function WelcomeHero({ capabilities, onAsk, onTopics }: Props) {
  const { s, lang } = useI18n()
  const Arrow = lang === 'ar' ? ArrowLeft : ArrowRight
  const topics = capabilities?.topics.length ?? 0
  const chunks = capabilities?.corpus.chunks ?? 0

  return (
    <section className="welcome-hero">
      <div className="welcome-hero__content">
        <span className="hero-label"><Sparkles size={15} /> {s.hero_eyebrow}</span>
        <h1>{s.hero_h1}</h1>
        <p>{s.hero_p}</p>
        <div className="hero-actions">
          <button className="primary-button" onClick={onAsk}>
            <MessageSquareText size={18} /> {s.hero_cta} <Arrow size={17} />
          </button>
          <button className="ghost-button" onClick={onTopics}>
            <Info size={18} /> {s.hero_secondary}
          </button>
        </div>
        <p className="hero-disclaimer">{s.unofficial}</p>
      </div>

      {/* The dial shows the corpus, not a semester: how many approved topics
          back the answers today. Zero is a real, honest reading. */}
      <div className="corpus-dial" aria-label={`${s.stat_topics}: ${topics}`}>
        <strong>{topics}</strong>
        <span>{s.stat_topics}</span>
        <small>{chunks ? `${chunks} · ${s.status_chunks}` : s.topics_empty_title}</small>
      </div>
    </section>
  )
}
