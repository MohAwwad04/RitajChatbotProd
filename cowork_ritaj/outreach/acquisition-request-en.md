# Request for approved access to public Ritaj pages

**Status:** draft for a human to send. **Do not send without filling the bracketed
fields.** The team names, the sender, and the meeting offer are the parts an
agent cannot supply.

**To:** Birzeit University Computer Center · Registration & Admission Office
**From:** [student name(s)], [programme], Birzeit University — [email]
**Date:** [date sent]
**Subject:** Permission to use a small set of public Ritaj pages in a student assistant project

---

Dear [name / "Computer Center team"],

We are [names], [year] students in [programme] at Birzeit University. As a
course/graduation project we have built an **assistant that answers student
questions about registration, the academic calendar, and other Ritaj services**,
and cites the Ritaj page each answer came from.

This is an **independent student project. It is not an official University
service**, and it is labelled as such everywhere it appears — in the assistant's
own introduction, in its interface, and in its privacy policy. We are writing
before publishing anything, because the assistant is deliberately built so that
it cannot answer at all until someone at the University has approved the pages
it reads.

## What we are asking for

Permission to use the **text of a small number of public Ritaj pages** as the
assistant's only knowledge source, and a named person who confirms that the
content is correct and public.

These are the pages we believe we need. Each is a **question**, not an
assertion — please correct any URL that is wrong, and tell us if any of them is
not actually public:

| # | Page | URL we believe is correct | Language | Why we want it |
|---|---|---|---|---|
| 1 | Registration instructions | `https://ritaj.birzeit.edu/reg/instructions` | Arabic | Backs the most common question students ask us |
| 2 | Registration instructions | `https://ritaj.birzeit.edu/reg/instructions` | English | The English half of the same content |
| 3 | Academic calendar | `https://ritaj.birzeit.edu/academic-calendar` | Arabic | Term dates, add/drop and exam periods |
| 4 | Academic calendar (English route) | `https://ritaj.birzeit.edu/academic-calendar/en` | English | **URL unconfirmed** — we do not know the English route |
| 5 | Course browser | `https://ritaj.birzeit.edu/hemis/courses` | English | We would rather *link* students here than copy it — offerings change constantly |
| 6 | Public directory | `https://ritaj.birzeit.edu/register/` | English | **We expect you may refuse this**, and we would accept that: it lists names, and a page can be public on Ritaj and still be inappropriate to index |
| 7 | Message boards | `https://ritaj.birzeit.edu/bzu-msgs/boards` | Arabic | Announcements — only if a content owner is willing to own them |

## What we are *not* asking for

- **No student data of any kind.** The assistant has no access to any student
  account, cannot sign in on anyone's behalf, and refuses questions about
  grades, GPA, schedules or balances by design — it tells the student to sign in
  to Ritaj themselves, or to contact your office.
- **No private or sign-in-only pages.** If a page requires a login, it is out of
  scope and we will remove it from our list.
- **No automated crawling of Ritaj.** Ritaj returns a Cloudflare challenge to
  automated requests. We treat that as a decision, not an obstacle, and we have
  not attempted to work around it. That is precisely why we are writing.

## Three ways you could give us the content — whichever suits you

1. **An export or feed from the Computer Center.** The most robust option: we
   receive the page text (HTML, PDF or plain text) directly, and re-request it
   on a schedule you choose.
2. **A content owner exports the pages.** The office that owns each page sends
   us the current text, and tells us how often it changes.
3. **A reviewer saves the public pages deliberately.** Someone with a normal
   browser session opens each page, saves it, and confirms the exact canonical
   URL. Slower, but it needs nothing built.

## What "approval" means concretely

For each page we record: the exact Ritaj URL, the date the content was taken, a
checksum of the text, how often it should be re-checked, and **the name of the
person who confirmed the content is correct and public**. That name is stored
with the record. If a page changes or approval is withdrawn, we remove it and
the assistant stops answering from it — this is one configuration change, not a
rebuild.

Until at least one page is approved, the assistant answers **nothing**: it
reports that it has no sources and refers the student to your offices. That is
its current, deliberate state.

## What we would like from you

1. Confirmation (or correction) of the URLs above, and which of them are public.
2. Whichever of the three delivery routes suits you.
3. A named contact per page or per office who can approve the content — in
   practice one person for the Arabic pages and one for the English.

We are happy to demonstrate the assistant in person or over a call, including
what it refuses to do. A one-page summary is attached
(`appendix-what-it-does.md`), and we can share the source code and the safety
tests with you.

We will not publish anything to students before this approval, and we will stop
immediately if you would prefer that we did not proceed at all.

Thank you for your time,

[names]
[emails / phone]
[supervisor name, if applicable]
