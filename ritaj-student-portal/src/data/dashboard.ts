import {
  Compass,
  House,
  ListChecks,
  MessageSquareText,
  ShieldCheck,
  Activity,
} from 'lucide-react'
import type { Strings } from '../i18n'
import type { NavigationItem, ViewId } from '../types'

// The portal's views.
//
// What used to live in this file: a named student, three invented courses with
// instructors and rooms, a GPA, a 240 JD balance, four exam dates and a nav rail
// promising "Grades" and "Financial record". None of it existed — the backend
// has no student-record access at all and declines to look, so every one of
// those screens was a promise the product could not keep. The rail below lists
// only views this build can actually render, and every label is bilingual
// because the assistant answers in both languages.
export const views = (s: Strings): NavigationItem[] => [
  { id: 'home', label: s.view_home, icon: House },
  { id: 'ask', label: s.view_ask, icon: MessageSquareText },
  { id: 'topics', label: s.view_topics, icon: ListChecks },
  { id: 'open', label: s.view_open, icon: Compass },
]

export const aboutViews = (s: Strings): NavigationItem[] => [
  { id: 'status', label: s.view_status, icon: Activity },
  { id: 'privacy', label: s.view_privacy, icon: ShieldCheck },
]

// The bottom bar on phones. Deliberately the same ids as the rail — a tab that
// leads somewhere the sidebar cannot reach is how two navigations drift apart.
export const mobileViews: ViewId[] = ['home', 'ask', 'topics', 'open', 'status']
