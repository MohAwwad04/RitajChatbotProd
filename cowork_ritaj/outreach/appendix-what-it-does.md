# Appendix — what the assistant does, and what it refuses

One page to attach to the acquisition request. Approvers respond better to a
demonstration than to a description, and the refusals are the part that answers
the question they actually have: *what could go wrong if we say yes?*

Every behaviour below is enforced by code and covered by a test — the file that
enforces it is named so a technical reader at the Computer Center can check the
claim rather than take it.

---

## In one sentence

A student asks a question in Arabic or English; the assistant searches **only
approved public Ritaj pages**, and either answers with the source named, or says
it does not know and points to the right office.

## What it does

| Behaviour | Enforced by |
|---|---|
| Answers only from approved pages whose canonical URL is exactly `ritaj.birzeit.edu` | `src/ritaj/source_policy.py`, `scripts/check_corpus_policy.py` (build fails otherwise) |
| Names the source page with each answer, and checks that the answer is actually supported by it | `src/ritaj/grounding.py`, `citations.py` |
| Says "I don't know" rather than guessing when no approved page supports the answer | `src/ritaj/generate.py` (abstention), red-team suite |
| Works in Arabic and English, including Arabic spelling and diacritic variation | `src/ritaj/arabic.py` |
| Flags an answer whose source is past its re-check window as possibly out of date | `source_policy.meta_is_stale` |
| Can offer a button that opens a **pre-approved** Ritaj page — never automatically, always after a click | `data/navigation.yaml`, `docs/adr/ADR-002` |

## What it refuses

| Refusal | Why it matters to you |
|---|---|
| **Any personal record** — grades, GPA, schedule, financial balance | It has no access to any student account and cannot sign in for anyone. It says the limitation is permanent and refers the student to Registration & Admission or Finance. |
| **Producing a URL** | The language model is never allowed to output a link. It can only name an identifier of a destination already reviewed and approved; the browser extension re-checks the destination independently before opening it. |
| **Acting inside Ritaj** | It navigates; it never submits a form, registers a course, or changes anything. |
| **Content that is not approved** | Twenty-two documents from the project's earlier version were quarantined because their source was `www.birzeit.edu` or a search result rather than Ritaj. None of them ships. |
| **Prompt-injection from page content** | Instructions embedded in indexed text are detected and stripped rather than followed. |

## What it keeps

- **No names.** The portal asks for no name and sends none. An earlier version
  did, and it was removed because the privacy policy said otherwise.
- **Aggregate logs only** by default: counts, response times, error codes, which
  source was cited, and whether the answer was grounded. Question and answer
  text are not stored.
- The privacy policy is served by the application itself, and a build check
  fails if it stops matching what the code does.

## Its state today

The assistant is complete and tested, and **answers nothing**, because no page
has been approved yet. It reports "not ready" and abstains. That is the state
this request exists to change — and it is also the safest possible default while
we wait.

---

*Contact: [names, email]. Source code and the safety test suite can be shared on
request.*
