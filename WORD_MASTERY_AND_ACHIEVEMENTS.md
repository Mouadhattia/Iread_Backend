# Word mastery & achievements

How iRead decides that a learner *knows* a word, and how that decision drives
every badge, certificate, streak and progress bar in the product.

This document is the reference for the whole feature. It spans four repos:

| Repo | Role in this feature |
| --- | --- |
| `Iread_Backend` | Owns the data model, the mastery rule, the achievement engine, and every read endpoint. **All logic lives here.** |
| `iReadGames` | Produces evidence. Every game posts one attempt per word. |
| `IREAD_FRONT` | Reader-facing surfaces: post-game recap, My Words, Trophy Room, Passport, dashboard streak. |
| `Dashboard-iread-last-version` | Admin/teacher surfaces: Word Review, Word Suggestions, Reader Progress. |

---

## 1. The strategy, in one page

**The problem.** "Did the learner learn this word?" has no single observable
answer. A child can guess a word from three visible letters, or recall it
because they saw it 40 seconds ago in the same puzzle. Counting correct
answers measures puzzle-solving, not vocabulary.

**The adopted strategy — mastery is proved by *corroboration*, not by
repetition.** A word only counts as mastered when the learner has produced it:

1. in **two different games** (two different retrieval shapes — spelling it,
   recognising it, recalling it from a definition), *and*
2. on **two different days** (defeats short-term recall), *and*
3. at least once with **no hints at all** (defeats guessing).

No single one of those is sufficient, and none of them can be substituted by
doing more of another. Ten clears of the same word in the same game on the same
day still leave it un-mastered. This is deliberately hard to game and it is the
core of the whole feature.

**Four supporting principles**, each of which shows up repeatedly in the code:

- **Never invent a level.** A word whose CEFR level is unknown stays *unresolved*
  forever rather than being defaulted into a band. Unresolved words are shown to
  the learner but excluded from every band statistic and completion check.
- **Evidence is append-only.** `word_progress_evidence` records every clear;
  the stage on `word_progress` is a *derived cache* recomputed from that log.
  The rule can therefore be changed later and re-run over history.
- **Practice and Daily Run are worth exactly the same.** The mode is recorded
  but never affects stage, pips, or mastery. Only the competitive *ranking*
  (leaderboard, one-play-per-day) is daily-run-only, and that lives in an
  entirely separate table.
- **Progress belongs to the learner, not the school.** Word progress,
  achievements and certificates are keyed on `user_id` alone. They survive a
  school change, a school closure, or leaving the platform's B2B side entirely.

**Scope boundary (decided explicitly, don't re-litigate):** mastery evidence
comes *only* from the four word games. Reading a book or an audiobook is
upstream — it is where vocabulary comes from and where the learner is exposed
to words — but it never advances a stage, never fires an achievement, and never
touches a streak. Wiring reading actions into the achievement pipeline was
proposed and rejected. Keep reading-completion flags (e.g. "story finished")
visibly distinct from vocabulary mastery; they will disagree often, and that is
correct.

---

## 2. Architecture at a glance

```
   ADMIN AUTHORING                 VOCABULARY SUBSTRATE
   ┌────────────────┐              ┌──────────────────────────────┐
   │ Book_text.text │──ingest────► │ word_sense   (lemma+POS+CEFR)│
   │ (per book)     │  (spaCy)     │ chapter                      │
   └────────────────┘              │ word_occurrence (sense↔chap) │
   ┌────────────────┐              └──────────────┬───────────────┘
   │ CEFR-J CSV     │──ingest────►                │ resolve
   └────────────────┘                             │ surface form
                                                  │
   GAMEPLAY                                       ▼
   ┌────────────────┐   POST /api/word-attempt   ┌──────────────────┐
   │ iReadGames     │───────────────────────────►│ progress_engine  │
   │ 4 games ×      │   (per word, per clear)    │  submit_attempt()│
   │ 2 modes        │                            └────────┬─────────┘
   └────────────────┘                                     │ writes
                                                          ▼
                                       ┌───────────────────────────────┐
                                       │ word_progress_evidence (log)  │
                                       │ word_progress   (derived)     │
                                       │ user_streak                   │
                                       │ user_achievement              │
                                       │ certificate                   │
                                       └───────────┬───────────────────┘
   SURFACES                                        │ GET /reader/*
   ┌───────────────────────────────────────────────▼─────────────────┐
   │ IREAD_FRONT: recap overlay · My Words · Trophy Room · Passport   │
   │ Dashboard:   Reader Progress (admin/teacher, read-only)          │
   │ Mobile app:  achievement cards on the reader "me" screen         │
   └──────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1 — the vocabulary substrate

Three tables, added by migration `f3c8a1d92b56` (*word data cefr layer*).

### `word_sense` — [models/word_sense.py](models/word_sense.py)

One row per **lemma + POS + sense_key**, unique on that triple. `sense_key` is
always `''` today: senses are resolved to lemma+POS only, because the CEFR
source itself is keyed that way. True sense-level disambiguation is left for a
future sense-aware source; the column exists so that change is additive.

Level resolution has a strict precedence and a strict "unknown" state:

```python
effective_cefr_level = cefr_override_level or cefr_level      # admin wins
is_unresolved        = not proper_noun_excluded and effective_cefr_level is None
```

- `cefr_level` / `cefr_source` — from the ingested CEFR file.
- `cefr_override_level` / `_note` / `_by` / `_at` — a human decision, always wins.
- `proper_noun_excluded` — a permanent editor-confirmed "this is a name, it will
  never have a level". Excluded words are **not** counted as unresolved and are
  never folded into a band.
- `definition` / `synonyms` / `example_sentence` — dictionary enrichment.
  **These are schema-complete but essentially empty in practice** — see §12.

### `chapter` + `word_occurrence`

`chapter` splits a book; `word_occurrence` records "this sense appears in this
chapter", keeping the printed `surface_form` and (where available) an
`example_line`. Occurrences are what let a raw string from a game be resolved
back to a sense.

**Every book currently has exactly one chapter, titled "Full text"**
([apps/word_ingestion.py:42](apps/word_ingestion.py#L42)). Real chapter
splitting does not exist. The consequence is documented in the code and matters
for achievements: *Chapter Master* and *Book Conqueror* necessarily fire at the
same moment. The completion logic is written per-chapter so this stops being
true the day chapters are split for real — no engine change needed.

### Ingestion

Two idempotent, re-runnable scripts. Both are **manual** — nothing calls them
automatically (verified: `ingest_book_vocabulary_list` has no caller outside
its script).

```bash
# 1. CEFR levels. Safe to re-run; a level from a different source is reported
#    as a conflict, never silently overwritten.
python scripts/ingest_cefr_source.py --source cefrj-vocabulary-profile-1.5.csv --tag cefrj-1.5

# 2. Book vocabulary → senses + occurrences. Run for every new book.
python scripts/ingest_book_vocabulary.py --book-id 27
python scripts/ingest_book_vocabulary.py --all
```

The CEFR source in use is **CEFR-J 1.5, which covers A1–B2 only**. The companion
Octanove C1/C2 file has never been loaded, so C1 and C2 words resolve to
*unresolved* — which is the designed-for behaviour, not a bug, but it does mean
the C1/C2 band achievements and certificates are unreachable in practice today.

Book ingestion runs `Book_text.text` through spaCy (POS-tag + lemmatize) and
creates an **unresolved** sense when the CEFR file has no match, rather than
guessing a level.

> **Known data-quality ceiling.** For most books `Book_text.text` is a curated
> one-term-per-line vocabulary list, not prose. spaCy needs sentence context to
> tag correctly, so on bare title-cased lines it over-tags common nouns as
> `PROPN`. Those words land in the safe *unresolved* bucket rather than getting
> a wrong level — a coverage cap, not a corruption risk. Real prose does exist
> in `AudioBookPage.official_text` for books with a synchronised audiobook and
> would be a much better tagging source (and would give real `example_line`
> values); ingesting from it is an open follow-up.

### What the games actually receive — and why it is *not* this table

This is the single most counter-intuitive part of the design, so it is spelled
out here.

Games do **not** receive word-sense objects. They receive plain strings:

- Modern path — `GET /reader/get_book_games/<book_id>/<game_type>` serves the
  **admin-authored `words` list on the game-calendar entry**
  ([apps/game_calendar.py](apps/game_calendar.py) `get_player_game_payload`).
- Legacy path — `GET /reader/get_book_games/<book_id>` whitespace-splits
  `Book_text.text` and returns `{'words': [...], 'deprecated': True}`.

A cutover to rich payloads was **explicitly decided against**: 26 call sites
across 5 iReadGames files treat `words` as a `string[]` (`.length`,
`.includes()`, positional indexing), so swapping in objects would be a breaking
change to a live endpoint rather than an additive one. More importantly nothing
needs it — the engine re-resolves the string itself.

Resolution happens server-side in
[`resolve_word_sense_for_book()`](apps/progress_engine.py#L73):

1. exact case-insensitive `surface_form` match on a `word_occurrence` in that
   book's chapters, else
2. a lemma-only `word_sense` fallback (`sense_key=''`), else
3. `404 WORD_NOT_RESOLVED`.

**Operational consequence:** if a book was never ingested, or an admin typed a
calendar word that appears nowhere in `Book_text.text`, every attempt on that
word 404s. The client swallows the error by design (see §5), so the failure is
*silent* — the reader plays normally and no progress is recorded. If a book
shows zero word progress, check ingestion first.

If richer per-word data is ever wanted in-game (CEFR badges, real hints), build
an **additive opt-in** endpoint (e.g. `GET /reader/word-metadata`) games call to
enrich what they already have. Never replace the `words: string[]` contract.

---

## 4. Layer 2 — how a word becomes mastered

Tables from migration `a4d7f1c9b358` (*word progress and achievements*), in
[models/word_progress.py](models/word_progress.py).

### The four stages

| Stage | Meaning | Condition (as implemented) |
| --- | --- | --- |
| `encountered` | The word has been put in front of the learner. | A `word_progress` row exists. Created on the **first attempt of any kind**, including a wrong one. |
| `guessed` | Produced correctly at least once, but only with help. | ≥1 evidence row, and none of the `known` conditions met. |
| `known` | Produced without help, or produced repeatedly. | ≥1 unaided clear **OR** ≥2 evidence rows **OR** ever typed from memory. |
| `mastered` | Corroborated. | **≥2 distinct sources AND ≥2 distinct days AND ≥1 unaided clear.** |

The exact code is [`_recompute_stage()`](apps/progress_engine.py#L174):

```python
is_known    = has_unaided or len(evidence_rows) >= 2 or typed_from_memory_ever
is_mastered = len(sources) >= 2 and len(days) >= 2 and has_unaided
```

Notes that matter:

- **Stages never regress.** The stage is recomputed from the whole evidence log
  on every correct attempt, and the log only grows. `first_guessed_at`,
  `first_known_at` and `mastered_at` are stamped once and never cleared.
- **A "source" is a game key or `typed_from_memory`** — the four game keys are
  `bee-genius`, `word-explorer`, `think-word`, `intellect-link`. Two clears in
  the *same* game are one source, no matter how many days apart.
- **A "day" is `occurred_on`**, a date, defaulting to the server's today.
- **"Unaided" means `hints_used == 0`** on that specific evidence row.
- **An incorrect attempt writes no evidence.** It creates the `word_progress`
  row (so the word shows as *encountered* in My Words) and nothing else. This
  is how words a learner struggles with get on the shelf at all: all four games
  post `correct: false` for words shown but never found before the round ended.

### The evidence log — `word_progress_evidence`

One append-only row per **correct** clear:

| Column | Purpose |
| --- | --- |
| `source` | game key, or `typed_from_memory` |
| `mode` | `daily` \| `practice` — **recorded, never used in any rule** |
| `occurred_on` | date, drives the "2+ days" test |
| `hints_used` | integer; `0` is what "unaided" means |
| `heaviest_hint_tier` | `light` \| `medium` \| `heavy` \| `NULL` |

`word_progress` caches `distinct_sources_count`, `distinct_days_count`,
`has_unaided_clear` and `consecutive_no_hint_clears` off this log so read paths
don't re-aggregate. The log is the source of truth; the cache is disposable.

### Pips — the visible mechanic

Four booleans on `word_progress`, one per game:

```python
if not from_memory and hints_used == 0:
    setattr(progress, PIP_FIELD_BY_GAME[game], True)
```

A pip lights **only for a hint-free clear in that game**. Pips drive:

- the 4-dot word coin in My Words,
- `pip_count >= 3` → *Triple Threat*,
- all four → *Master of All Trades*,
- the near-miss nudge (`games_remaining = 4 - pip_count`).

> ⚠️ **Pips are not the mastery rule.** Mastery needs 2 sources / 2 days /
> 1 unaided — a word can be `mastered` at 2 pips, and a 4-pip word earned
> entirely in one day is *not* mastered. Pips are a "which games have you
> beaten this word in" collectible, nothing more.
>
> Reader-facing copy used to state the opposite (*"Fill all four pips to master
> a word"*, and a recap nudge computed as `4 - pip_count`). **Fixed 2026-08-07**
> — see §9. Anything new that talks to the reader about mastery must describe
> the three requirements, never the pips.

### The hint ladder

Three weighted tiers, `light` → `medium` → `heavy`. Each game maps its own
ad-hoc hint mechanic onto them
([iReadGames/client/src/lib/word-attempts.ts](../iReadGames/client/src/lib/word-attempts.ts)):

| Game (code key) | Product name | Hint mechanic in that game | Mapped tier |
| --- | --- | --- | --- |
| `think-word` | Think Word | definition reveal | `light` |
| `bee-genius` | Bee Genius / "Letter Bee" | full-word reveal | `heavy` |
| `intellect-link` | Intellect Link / "Letter Links" | full-word reveal | `heavy` |
| `word-explorer` | Word Explorer | 1: direction · 2: first-letter position | `light`, `medium` |

Bee Genius and Intellect Link are mapped `heavy` because the UI reveals the
**whole word**, despite their toast copy claiming "first letter". The misleading
copy is a known open item; the tier mapping is the honest one.

The tier only affects one achievement (*Meaning Master*, which requires a clear
whose heaviest hint was `light`). Everything else keys off `hints_used == 0`.

### Daily Run vs Practice

Both modes call the **same** `submit_attempt()` with the same arguments and
produce identical progress. What differs sits entirely outside this engine:

| | Daily Run | Practice |
| --- | --- | --- |
| Word progress / pips / mastery | identical | identical |
| Streak | counts | counts |
| Achievements | fire | fire |
| Result row | `Game_result`, **upserted, one row per user/day/game/book** — this uniqueness is exactly what the leaderboard depends on | `PracticePlay`, appended, unlimited per day |
| Leaderboard / ranking | yes | no |

### Worked example

Book 27, one word, `bicycle`:

| # | Event | Evidence written | Resulting stage |
| --- | --- | --- | --- |
| 1 | Think Word, hint used, cleared | `think-word`/day 1/hints=1/light | `guessed` |
| 2 | Bee Genius, no hint, cleared, **same day** | `bee-genius`/day 1/hints=0 | `known` — 2 sources but only 1 day |
| 3 | Word Explorer, no hint, cleared, **next day** | `word-explorer`/day 2/hints=0 | `mastered` ✅ |

At step 3 the response carries `newly_mastered: true`, and the same call fires
*Steel Trap* (first mastered word), *No Hints*, *Meaning Master* (step 1 was a
`light`-only clear), *First A1 Word*, and — if this was the learner's only
tracked A1 word — *A1 Cleared* plus an **A1 certificate**.

---

## 5. The write path, end to end

```
game page (8 of them: 4 games × 2 modes)
  └─ submitWordAttempt({bookId, word, game, mode, correct,
                        hintsUsed, heaviestHintTier, fromMemory, userId})
       └─ POST /api/word-attempt          (iReadGames Express proxy)
            └─ POST /reader/word-attempt  (Iread_Backend)
                 └─ submit_attempt()
                      1. validate game / mode / hint tier
                      2. resolve surface form → word_sense
                      3. get-or-create word_progress   (stage=encountered)
                      4. if correct: append evidence, light pip, recompute stage
                      5. commit
                      6. update streak                 (runs even if incorrect)
                      7. if correct: evaluate achievements
                      8. issue certificates from whatever just unlocked
                      9. find nearest near-miss
```

The response is what the recap is built from:

```json
{
  "word_sense_id": 7799, "lemma": "bicycle", "stage": "mastered",
  "stage_advanced": true, "pip_count": 3, "newly_mastered": true,
  "cefr_level": "A1",
  "streak": {"current_streak": 4, "best_streak": 4,
             "grace_available": true, "welcome_back": false},
  "unlocked_achievements": [{"key": "steel_trap", "tier": 1, "threshold": 10}],
  "new_certificates": [...],
  "nearest_near_miss": {"lemma": "wheel", "pip_count": 3, "games_remaining": 1}
}
```

**Failures are swallowed on purpose.** `submitWordAttempt` catches and logs;
telemetry must never interrupt a child's win screen. The cost is that a
misconfigured book fails silently (§3).

**Client-side accuracy notes** worth knowing before touching the game pages:

- Think Word's daily page keeps a running hint total for the whole day's pack.
  A `hintsAtWordStartRef` snapshot is taken at each word transition so hints are
  attributed to the word they were actually spent on.
- Bee Genius / Intellect Link clear their `revealedWord` state the instant the
  hinted word is found, so "was this word hinted" must be read from the
  component's pre-update closure at the correct-word branch — which is why
  `revealedWord` appears in those `useCallback` dependency arrays.

---

## 6. Streaks

`user_streak`, one row per user, shared across both modes.
[`_update_streak()`](apps/progress_engine.py#L211) runs on **every** attempt,
correct or not — playing at all counts as showing up.

| Gap since last play | Result |
| --- | --- |
| same day | no change |
| 1 day | `current_streak += 1` |
| 2 days **and** grace available | `current_streak += 1`, grace consumed |
| 2 days, no grace | reset to 1 |
| >2 days | reset to 1 |
| >3 days | reset to 1, and `welcome_back: true` in the response |

Grace replenishes 30 days after it was used (`GRACE_REPLENISH_DAYS`). The design
intent is stated in the code: *never punish a single lapse*. `best_streak` is a
high-water mark and is never reduced.

---

## 7. Achievements

`user_achievement`, unique on `(user_id, achievement_key, tier)`. Two
consequences follow from that constraint and from
[`_award_if_new()`](apps/progress_engine.py#L415):

- **Never awarded twice.**
- **Never revoked.** Nothing in the codebase deletes a `user_achievement`. A
  band you cleared stays cleared even after you encounter new words in it (§7.3).

Evaluation runs on every *correct* attempt, recomputes every metric, and awards
anything newly satisfied. It is idempotent — safe to run as often as you like.

### 7.1 Tiered achievements

| Key | Title ladder | Thresholds | Metric |
| --- | --- | --- | --- |
| `word_collector` | Word Collector → … → Lexicon Master | 10 / 50 / 100 / 500 / 1000 | words at `guessed` or better |
| `steel_trap` | Steel Trap I–IV | 10 / 50 / 100 / 500 | words `mastered` |
| `triple_threat` | Triple Threat I–III | 5 / 25 / 100 | words with ≥3 pips |
| `clean_run` | Clean Run I–III | 5 / 15 / 40 | best `consecutive_no_hint_clears` on any word |
| `on_a_roll` | On a Roll I–IV | 3 / 7 / 30 / 100 | current streak, in days |
| `word_wizard` | Word Wizard I–III | 10 / 50 / 100 | size of the "I already know" shelf |
| `well_read` | Well Read I–III | 3 / 5 / 10 | books fully mastered |

Tiers are awarded independently, so a jump past several thresholds at once
unlocks all of them in the same response.

### 7.2 Single-fire achievements

| Key | Title | Condition |
| --- | --- | --- |
| `master_of_all_trades` | Master of All Trades | one word cleared hint-free in **all four** games |
| `no_hints` | No Hints | any clear with zero hints |
| `meaning_master` | Meaning Master | any clear whose heaviest hint was `light` (meaning only, no letters) |
| `its_a_hint_now` | It's a Hint Now! | **hook exists, never fires** — `award_hint_reused()` is waiting on a hint generator that sources synonyms from learners' own mastered words |

### 7.3 CEFR band achievements

Two per band, for all six of A1…C2:

- `first_word_in_<level>` — first mastered word in that band.
- `band_cleared_<level>` — every tracked word in that band mastered.

**The band roll-up is scoped to words the learner has personally encountered**
([`get_band_rollup()`](apps/progress_engine.py#L259)) — not to the whole
catalogue. `A2 Cleared` therefore means *"every A2 word you have met is
mastered"*, which is achievable early with a handful of words and then stays
earned as the learner meets more A2 words. That is a deliberate consequence of
using the personal roll-up (a catalogue-wide denominator would make the badge
unreachable for everyone), but it does mean the badge is a *milestone*, not a
standing claim of proficiency. Worth keeping in mind before it is used as a
placement signal.

Unresolved and proper-noun-excluded words are excluded from every band count.
And since only A1–B2 are loaded (§3), **the C1/C2 badges are currently
unreachable**.

### 7.4 Book / chapter achievements

`chapter_master_<chapter_id>` and `book_conqueror_<book_id>`, from
[`get_book_completion()`](apps/progress_engine.py#L282): a chapter is complete
when **every leveled word occurring in it is mastered**. Unleveled words are
excluded — a book full of unresolved proper nouns is still completable. A
chapter with *no* leveled words is never complete (so it can't be a free win).

`get_achievement_status()` enriches these with the book title and
`mastered / total` counts, so the trophy shelf can show which book is closest
to done rather than N identical cards.

### 7.5 Deliberately *not* persisted

*Daily Goal* (`get_daily_goal_status()`, default 5 distinct words/day) and
*Welcome Back* (>3-day gap) are **computed flags, not badges**. Reasoning: the
"never award the same achievement twice" rule doesn't fit something meant to
recur every time it naturally recurs. This is an interpretation call, flagged
here in case product disagrees.

`{Game} Specialist` was never implemented — the brief itself frames it as
open-ended.

---

## 8. Certificates & the Reading Passport

[apps/certificates.py](apps/certificates.py), migration `e5f8c1a2d740`.

Certificates are the durable, printable form of two milestones:

| Kind | Trigger | Serial |
| --- | --- | --- |
| `cefr_band` | `band_cleared_<level>` | `IRP-<user>-<LEVEL>` |
| `book_mastery` | `book_conqueror_<book>` | `IRP-<user>-B<book>` |

Unlike achievements they carry a serial and an issue date, and **a certificate
never references a school** — like the rest of the passport it belongs to the
learner and survives school changes and closures.

Issuance is idempotent via a `(user_id, milestone_key)` unique constraint, which
allows two complementary paths: a cheap one inside `submit_attempt()` that maps
the already-computed `unlocked` list onto certificates with no extra queries,
and a reconciling `issue_certificates_for_user()` used when the passport is
viewed or backfilled. Neither can double-issue.

---

## 9. The near-miss — the retention lever

[`find_nearest_near_miss()`](apps/progress_engine.py) returns the word closest
to mastery. It is attached to **every** attempt response and to the progress
summary, and it is what the recap overlay and the mobile home card render.

Candidates are non-mastered words with **at least one correct clear**
(encountered-only words are excluded — they aren't near anything). They are
ranked by **how many of the three mastery requirements are still missing**,
tie-broken by pip count, and the payload names the gap explicitly:

```json
"nearest_near_miss": {
  "lemma": "appreciation", "stage": "known", "pip_count": 2,
  "distinct_sources_count": 2, "distinct_days_count": 1,
  "needs_new_game": false, "needs_new_day": true, "needs_unaided_clear": false,
  "next_step": "new_day",
  "requirements_met": 2, "requirements_total": 3, "requirements_remaining": 1
}
```

`next_step` is the single most useful instruction, chosen by what the learner
can act on **right now**: `new_game` → `unaided_clear` → `new_day`. Switching
game and dropping hints are both doable this minute (and clearing in a new game
hint-free satisfies two requirements at once); coming back tomorrow is not, so
`new_day` is only ever returned when it is the sole remaining requirement.
Clients render one sentence per `next_step` value and a `met / total` bar.

> **Changed 2026-08-07.** This previously ranked by `pip_count` and reported
> `games_remaining = 4 - pip_count`. Two bugs fell out of that. It mis-ordered:
> on a real reader (user 260) it surfaced *appreciation* — which needed **no**
> further games, only a second day — with the message *"Just 2 more games to
> master it"*, ahead of six words that genuinely were one game away. And it
> **hid** every word whose clears had all been hinted (`pip_count == 0`), even
> one hint-free clear from mastering: 4 of that reader's 20 candidates could
> never be surfaced at all. `games_remaining` is retained as a deprecated alias
> of `requirements_remaining` so older clients keep rendering a sane number.

---

## 10. API surface

### Write (`Iread_Backend`, unauthenticated-tolerant — `user_id` in body)

| Endpoint | Purpose |
| --- | --- |
| `POST /reader/word-attempt` | One word, one clear or miss. The only way progress is ever created. |
| `POST /reader/self-reported-word` | Add a word to the "I already know" shelf. |

`iReadGames` reaches these through its own Express proxy
(`POST /api/word-attempt`), mirroring the existing `/api/save-result` pattern.
`IREAD_FRONT` calls `Iread_Backend` **directly** — it needs no proxy.

### Read (`?user_id=` or the session user)

| Endpoint | Returns |
| --- | --- |
| `GET /reader/word-progress/summary` | guessed/mastered counts, band roll-up, streak, near-miss, shelf count |
| `GET /reader/achievements` | full catalog with earned/locked + progress-to-next-tier |
| `GET /reader/word-collection` | flat per-word list (lemma, surface form, level, stage, pips, book/chapter) |
| `GET /reader/words-i-know` | the self-reported shelf |
| `GET /reader/passport` | identity + schools + reading history + progress + achievements + certificates |
| `GET /reader/certificates` | issued certificates |

### Admin / teacher

| Endpoint | Who | Purpose |
| --- | --- | --- |
| `GET /admin/word-senses` | school admin, super admin, content manager | list/filter/search word data (school-scoped via occurrences → chapter → book) |
| `GET /admin/word-senses/quality` | same | resolved / unresolved rate |
| `PUT /admin/word-senses/<id>` | direct for super admin + content manager; school admin gets **403 `MUST_SUGGEST`** on CEFR/proper-noun | edit levels + dictionary fields — **currently 500s for everyone, see §14.0** |
| `POST /admin/word-senses/<id>/suggest` | school admin | propose a CEFR level or proper-noun exclusion |
| `GET /admin/word-suggestions` | super admin, content manager | review queue, grouped by word |
| `POST /admin/word-suggestions/<id>/approve` \| `/reject` | super admin, content manager | approving supersedes competing siblings |
| `GET /admin/settings` | super admin, content manager | read the `require_dictionary_approval` toggle |
| `PUT /admin/settings` | **super admin only** (explicit in-body check) | write the toggle |
| `GET /admin/reader-progress` | school admin, super admin, content manager | per-reader summary rows, school-scoped |
| `GET /teacher/reader-progress` | teacher, assistant, admin, super admin | same rows, read-only |

Access to the `/admin/*` routes above is granted by the blueprint-wide
`@admin.before_request` gate plus the `@content_endpoint` decorator, which
registers a route as reachable by the platform-wide **content manager** role.
`can_manage_content()` (= super admin **or** content manager) is the
"may edit platform content directly" predicate; `is_super_admin()` remains the
gate for tenants, users, revenue, storage and the audit log.

> **Identity gotcha, learned the hard way.** `user_id` on all of these is the
> **MySQL integer `User.id`**. `IREAD_FRONT`'s `getAuthenticatedReaderId()`
> returns `quiz_id` — a Mongo ObjectId string from the external quiz service —
> which is correct for quiz call sites and *wrong* for every endpoint here.
> Use `user?.id` directly. The backend now returns a clean
> `400 INVALID_USER_ID` instead of a 500 when a non-numeric id arrives.

---

## 11. Surfaces, by audience

### Reader — `IREAD_FRONT`

| Surface | Path / file | What it shows |
| --- | --- | --- |
| Post-game recap | [GameRecapOverlay.js](../IREAD_FRONT/src/components/marketing/student/GameRecapOverlay.js) | words guessed, hints used, newly-unlocked achievements, streak (+ "new record"), near-miss with progress bar |
| My Words | `/student/my-words/` · [WordCollection.js](../IREAD_FRONT/src/components/marketing/student/WordCollection.js) | word coins grouped A1–C2 + an *Unleveled* bucket, per-level mastered/total bar, 4 pips per word, checkmark when mastered |
| Trophy Room | `/student/trophies/` · [TrophyRoom.js](../IREAD_FRONT/src/components/marketing/student/TrophyRoom.js) | badge shelf, locked badges visible, grouped by category |
| Passport | [Passport.js](../IREAD_FRONT/src/components/marketing/student/Passport.js) | cross-school learner record + certificates |
| Dashboard streak | `ReaderDashboard.js` hero row | current streak next to the CEFR chip |

**How the recap knows what unlocked.** Threading rich per-attempt data through
a `postMessage` bridge across 8 game files was rejected as fragile. Instead:

1. `Games.js` snapshots `/reader/achievements` **before** the reader enters the
   iframe (`collectEarnedKeys`).
2. iReadGames posts a *lightweight* `iread-game-recap` message on completion —
   game, mode, words guessed, hints used, outcome. Nothing else.
3. The parent re-fetches achievements + summary and **diffs** against the
   snapshot (`diffNewlyUnlocked`) to find what is genuinely new this session.

**Double-dialog handling.** Every game already opens its own modal on game-over
inside the iframe, at the same trigger. So:
- practice pages **suppress** their native `GameResultModal` when embedded
  (`isEmbeddedInParentFrame()`) — the parent recap covers everything it showed;
- daily pages **keep** their `DailyLeaderboardDialog` (it shows the day's
  ranking, which the recap doesn't have) and **defer** posting the recap until
  the reader dismisses it (`useDeferredDailyRecap`, which waits for a real
  open→close transition, since the dialog starts closed).

### Admin / teacher — `Dashboard-iread-last-version`

Routes and their guards are declared in
[src/layouts/AllRoutes.js](../Dashboard-iread-last-version/src/layouts/AllRoutes.js)
— *not* in `DashboardRoutes.js`, which only holds nav.

| Page | Route | Guard | Roles |
| --- | --- | --- | --- |
| Word Review | `/dashboard/word-review` | `adminOrSuperAdminRoute` | school admin, super admin, content manager |
| Word Suggestions | `/dashboard/word-suggestions` | `platformContentRoute` | super admin, content manager |
| Reader Progress | via Games nav | `quizManagementRoute` | teacher, assistant, school admin, super admin, content manager |

`ReaderProgress.js` calls `/admin/reader-progress` first and falls back to
`/teacher/reader-progress` on 401, so one component serves all four roles.

> `DashboardRoutes.js` has **four independent nav arrays** — `DashboardMenu`
> (school admin), `DashboardSuperAdmin`, `DashboardTeacher`, `DashboardAssistant`.
> Adding a page to one does not add it to the others, and a route guard is
> separate again from the nav entry. Both have caused real "invisible page"
> bugs in this feature.

### Mobile — `iread-mobile-app`

Achievement cards on the reader "me" screen
([src/api/achievements.ts](../iread-mobile-app/src/api/achievements.ts)).
`toAchievementView()` exists because `/reader/achievements` returns **two
different shapes in the same array** — tiered entries (`tiers[]`, no top-level
`title`/`earned`) and single-fire entries (`title`/`earned`, no `tiers`).
Handling only the tiered shape made every single-shot achievement report "All
tiers complete" next to an unearned star. Any new client must handle both.

---

## 12. Governance of word data

School admins can see the vocabulary behind their own books but cannot
unilaterally change what a word *means* platform-wide, because there is one
global `word_sense` row shared by every school. The workflow
(migration `c8a3e5f1d962`):

| Change | School admin | Super admin / content manager |
| --- | --- | --- |
| CEFR level, proper-noun exclusion | **always suggest** (`403 MUST_SUGGEST` on direct PUT) | direct |
| Definition, synonyms, example | direct by default; becomes a suggestion when `PlatformSettings.require_dictionary_approval` is on | always direct |

Flipping `require_dictionary_approval` itself is **super-admin only** — a
content manager can read `/admin/settings` but not write it.

- A pending suggestion is visible as *provisional* **only to the suggesting
  school** — achieved by scoping visibility (`serialize_word_sense(...,
  viewer_school_id=)`), not by forking the data.
- Competing suggestions from different schools are shown **side by side**,
  grouped by word. Approving one **supersedes** every other pending sibling for
  the same `(word_sense, suggestion_type)` pair.
- Approving anything writes to the single global `WordSense` row. There is no
  per-school override layer.
- Because band roll-ups are always a live query, resolving a word takes effect
  immediately — **no history recompute is needed**.

Both directions are notified in-app (no email), reusing the pre-existing
`ReaderNotification` system: `notify_word_suggestion_submitted` → all super
admins; `notify_word_suggestion_reviewed` → the original suggester, with the
reviewer's note on rejection.

---

## 13. Operations

### Migration chain

```
e1a5f7c3d9b4 → f3c8a1d92b56  word data cefr layer      (word_sense, chapter, word_occurrence)
             → a4d7f1c9b358  word progress + achievements
             → c8a3e5f1d962  word suggestions + platform settings
   ...       → e5f8c1a2d740  reader certificates
```

See [MIGRATIONS.md](MIGRATIONS.md) for how migrations are applied in this
project.

### Adding a new book (checklist)

1. Create the book and populate `Book_text.text`.
2. **Run `python scripts/ingest_book_vocabulary.py --book-id <id>`.** Nothing
   does this automatically. Skip it and the games still work, but every word
   attempt 404s silently and the book contributes zero progress.
3. Check the resolved/unresolved split on `/dashboard/word-review` filtered to
   that book; resolve or exclude the stragglers.
4. When authoring game-calendar word lists, use surface forms that actually
   appear in `Book_text.text` — the calendar list and the occurrence table are
   populated independently and only agree if you make them agree.

### Diagnosing "a reader has no progress"

In order of likelihood:

1. Book never ingested → no occurrences → every attempt 404s.
2. Calendar words don't match ingested surface forms → same.
3. Client sending `quiz_id` instead of `User.id` → `400 INVALID_USER_ID`.
4. Multi-school reader with no school context → the daily-run path 400s with
   `SCHOOL_CONTEXT_REQUIRED` before any word is played (`Games.js` must pass
   `school_id` into the iframe URL).

---

## 14. Known gaps and open items

Ranked roughly by impact. All verified against the current code.

### 0. 🔴 Live defect — `PUT /admin/word-senses/<id>` 500s on every call

Found 2026-08-07 while writing this document, by static analysis of
`apps/admin/routes.py`; not previously known.

Commit `5003e8c` *"Adding admin content assistant"* (2026-08-03) renamed the
predicate at the top of `update_word_sense()`:

```python
-        super_admin = is_super_admin()
+        direct_editor = can_manage_content()
```

but left its **four downstream uses** on the old name — lines 11550, 11561,
11587 and 11589 still read `super_admin`, which is now defined neither in the
function nor at module scope. The first of those runs unconditionally, right
after the `get_json()` call, so **every** request to this route raises
`NameError: name 'super_admin' is not defined`, is swallowed by the function's
blanket `except Exception`, and comes back as
`500 {"message": "Internal server error", "error": "..."}`.

Impact: this is the *only* route that writes a CEFR level, a proper-noun
exclusion, or dictionary content. So since 2026-08-03, Word Review's "set
level", "mark proper noun" and "Edit details" actions have been dead for every
role — super admin, content manager and school admin alike (the school-admin
`suggest` route is separate and unaffected, as are all read endpoints). This
also means gap #2 below is currently *absolute*: there is no working path at
all, manual or automatic, for a definition to enter the system.

Fix: rename the four `super_admin` references to `direct_editor`. That matches
the refactor's evident intent — all four are the "may edit platform content
directly" test, which is exactly what `can_manage_content()` computes.

### Everything else

1. ~~**Pips vs the mastery rule disagree in reader-facing copy.**~~ **Fixed
   2026-08-07.** `find_nearest_near_miss()` now ranks by real requirements and
   returns a `next_step`; the recap, the My Words page (which now states the
   rule outright) and the mobile home card all render it; en/fr/ar strings
   added for the `game_recap.*` and `word_collection.*` namespaces, which had
   been running on English `defaultValue` fallbacks. See §9.
2. **Dictionary enrichment has no data.** `definition` / `synonyms` /
   `example_sentence` have existed since the first migration, but no ingestion
   step populates them — the CEFR load doesn't, book ingestion doesn't. The only
   real dictionary lookups anywhere are iReadGames' server-side
   `api.dictionaryapi.dev` fetch (`server/storage.ts`, in-memory cache, feeds
   Think Word's one hint tier and is never persisted) and the admin
   `GET /admin/define` WordNet endpoint, a stateless lookup that also writes
   nothing back. Manual entry through Word Review is the *only* path for a
   definition to exist — **and it is currently broken, see §14.0**.
3. **`from_memory` is built but never sent.** The engine supports it, the
   payload type declares it, and no game ever passes it. Bee Genius / Intellect
   Link's existing "non-themed word" mechanic is the natural fit and this is
   pure client wiring — the highest-leverage remaining item.
4. **No real chapters.** One "Full text" chapter per book, so Chapter Master and
   Book Conqueror always fire together.
5. **C1/C2 are unreachable.** The Octanove C1/C2 CEFR file has never been
   loaded, so those bands, their badges and their certificates cannot be earned.
6. **`get_book_completion()` scans every chapter in the database** on every
   correct attempt, lazy-loading `occurrence.word_sense` per occurrence — and
   `get_achievement_status()` calls it **twice** (once directly, once through
   the `well_read` metric). This is the hot spot to watch as the catalogue
   grows; the mastered-set fetch has already been optimised, the chapter scan
   has not.
7. **The lemma-only resolution fallback ignores POS.** When no occurrence row
   matches, `WordSense.query.filter_by(lemma=..., sense_key='')` returns an
   arbitrary POS row, so evidence can attach to the wrong sense of a word.
8. **`its_a_hint_now` can never fire** — its hook is waiting on a hint generator
   that doesn't exist.
9. **Collection views:** only *By level* shipped. *By book*, *List (closest to
   mastered)* and *Swarm* were specified and deferred.
10. **Recap gaps:** no CEFR breakdown, no daily-run ranking block (the ranking
    data exists in iReadGames but is never threaded through).
11. **i18n:** the newer reader pages (My Words, Trophy Room, Passport) rely on
    English `defaultValue` fallbacks rather than real fr/ar translations.
