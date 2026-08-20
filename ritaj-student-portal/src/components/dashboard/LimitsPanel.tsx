import { KeyRound, Link2Off, ShieldQuestion, UserRoundX } from 'lucide-react'
import { useI18n } from '../../i18n'
import { SectionHeader } from '../ui/SectionHeader'

// Replaces SemesterPath (a five-milestone timeline of invented term dates).
//
// Stating the limits on the home screen is not a disclaimer bolted on for
// safety's sake — it is the product. A student who learns here that the
// assistant cannot see their grades does not spend their first three questions
// discovering it from refusals. Each row mirrors a control that exists in code:
// guardrails.check_scope for the first two, navigation.py + ADR-002 for the
// third, grounding.py's abstention for the fourth.
export function LimitsPanel() {
  const { s } = useI18n()

  const limits = [
    { icon: UserRoundX, title: s.limit_records, body: s.limit_records_body },
    { icon: KeyRound, title: s.limit_signin, body: s.limit_signin_body },
    { icon: Link2Off, title: s.limit_links, body: s.limit_links_body },
    { icon: ShieldQuestion, title: s.limit_guess, body: s.limit_guess_body },
  ]

  return (
    <section className="content-card limits-card">
      <SectionHeader title={s.limits_title} eyebrow={s.limits_eyebrow} />
      <div className="limits-grid">
        {limits.map((limit) => {
          const Icon = limit.icon
          return (
            <article className="limit-row" key={limit.title}>
              <span className="limit-row__icon"><Icon size={19} /></span>
              <div>
                <strong>{limit.title}</strong>
                <p>{limit.body}</p>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
