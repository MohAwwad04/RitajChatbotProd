import { ArrowLeft, CalendarDays, Clock3 } from 'lucide-react'
import { calendarEvents } from '../../data/dashboard'
import { SectionHeader } from '../ui/SectionHeader'

export function UpcomingEvents() {
  return (
    <section className="content-card events-card">
      <SectionHeader title="القادم" eyebrow="المواعيد المهمة" action={<button className="icon-button subtle"><CalendarDays size={19} /></button>} />
      <div className="events-list">
        {calendarEvents.map((event) => (
          <article className="event-row" key={`${event.day}-${event.title}`}>
            <div className={`date-tile ${event.tone}`}><span>{event.month}</span><strong>{event.day}</strong></div>
            <div><strong>{event.title}</strong><small><Clock3 size={13} /> {event.meta}</small></div>
          </article>
        ))}
      </div>
      <button className="secondary-button full-button">فتح التقويم <ArrowLeft size={16} /></button>
    </section>
  )
}
