import type { LucideIcon } from 'lucide-react'

// The views this build can render. `privacy` opens the served policy page
// (GET /privacy) rather than a client-side route, so the portal and the
// extension always show the same document.
export type ViewId = 'home' | 'ask' | 'topics' | 'open' | 'status' | 'privacy'

export type NavigationItem = {
  id: ViewId
  label: string
  icon: LucideIcon
}

// `Course`, `CalendarEvent` and `QuickAction` used to live here. They typed a
// student record the product has no access to; deleting the types keeps a future
// component from re-introducing the fiction just because a shape was handy.
