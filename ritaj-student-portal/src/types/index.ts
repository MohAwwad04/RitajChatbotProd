import type { LucideIcon } from 'lucide-react'

export type NavigationItem = {
  label: string
  icon: LucideIcon
  badge?: number
}

export type Course = {
  code: string
  name: string
  instructor: string
  section: string
  time: string
  room: string
  color: string
  progress: number
}

export type CalendarEvent = {
  day: string
  month: string
  title: string
  meta: string
  tone: 'green' | 'gold' | 'red'
}

export type QuickAction = {
  label: string
  description: string
  icon: LucideIcon
  badge?: number
}
