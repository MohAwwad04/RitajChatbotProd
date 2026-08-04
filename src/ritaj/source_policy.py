"""Source policy — provenance enforced by code, not by comments in Markdown.

The corpus this replaces was hand-written from research. Several documents cited
`www.birzeit.edu` or `koha.birzeit.edu`, some cited nothing, and several sections
were explicitly labelled `SAMPLE` placeholder text — all of it indexed and
citable, and the answer layer had no way to tell the difference. A citation is
only worth anything if something *checks* it.

So every production record must satisfy all of:

  * canonical URL is `https` and its hostname is exactly `ritaj.birzeit.edu`
    (not a subdomain of it, not `www.birzeit.edu`, not a redirect to it);
  * it is public information approved for this assistant;
  * the content was fetched or exported from Ritaj, not copied from a search
    result or a third-party page;
  * retrieval time, content hash, language, title and approval status are
    recorded, and the stored hash matches the stored content;
  * a reviewer named the approval;
  * the text carries no personal student data or credentials.

`approved: false` records are legitimate — they are the review queue. They are
simply never built into a production index. The build fails rather than skipping
a malformed record, because "quietly dropped one document" and "indexed
something nobody approved" are both worse than a red build.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# The single allowed host. Exact match — `evil-ritaj.birzeit.edu` and
# `ritaj.birzeit.edu.attacker.test` must both fail, which endswith() would not
# catch on its own.
ALLOWED_HOST = "ritaj.birzeit.edu"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SOURCES_PATH = DATA_DIR / "sources.yaml"
SNAPSHOT_ROOT = DATA_DIR / "snapshots"

LANGUAGES = {"ar", "en"}
VISIBILITIES = {"public"}          # non-public material is out of scope entirely
CONTENT_KINDS = {"html", "pdf", "markdown", "text"}
# How often a record must be re-checked against Ritaj. Drives staleness, which
# the answer layer surfaces rather than silently serving last term's deadlines.
REFRESH_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "termly": timedelta(days=120),
    "monthly": timedelta(days=31),
    "yearly": timedelta(days=365),
}

# Identity and policy fields, required of every record including those still in
# the review queue — an entry that cannot say what page it is or who owns it is
# not a queue item, it is a note.
REQUIRED_FIELDS = (
    "id", "canonical_url", "title", "language", "visibility", "content_kind",
    "owner", "refresh", "approved",
)
# Only meaningful once the content actually exists. A record awaiting
# acquisition legitimately has no snapshot, no hash and no fetch time; demanding
# them would force placeholder values, which is how "TBD" ends up in a checksum
# field and stops meaning anything.
CONTENT_REQUIRED_FIELDS = ("fetched_at", "sha256", "content_path")

# Personal data that must never enter the index. A hit quarantines the record
# for a human to look at — it does not auto-clean, because deciding that a
# number is a phone extension rather than a student id is a judgement call.
#
# The bare-number rule is deliberately broad (7-9 digits covers Birzeit student
# ids and Palestinian national ids) and will occasionally flag a phone number on
# a contact page. That is the right direction to be wrong in: a reviewer clears
# a false positive once, whereas a student id embedded in the index is a
# disclosure that citations will happily repeat.
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("id number (student/national)", re.compile(r"(?<![\d.])\d{7,9}(?![\d.])")),
    ("student email", re.compile(r"\b[\w.+-]+@student\.birzeit\.edu\b", re.I)),
    ("password literal", re.compile(r"(?i)\bpass(?:word|wd)\s*[:=]\s*\S{6,}")),
    ("payment card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
]


@dataclass
class Problem:
    """One policy violation. `fatal` decides whether a build may proceed."""

    source_id: str
    field: str
    message: str
    fatal: bool = True

    def __str__(self) -> str:
        return f"[{self.source_id}] {self.field}: {self.message}"


@dataclass
class Source:
    """One approved-or-pending knowledge record."""

    id: str
    canonical_url: str
    title: str
    language: str
    visibility: str
    content_kind: str
    owner: str
    refresh: str
    approved: bool
    fetched_at: str | None = None
    sha256: str | None = None
    content_path: str | None = None
    approved_by: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    navigation: dict | None = None
    notes: str | None = None
    raw: dict = field(default_factory=dict)

    # --- derived ------------------------------------------------------------
    def has_content(self) -> bool:
        """False for a review-queue entry that has not been acquired yet."""
        return bool(self.content_path)

    def path(self) -> Path:
        if not self.content_path:
            raise ValueError(f"source {self.id} has no content_path")
        return DATA_DIR / self.content_path

    def text(self) -> str:
        return self.path().read_text(encoding="utf-8")

    def fetched_date(self) -> date | None:
        return _parse_date(self.fetched_at)

    def stale_after(self) -> date | None:
        fetched = self.fetched_date()
        interval = REFRESH_INTERVALS.get(self.refresh)
        if fetched is None or interval is None:
            return None
        return fetched + interval

    def is_stale(self, on: date | None = None) -> bool:
        """Past its refresh cadence — needs re-checking against Ritaj."""
        deadline = self.stale_after()
        return deadline is not None and (on or _today()) > deadline

    def is_effective(self, on: date | None = None) -> bool:
        """Currently in force, per effective_from/effective_to.

        Expired records stay searchable (a student asking about last year should
        still be answered) but retrieval prefers effective ones — see
        retrieve.py. This method is the definition both rely on.
        """
        when = on or _today()
        start = _parse_date(self.effective_from)
        end = _parse_date(self.effective_to)
        if start and when < start:
            return False
        if end and when > end:
            return False
        return True


def _today() -> date:
    return datetime.now(timezone.utc).date()


def meta_is_stale(meta: dict, on: date | None = None) -> bool:
    """Staleness for a stored chunk's metadata (not a manifest record).

    Computed at answer time, never at index time: a chunk indexed inside its
    refresh window becomes stale simply by the passage of time, and an index
    rebuilt weekly would otherwise keep asserting freshness it no longer has.
    """
    fetched = _parse_date(meta.get("as_of"))
    interval = REFRESH_INTERVALS.get(meta.get("refresh", ""))
    if fetched is None or interval is None:
        return False
    return (on or _today()) > fetched + interval


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def sha256_text(text: str) -> str:
    """Hash of content as stored. Newlines normalized so a checkout on another
    platform doesn't invalidate every hash in the manifest."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# --- URL policy --------------------------------------------------------------
def check_url(url: str) -> str | None:
    """None if `url` is an acceptable canonical Ritaj URL, else why not."""
    if not url or not isinstance(url, str):
        return "missing"
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return f"unparseable ({exc})"
    if parsed.scheme != "https":
        return f"scheme must be https, got {parsed.scheme or '(none)'!r}"
    if parsed.username or parsed.password:
        return "embedded credentials are not allowed"
    host = (parsed.hostname or "").lower()
    if host != ALLOWED_HOST:
        return f"host must be exactly {ALLOWED_HOST}, got {host or '(none)'!r}"
    if parsed.port not in (None, 443):
        return f"non-standard port {parsed.port}"
    return None


def scan_pii(text: str) -> list[str]:
    """Names of PII/credential patterns found in `text` (never the values)."""
    return [label for label, pattern in _PII_PATTERNS if pattern.search(text)]


# --- manifest loading + validation -------------------------------------------
def load_manifest(path: Path | None = None) -> list[dict]:
    """Read data/sources.yaml. Missing file = empty manifest (not an error)."""
    path = path or SOURCES_PATH
    if not path.exists():
        return []
    import yaml  # noqa: PLC0415 — optional dep, only needed when a manifest exists

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list of source records")
    return data


def parse(record: dict) -> tuple[Source | None, list[Problem]]:
    """Turn one manifest entry into a Source, collecting structural problems."""
    sid = str(record.get("id") or "<no id>")
    problems = [
        Problem(sid, f, "required field is missing")
        for f in REQUIRED_FIELDS
        if record.get(f) is None
    ]
    if problems:
        return None, problems
    known = {f.name for f in Source.__dataclass_fields__.values()} - {"raw"}
    source = Source(**{k: v for k, v in record.items() if k in known}, raw=record)
    return source, []


def validate(source: Source, *, check_content: bool = True) -> list[Problem]:
    """Every policy violation for one record. Empty list = it may be indexed."""
    problems: list[Problem] = []

    def bad(field_name: str, message: str, fatal: bool = True) -> None:
        problems.append(Problem(source.id, field_name, message, fatal))

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", source.id):
        bad("id", "must be lowercase kebab-case, 3-64 chars")

    url_problem = check_url(source.canonical_url)
    if url_problem:
        bad("canonical_url", url_problem)

    if source.language not in LANGUAGES:
        bad("language", f"must be one of {sorted(LANGUAGES)}")
    if source.visibility not in VISIBILITIES:
        bad("visibility", f"must be one of {sorted(VISIBILITIES)}")
    if source.content_kind not in CONTENT_KINDS:
        bad("content_kind", f"must be one of {sorted(CONTENT_KINDS)}")
    if source.refresh not in REFRESH_INTERVALS:
        bad("refresh", f"must be one of {sorted(REFRESH_INTERVALS)}")

    # Only a *present* value has to parse. Absence is handled by the
    # approved-record check below: a queue entry has nothing to date yet.
    if source.fetched_at and source.fetched_date() is None:
        bad("fetched_at", "must be an ISO-8601 date/datetime")
    if source.effective_from and _parse_date(source.effective_from) is None:
        bad("effective_from", "must be an ISO-8601 date")
    if source.effective_to and _parse_date(source.effective_to) is None:
        bad("effective_to", "must be an ISO-8601 date")
    start, end = _parse_date(source.effective_from), _parse_date(source.effective_to)
    if start and end and end < start:
        bad("effective_to", "is before effective_from")

    if source.approved:
        if not source.approved_by:
            bad("approved_by", "an approved record must name who approved it")
        for missing in (f for f in CONTENT_REQUIRED_FIELDS if not getattr(source, f)):
            bad(missing, "required once a record is approved for indexing")
    elif source.has_content():
        # Pending record that *does* have a snapshot: still worth checking, but
        # a problem here can't block a build it isn't part of.
        pass

    if source.navigation:
        problems.extend(_validate_navigation(source))

    if check_content and source.has_content():
        content_problems = _validate_content(source)
        if not source.approved:
            # Downgrade: an unapproved record is not in any production index, so
            # its problems are review notes, not build failures.
            content_problems = [
                Problem(p.source_id, p.field, p.message, fatal=False)
                for p in content_problems
            ]
        problems.extend(content_problems)

    return problems


def _validate_navigation(source: Source) -> list[Problem]:
    nav = source.navigation or {}
    out: list[Problem] = []
    for key in ("id", "label_ar", "label_en", "destination"):
        if not nav.get(key):
            out.append(Problem(source.id, f"navigation.{key}", "required"))
    destination = nav.get("destination", "")
    if destination:
        problem = check_url(destination)
        if problem:
            out.append(Problem(source.id, "navigation.destination", problem))
    return out


def _validate_content(source: Source) -> list[Problem]:
    out: list[Problem] = []
    path = source.path()
    if not path.is_file():
        out.append(Problem(source.id, "content_path", f"no file at {source.content_path}"))
        return out
    try:
        text = source.text()
    except (OSError, UnicodeDecodeError) as exc:
        out.append(Problem(source.id, "content_path", f"unreadable: {exc}"))
        return out
    if not text.strip():
        out.append(Problem(source.id, "content_path", "file is empty"))
        return out

    actual = sha256_text(text)
    if source.sha256 in ("", "TBD", None):
        out.append(Problem(source.id, "sha256", f"not recorded (content hashes to {actual})"))
    elif actual != source.sha256:
        out.append(Problem(
            source.id, "sha256",
            f"content changed since approval (recorded {source.sha256[:12]}…, "
            f"now {actual[:12]}…) — re-review before indexing",
        ))

    found = scan_pii(text)
    if found:
        out.append(Problem(source.id, "content", f"possible personal data: {', '.join(found)}"))

    # A source that reads as instructions to the model is an injection vector,
    # whether it was planted or written carelessly. Flag, don't auto-edit.
    from . import guardrails  # noqa: PLC0415 — avoids a circular import at module load

    if guardrails._INJECTION.search(text):
        out.append(Problem(source.id, "content", "contains instruction-override text"))

    return out


@dataclass
class ManifestReport:
    sources: list[Source]
    approved: list[Source]
    problems: list[Problem]

    @property
    def ok(self) -> bool:
        return not any(p.fatal for p in self.problems)

    def summary(self) -> str:
        lines = [
            f"{len(self.sources)} record(s), {len(self.approved)} approved, "
            f"{len(self.problems)} problem(s)"
        ]
        lines += [f"  {p}" for p in self.problems]
        return "\n".join(lines)


def load_and_validate(path: Path | None = None, *, check_content: bool = True) -> ManifestReport:
    """Parse + validate the whole manifest.

    `approved` contains only records that are both approved AND clean — the
    exact set a production index may be built from.
    """
    records = load_manifest(path)
    sources: list[Source] = []
    problems: list[Problem] = []
    seen_ids: set[str] = set()
    seen_urls: dict[str, tuple[str, bool]] = {}  # url -> (owning id, approved)

    for record in records:
        source, structural = parse(record)
        if source is None:
            problems.extend(structural)
            continue
        if source.id in seen_ids:
            problems.append(Problem(source.id, "id", "duplicate id"))
            continue
        seen_ids.add(source.id)
        # Two records claiming the same canonical URL means at least one cites a
        # page it isn't — a student following the citation lands somewhere that
        # doesn't say what they were told. Fatal only once both are approved
        # (i.e. both would be indexed); in the review queue it is a note for
        # whoever resolves the language split.
        previous = seen_urls.get(source.canonical_url)
        if previous is not None:
            other_id, other_approved = previous
            problems.append(Problem(
                source.id, "canonical_url", f"duplicate of {other_id}",
                fatal=source.approved and other_approved,
            ))
        else:
            seen_urls[source.canonical_url] = (source.id, source.approved)
        sources.append(source)
        problems.extend(validate(source, check_content=check_content))

    bad_ids = {p.source_id for p in problems if p.fatal}
    approved = [s for s in sources if s.approved and s.id not in bad_ids]
    return ManifestReport(sources=sources, approved=approved, problems=problems)
