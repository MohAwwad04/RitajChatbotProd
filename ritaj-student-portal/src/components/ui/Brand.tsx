import { GeneratedIcon } from './GeneratedIcon'
import { useI18n } from '../../i18n'

export function Brand({ compact = false }: { compact?: boolean }) {
  const { s } = useI18n()
  return (
    <div className={`brand ${compact ? 'brand--compact' : ''}`} aria-label={s.aria_brand}>
      <span className="brand__mark"><GeneratedIcon name="graduation" size={24} /></span>
      {!compact && (
        <span className="brand__copy">
          <strong>{s.brand_name}</strong>
          <small>{s.brand_sub}</small>
        </span>
      )}
    </div>
  )
}
