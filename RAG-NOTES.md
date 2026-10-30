# Vector DB & Agent Notes

Design decisions for ingesting this corpus and filtering retrieval by
tradition. Update this file when the conventions change.

## Doc metadata contract

Every `docs/*.md` file carries YAML front matter:

```yaml
---
title: "..."
author: "..."
tradition: "reformed"    # single value — see vocabulary
genre: "treatise"        # single value — see vocabulary
covers: ["Rev"]          # commentaries only — OSIS books/ranges
translator: "..."        # optional
edition: "..."           # optional
source: "..."
---
```

**`tradition` and `genre` are always single strings.** We deliberately
did NOT make them lists. These fields answer "what *is* this work?" —
the question of "who should *see* it?" belongs to the retrieval
filter, not the doc.

## Tradition vocabulary

Controlled values (defined in `.devin/skills/txt-to-md-rag/SKILL.md`):

| value | meaning |
|---|---|
| `early-church` | pre-schism patristic (roughly pre-1054) — shared heritage |
| `medieval` | medieval Latin West, pre-Reformation — shared heritage |
| `catholic` | Roman Catholic, post-Reformation |
| `orthodox` | Eastern Orthodox |
| `anglican` | Church of England / Anglican communion |
| `lutheran` | Lutheran |
| `reformed` | Reformed, Presbyterian, Puritan |
| `reformed-baptist` | Calvinistic / Particular Baptist |
| `baptist` | other Baptist |
| `congregationalist` | Congregationalist |
| `arminian` | Arminian / Remonstrant, non-Wesleyan |
| `methodist` | Wesleyan / Methodist / Holiness |
| `anabaptist` | Anabaptist |
| `dispensationalist` | Dispensationalist |
| `restorationist` | Stone-Campbell / Disciples of Christ / Churches of Christ |
| `liberal-protestant` | Liberal/mainline Protestant |
| `evangelical` | broad evangelical, when nothing else fits |
| `other` | catch-all |

## Tagging rules

1. **Pre-schism works get the era label, not a later communion.**
   Augustine → `early-church` (not `catholic`). Aquinas, Anselm,
   Catherine of Siena → `medieval` (not `catholic`). They are shared
   heritage claimed by multiple traditions.

2. **Tag the work's theology, not the author's biography, when they
   differ.** Cross's *Theology of Schleiermacher* → `liberal-protestant`
   (the content is Schleiermacher). Upham's *Felon's Maxims* →
   `catholic` (the content is Fénelon; Upham only edited/translated).
   Bullinger → `dispensationalist` despite Anglican ordination.

3. **Straddlers get a granular vocab value, not two tags.** Spurgeon →
   `reformed-baptist`, not `["reformed", "baptist"]`. If a new
   straddler appears, extend the vocabulary rather than multi-tagging.

## Genre vocabulary

| value | meaning |
|---|---|
| `systematic` | systematic / dogmatic theologies |
| `treatise` | focused theological monographs, works collections |
| `commentary` | scripture commentaries — see `covers` below |
| `sermon` | sermons & sermon collections (incl. discourses) |
| `devotional` | meditations, prayers, practical piety |
| `catechism` | catechisms & catechism expositions |
| `history` | church history, history of doctrine |
| `biography` | lives, autobiographies, memoirs |
| `apologetics` | apologetic works |
| `illustration` | sermon illustration collections |
| `letters` | correspondence collections |
| `liturgy` | prayer books, liturgies, orders of service |
| `reference` | bibliographies, dictionaries, guides |
| `other` | catch-all |

Genre calls on fuzzy cases follow "tag what the work *is*": Charnock's
and Flavel's published discourses are `sermon` (preached), Baxter's
evangelistic books are `treatise` (written as books), *Confessions* is
`biography`, Spurgeon's commentary guide is `reference`.

## Scripture references (commentaries)

For `genre: "commentary"` docs, pericope-level metadata is the most
valuable retrieval signal for sermon prep ("what do commentators say
on Romans 8:28?"). Convention:

- Doc-level: `covers: [...]` — OSIS book codes or ranges for the whole
  volume (`["Rev"]`, `["Matt 13–28"]`, `["Exod", "Lev", "Num",
  "Deut"]`). Book-granular is fine when exact ranges aren't known.
- Section-level: headings for commented passages carry the range in
  OSIS form — `### Rom 8:18–25`, optionally with the book's own title
  after an em dash (`### Rom 8:18–25 — Future Glory`).
- At ingest, the splitter parses headings and attaches a
  `scripture_refs` list to each chunk. Agents can then query
  `scripture_refs intersects "Rom 8"` — plan the DB schema for
  per-chunk ref arrays, not just doc-level `covers`.

## Retrieval model

**Embeddings do the finding; `tradition` only does the excluding.**
The field contributes nothing to semantic similarity — it is purely a
filter gate and a provenance label.

Per-client filters are **inclusion lists**, and every Western client
should include the shared-heritage labels:

```python
FILTERS = {
    "reformed":  ["reformed", "reformed-baptist", "congregationalist",
                  "early-church", "medieval"],
    "anglican":  ["anglican", "early-church", "medieval"],
    "catholic":  ["catholic", "early-church", "medieval"],
    "lutheran":  ["lutheran", "early-church", "medieval"],
    "methodist": ["methodist", "arminian", "early-church", "medieval"],
    "baptist":   ["baptist", "reformed-baptist", "early-church",
                  "medieval"],
}
```

(Tune per client — e.g. whether `arminian`/`finney` belongs in a
Reformed client's visible set is a product decision.)

Genre filters compose with tradition filters: an illustration agent
uses `genre: "illustration"`, a commentary agent uses
`genre: "commentary"` + `scripture_refs intersects <passage>`, a
"models of preaching" agent uses `genre: "sermon"`.

### Filtering posture

Genre is **opt-in**, not a default gate. Metadata never affects
embedding similarity — it only excludes. So:

- Default queries run unfiltered by genre (client tradition filter
  only).
- Apply a genre filter only when the query clearly targets a genre —
  and use inclusive sibling lists: "preaching models" →
  `["sermon", "devotional"]`; "doctrinal depth" → `["systematic",
  "treatise", "catechism", "commentary"]`.
- Fallback: if a genre-filtered query returns thin results, retry
  without it. Granular tags can always be unioned; false exclusion is
  the failure mode to avoid.
- Inject `author`/`genre`/`tradition` into chunk context headers at
  ingest so agents see provenance in unfiltered results too.

## If agents generate filters dynamically

Put the mapping in the retrieval tool's description/system prompt —
one paragraph in one place — rather than multi-tagging docs:

> When filtering by tradition, always include `early-church` and
> `medieval` alongside the communion label; they are shared heritage.
> For `reformed` also include `reformed-baptist` and
> `congregationalist`. For `methodist` also include `arminian`.

## Why single-value, not multi-tag

- Client-side inclusion lists already deliver shared-heritage recall;
  redundant tags on every doc would duplicate that mapping across the
  corpus and drift over time.
- Overlapping tags hurt precision — `["catholic", "reformed"]` on
  Augustine would surface him when a user asks for *distinctively*
  Reformed perspectives.
- Adding a new client tradition = editing one filter list, not
  re-tagging the corpus.

## Current corpus distribution

(as of 2026-10-09, 253 docs — includes the gen-COM commentary batch)

By tradition:

| tradition | count |
|---|---|
| reformed | 136 |
| anglican | 27 |
| baptist | 22 |
| congregationalist | 10 |
| liberal-protestant | 9 |
| methodist | 6 |
| medieval | 6 |
| lutheran | 6 |
| evangelical | 5 |
| early-church | 5 |
| arminian | 5 |
| restorationist | 4 |
| dispensationalist | 4 |
| catholic | 4 |
| reformed-baptist | 3 |
| other | 1 |

By genre:

| genre | count |
|---|---|
| commentary | 125 |
| treatise | 61 |
| sermon | 28 |
| devotional | 11 |
| history | 10 |
| systematic | 7 |
| reference | 4 |
| catechism | 3 |
| apologetics | 3 |
| biography | 1 |

Still thin: `catholic` (4), `orthodox` (0), `anabaptist` (0),
`illustration` (0), `liturgy` (0), `biography` (1).

## gen-COM batch notes (2026-10-09)

- 194 sources fetched; 37 were scan-only editions (image placeholders,
  no OCR) and were removed — recorded in `fetch_ccel.py` `DUPLICATES`
  so re-runs skip them. Darby's Synopsis has no plain-text edition.
- Barnes' individual NT volumes are scan-only, but
  `barnes-barnes-new-testament-notes` (22MB) contains the whole set.
- `white-acts-of-the-apostles` (Ellen G. White, SDA) was in the genre
  list — tagged `other`; remove if unwanted.
- Heading OSIS normalization: `tools/normalize_headings.py` handles
  full book names → codes, JFB abbrevs (`Ge 1:1` → `Gen 1:1`), spaced
  caps (`G E N E S I S` / `M a T T H E W`), `Psalm N — v` → `Ps N:v`,
  `Book Chapter N` → `Book N`, roman→arabic, en dashes, and book-context
  tracking for `Chapter N` headings — opt-in per file via `CHAPTER_CTX`
  (only chapter-by-chapter commentaries: Jamieson, Barnes NT, Henry
  vols I–VI, Leupold). `tools/tag_frontmatter.py` holds the
  tradition/genre/covers maps so a reconverted doc can be retagged.
- Known residual gaps: `gray_jm-cwc` and `henry-concise` keep bare
  `Chapter N` headings — their book dividers aren't reliably detectable
  (wrong-book labels are worse than none). `bennett-jeremiah-ii` and
  similar Expositor's Bible vols use *commentary* chapter numbers that
  don't equal Bible chapters — covers + inline refs only.
  Some files carry raw `[N]` footnote leftovers (largest: schaff-psalms
  1059, smith_ga-isaiah-ii 529, nave 4366 — dictionary entry markers).

## Gutenberg re-source batch (2026-10-09)

- 71 works re-sourced from Project Gutenberg: `tools/fetch_gutenberg.py`
  (PG ebook ids) + `tools/convert_gutenberg.py` (txt→md). `source:`
  front matter and the attribution block now point to gutenberg.org.
- Not converted: `barnes-barnes-new-testament-notes` — PG has only the
  Revelation volume (#55228), not the full NT set; stays on CCEL.
- `aquinas-summa-theologica` — PG publishes Parts I, I-II, II-II, III
  only; the posthumous Supplement (Q.91+) is not on Gutenberg and is
  absent from the new doc (~87% of former word count).
- `augustine-confessions` — the PG Pusey edition has no chapter-level
  headings in the source; `### Chapter N` markers were inserted at the
  standard chapter boundaries (aligned to the former CCEL doc's
  paragraph openers — same Pusey translation).
- `boethius-theological-tractates` — doc is now bilingual (Loeb Latin +
  English interleaved per numbered section), matching the PG source.
