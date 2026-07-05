import { Check, Flag, GraduationCap } from 'lucide-react'
import { SectionHeader } from '../ui/SectionHeader'

const milestones = [
  { label: 'بداية الفصل', date: '21 كانون الثاني', state: 'done' },
  { label: 'الامتحان النصفي', date: '14 نيسان', state: 'done' },
  { label: 'نهاية التدريس', date: '25 حزيران', state: 'current' },
  { label: 'الامتحانات النهائية', date: '27 حزيران', state: 'next' },
  { label: 'نهاية الفصل', date: '12 تموز', state: 'next' },
]

export function SemesterPath() {
  return (
    <section className="content-card semester-path-card">
      <SectionHeader title="مسار الفصل" eyebrow="الفصل الثاني 2025/2026" action={<button className="text-button">التقويم الكامل</button>} />
      <div className="semester-path">
        <div className="semester-path__line"><span /></div>
        {milestones.map((item, index) => (
          <div className={`milestone ${item.state}`} key={item.label}>
            <span className="milestone__dot">
              {item.state === 'done' ? <Check size={14} /> : index === milestones.length - 1 ? <Flag size={14} /> : <GraduationCap size={15} />}
            </span>
            <strong>{item.label}</strong>
            <small>{item.date}</small>
          </div>
        ))}
      </div>
    </section>
  )
}
