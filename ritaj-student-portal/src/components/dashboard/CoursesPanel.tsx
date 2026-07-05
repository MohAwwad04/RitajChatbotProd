import { ArrowLeft, Clock3, MapPin, MoreHorizontal } from 'lucide-react'
import { courses } from '../../data/dashboard'
import { SectionHeader } from '../ui/SectionHeader'

export function CoursesPanel({ query }: { query: string }) {
  const filtered = courses.filter((course) => `${course.name} ${course.code} ${course.instructor}`.toLowerCase().includes(query.trim().toLowerCase()))
  return (
    <section className="content-card courses-card">
      <SectionHeader title="مساقاتي" eyebrow="المساقات الحالية" action={<button className="text-button">عرض الكل <ArrowLeft size={15} /></button>} />
      <div className="courses-list">
        {filtered.map((course) => (
          <article className="course-row" key={course.code}>
            <span className="course-row__accent" style={{ backgroundColor: course.color }} />
            <div className="course-row__code" style={{ color: course.color }}>{course.code}</div>
            <div className="course-row__title"><strong>{course.name}</strong><small>{course.instructor} · {course.section}</small></div>
            <div className="course-row__detail"><Clock3 size={15} /><span>{course.time}</span></div>
            <div className="course-row__detail"><MapPin size={15} /><span>{course.room}</span></div>
            <div className="course-progress" aria-label={`اكتمل ${course.progress} بالمئة`}><span style={{ width: `${course.progress}%`, backgroundColor: course.color }} /></div>
            <button className="icon-button subtle" aria-label={`خيارات ${course.name}`}><MoreHorizontal size={19} /></button>
          </article>
        ))}
        {filtered.length === 0 && <p className="empty-state">لا توجد مساقات مطابقة لـ “{query}”.</p>}
      </div>
    </section>
  )
}
