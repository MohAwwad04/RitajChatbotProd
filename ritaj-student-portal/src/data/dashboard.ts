import {
  Bell,
  BookOpen,
  CalendarDays,
  CircleDollarSign,
  ClipboardCheck,
  FileChartColumn,
  FileText,
  GraduationCap,
  House,
  Library,
  Mail,
  MessageSquareText,
  Percent,
  ScrollText,
  Settings,
  ShieldCheck,
  Sparkles,
  UserRound,
  UsersRound,
  WalletCards,
} from 'lucide-react'
import type { CalendarEvent, Course, NavigationItem, QuickAction } from '../types'

export const mainNavigation: NavigationItem[] = [
  { label: 'الرئيسية', icon: House },
  { label: 'المساقات', icon: BookOpen },
  { label: 'التقويم الأكاديمي', icon: CalendarDays },
  { label: 'العلامات', icon: Percent },
  { label: 'الملف الشخصي', icon: UserRound },
]

export const serviceNavigation: NavigationItem[] = [
  { label: 'الرسائل', icon: Mail, badge: 3 },
  { label: 'السجل المالي', icon: WalletCards },
  { label: 'طلبات الدعم', icon: MessageSquareText },
]

export const quickActions: QuickAction[] = [
  { label: 'الجدول الدراسي', description: 'مواعيد المحاضرات والقاعات', icon: CalendarDays },
  { label: 'العلامات', description: 'نتائج الفصل الحالي', icon: FileChartColumn },
  { label: 'السجل الأكاديمي', description: 'كشف العلامات الرسمي', icon: GraduationCap },
  { label: 'السجل المالي', description: 'الدفعات والرصيد', icon: CircleDollarSign },
  { label: 'الرسائل', description: '3 رسائل غير مقروءة', icon: Mail, badge: 3 },
  { label: 'الخطة الدراسية', description: 'تقدم الخطة والمتطلبات', icon: ScrollText },
]

export const courses: Course[] = [
  {
    code: 'COMP 433',
    name: 'هندسة البرمجيات',
    instructor: 'د. عادل طويل',
    section: 'شعبة 2',
    time: '10:00 – 11:20',
    room: 'Masri 104',
    color: '#1f7a54',
    progress: 72,
  },
  {
    code: 'ENCS 4300',
    name: 'التدريب العملي',
    instructor: 'م. محمد حسين',
    section: 'شعبة 1',
    time: '12:30 – 01:50',
    room: 'Online',
    color: '#b88731',
    progress: 58,
  },
  {
    code: 'ENCS 4380',
    name: 'أساليب المواءمة',
    instructor: 'د. واصل غانم',
    section: 'شعبة 2',
    time: '02:00 – 03:20',
    room: 'Bamieh 202',
    color: '#3d6f9f',
    progress: 64,
  },
]

export const calendarEvents: CalendarEvent[] = [
  { day: '25', month: 'حزيران', title: 'آخر يوم تدريس', meta: 'الفصل الثاني', tone: 'red' },
  { day: '29', month: 'حزيران', title: 'امتحان هندسة البرمجيات', meta: '09:00 صباحاً', tone: 'gold' },
  { day: '04', month: 'تموز', title: 'امتحان COMP 433', meta: '11:30 صباحاً', tone: 'gold' },
  { day: '12', month: 'تموز', title: 'نهاية الامتحانات', meta: 'الفصل الثاني', tone: 'green' },
]

export const footerLinks = [
  { label: 'دليل الطالب', icon: Library },
  { label: 'الخصوصية والأمان', icon: ShieldCheck },
  { label: 'الإعدادات', icon: Settings },
]

export const utilityLinks = [
  { label: 'طلبات أكاديمية', icon: ClipboardCheck },
  { label: 'الأنظمة والتعليمات', icon: FileText },
  { label: 'مجتمع الجامعة', icon: UsersRound },
  { label: 'مزايا الطالب', icon: Sparkles },
  { label: 'التنبيهات', icon: Bell },
]
