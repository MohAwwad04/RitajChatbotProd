import type { ReactNode } from 'react'

type Props = {
  title: string
  eyebrow?: string
  action?: ReactNode
}

export function SectionHeader({ title, eyebrow, action }: Props) {
  return (
    <div className="section-header">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  )
}
