## @file
# @brief The word-progress and achievement engine (Achievement & Word-Progress
# System brief). Both daily-run and practice modes call submit_attempt() —
# the mode never affects stage, pips, or mastery, only a separate daily-run
# ranking that lives entirely outside this module.
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from extensions import db
from models.book import Book
from models.chapter import Chapter
from models.word_occurrence import WordOccurrence
from models.word_progress import (
    GAME_KEYS,
    STAGE_ENCOUNTERED,
    STAGE_GUESSED,
    STAGE_KNOWN,
    STAGE_MASTERED,
    SelfReportedWord,
    UserAchievement,
    UserStreak,
    WordProgress,
    WordProgressEvidence,
)
from models.word_sense import WordSense

PIP_FIELD_BY_GAME = {
    'bee-genius': 'pip_bee_genius',
    'word-explorer': 'pip_word_explorer',
    'think-word': 'pip_think_word',
    'intellect-link': 'pip_intellect_link',
}

HINT_TIERS = ('light', 'medium', 'heavy')
TYPED_FROM_MEMORY = 'typed_from_memory'
CEFR_LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')

DEFAULT_DAILY_WORD_GOAL = 5
WELCOME_BACK_GAP_DAYS = 3
GRACE_REPLENISH_DAYS = 30

WORD_COLLECTOR_TIERS = (10, 50, 100, 500, 1000)
STEEL_TRAP_TIERS = (10, 50, 100, 500)
TRIPLE_THREAT_TIERS = (5, 25, 100)
CLEAN_RUN_TIERS = (5, 15, 40)
ON_A_ROLL_TIERS = (3, 7, 30, 100)
WORD_WIZARD_TIERS = (10, 50, 100)
WELL_READ_TIERS = (3, 5, 10)


class AttemptError(ValueError):
    def __init__(self, message, code, status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def attempt_error_response(error):
    return {'message': error.message, 'code': error.code}, error.status_code


def _today():
    return date.today()


# ---------------------------------------------------------------------------
# Word-sense resolution
# ---------------------------------------------------------------------------

def resolve_word_sense_for_book(book_id, surface_form):
    """Games today only know a book_id + a raw word string — resolve that to
    the word-sense it was ingested as (Phase 1's occurrences). Falls back to
    a direct lemma match if no occurrence row exists yet."""
    surface_form = (surface_form or '').strip()
    if not surface_form:
        raise AttemptError('word is required', 'WORD_REQUIRED')

    occurrence = (
        WordOccurrence.query
        .join(Chapter, WordOccurrence.chapter_id == Chapter.id)
        .filter(Chapter.book_id == book_id)
        .filter(db.func.lower(WordOccurrence.surface_form) == surface_form.lower())
        .first()
    )
    if occurrence:
        return occurrence.word_sense

    word_sense = WordSense.query.filter_by(lemma=surface_form.lower(), sense_key='').first()
    if word_sense:
        return word_sense

    raise AttemptError('word not recognized for this book', 'WORD_NOT_RESOLVED', 404)


# ---------------------------------------------------------------------------
# Core attempt submission — called by both daily-run and practice
# ---------------------------------------------------------------------------

def submit_attempt(user_id, book_id, surface_form, game, mode, correct,
                    hints_used=0, heaviest_hint_tier=None, from_memory=False,
                    occurred_on=None):
    if game not in GAME_KEYS:
        raise AttemptError('unsupported game %r' % (game,), 'UNSUPPORTED_GAME')
    if mode not in ('daily', 'practice'):
        raise AttemptError('mode must be daily or practice', 'INVALID_MODE')
    if heaviest_hint_tier is not None and heaviest_hint_tier not in HINT_TIERS:
        raise AttemptError('invalid hint tier %r' % (heaviest_hint_tier,), 'INVALID_HINT_TIER')

    occurred_on = occurred_on or _today()
    word_sense = resolve_word_sense_for_book(book_id, surface_form)

    progress = WordProgress.query.filter_by(user_id=user_id, word_sense_id=word_sense.id).first()
    if progress is None:
        progress = WordProgress(user_id=user_id, word_sense_id=word_sense.id, stage=STAGE_ENCOUNTERED)
        db.session.add(progress)
        db.session.flush()

    previous_stage = progress.stage

    if correct:
        evidence = WordProgressEvidence(
            word_progress_id=progress.id,
            source=TYPED_FROM_MEMORY if from_memory else game,
            mode=mode,
            occurred_on=occurred_on,
            hints_used=hints_used,
            heaviest_hint_tier=heaviest_hint_tier,
        )
        db.session.add(evidence)
        db.session.flush()

        if not from_memory and hints_used == 0:
            setattr(progress, PIP_FIELD_BY_GAME[game], True)

        progress.consecutive_no_hint_clears = (
            progress.consecutive_no_hint_clears + 1 if hints_used == 0 else 0
        )

        _recompute_stage(progress)

    db.session.commit()

    newly_mastered = correct and previous_stage != STAGE_MASTERED and progress.stage == STAGE_MASTERED
    streak_state = _update_streak(user_id, occurred_on)
    unlocked = _evaluate_achievements(user_id) if correct else []
    # Passport certificates ride on the milestones the achievement pass just
    # unlocked (band cleared / book mastered) — no extra queries. Local import
    # avoids a circular dependency (certificates reconcile via this engine).
    if unlocked:
        from apps.certificates import issue_certificates_from_unlocked
        new_certificates = issue_certificates_from_unlocked(user_id, unlocked)
    else:
        new_certificates = []
    near_miss = find_nearest_near_miss(user_id)

    return {
        'word_sense_id': word_sense.id,
        'lemma': word_sense.lemma,
        'stage': progress.stage,
        'stage_advanced': previous_stage != progress.stage,
        'pip_count': progress.pip_count,
        'newly_mastered': newly_mastered,
        'cefr_level': word_sense.effective_cefr_level,
        'streak': streak_state,
        'unlocked_achievements': unlocked,
        'new_certificates': new_certificates,
        'nearest_near_miss': near_miss,
    }


def _recompute_stage(progress):
    evidence_rows = WordProgressEvidence.query.filter_by(word_progress_id=progress.id).all()
    if not evidence_rows:
        return

    sources = {row.source for row in evidence_rows}
    days = {row.occurred_on for row in evidence_rows}
    has_unaided = any(row.hints_used == 0 for row in evidence_rows)
    typed_from_memory_ever = TYPED_FROM_MEMORY in sources

    progress.distinct_sources_count = len(sources)
    progress.distinct_days_count = len(days)
    progress.has_unaided_clear = has_unaided

    now = datetime.now()
    if progress.first_guessed_at is None:
        progress.first_guessed_at = now

    is_known = has_unaided or len(evidence_rows) >= 2 or typed_from_memory_ever
    is_mastered = len(sources) >= 2 and len(days) >= 2 and has_unaided

    if is_mastered:
        progress.stage = STAGE_MASTERED
        if progress.mastered_at is None:
            progress.mastered_at = now
    elif is_known:
        progress.stage = STAGE_KNOWN
        if progress.first_known_at is None:
            progress.first_known_at = now
    else:
        progress.stage = STAGE_GUESSED


# ---------------------------------------------------------------------------
# Streak (section 11) — one shared streak for both modes, grace-protected
# ---------------------------------------------------------------------------

def _update_streak(user_id, played_on):
    streak = UserStreak.query.filter_by(user_id=user_id).first()
    if streak is None:
        streak = UserStreak(user_id=user_id, current_streak=1, best_streak=1, last_played_on=played_on)
        db.session.add(streak)
        db.session.commit()
        return _streak_state(streak, welcome_back=False)

    if streak.last_played_on == played_on:
        db.session.commit()
        return _streak_state(streak, welcome_back=False)

    gap_days = (played_on - streak.last_played_on).days if streak.last_played_on else None
    welcome_back = gap_days is not None and gap_days > WELCOME_BACK_GAP_DAYS

    if gap_days == 1:
        streak.current_streak += 1
    elif gap_days == 2 and streak.grace_available:
        # One missed day is protected — never punish a lapse (section 4/13).
        streak.current_streak += 1
        streak.grace_available = False
        streak.grace_used_on = played_on
    else:
        streak.current_streak = 1

    if streak.grace_used_on and (played_on - streak.grace_used_on).days >= GRACE_REPLENISH_DAYS:
        streak.grace_available = True

    streak.best_streak = max(streak.best_streak, streak.current_streak)
    streak.last_played_on = played_on
    db.session.commit()

    return _streak_state(streak, welcome_back=welcome_back)


def _streak_state(streak, welcome_back):
    return {
        'current_streak': streak.current_streak,
        'best_streak': streak.best_streak,
        'grace_available': streak.grace_available,
        'welcome_back': welcome_back,
    }


# ---------------------------------------------------------------------------
# CEFR band roll-up (T17) and book/chapter completion (T18)
# ---------------------------------------------------------------------------

def get_band_rollup(user_id):
    """Mastered-per-band and total-per-band, scoped to words this learner has
    actually encountered, excluding unleveled words entirely (never folded
    into a band)."""
    rollup = {level: {'mastered': 0, 'total': 0} for level in CEFR_LEVELS}

    rows = (
        db.session.query(WordSense.cefr_level, WordSense.cefr_override_level, WordProgress.stage)
        .join(WordProgress, WordProgress.word_sense_id == WordSense.id)
        .filter(WordProgress.user_id == user_id)
        .all()
    )
    for cefr_level, cefr_override_level, stage in rows:
        level = cefr_override_level or cefr_level
        if level not in rollup:
            continue
        rollup[level]['total'] += 1
        if stage == STAGE_MASTERED:
            rollup[level]['mastered'] += 1

    return rollup


def get_book_completion(user_id):
    """T18 — 'every leveled target word mastered' per chapter and book.
    Every book currently has exactly one default chapter (Phase 1), so
    Chapter Master and Book Conqueror necessarily fire together until real
    chapter splitting exists — this logic is written generically so that
    stops being true the moment chapters are split for real."""
    results = {}

    # The mastered set is fetched once rather than counted per chapter. The old
    # shape ran one COUNT per chapter in the database -- not per chapter the
    # reader has touched -- so this route got slower as the platform catalogue
    # grew, for every reader. One query now serves every chapter below.
    mastered_sense_ids = {
        row.word_sense_id
        for row in WordProgress.query.with_entities(WordProgress.word_sense_id).filter(
            WordProgress.user_id == user_id,
            WordProgress.stage == STAGE_MASTERED,
        )
    }

    for chapter in Chapter.query.all():
        leveled_sense_ids = [
            occurrence.word_sense_id for occurrence in chapter.word_occurrences
            if occurrence.word_sense.effective_cefr_level is not None
        ]
        mastered_count = sum(1 for sense_id in leveled_sense_ids if sense_id in mastered_sense_ids)

        if not leveled_sense_ids:
            chapter_complete = False
        else:
            chapter_complete = mastered_count == len(leveled_sense_ids)

        book_entry = results.setdefault(
            chapter.book_id,
            {'chapters': {}, 'book_complete': True, 'mastered': 0, 'total': 0},
        )
        book_entry['chapters'][chapter.id] = chapter_complete
        # Kept rather than discarded: "4 words left in this book" is the whole
        # reason a reader opens the book again, and the numbers were already
        # being computed here only to be thrown away.
        book_entry['mastered'] += mastered_count
        book_entry['total'] += len(leveled_sense_ids)
        if not chapter_complete:
            book_entry['book_complete'] = False

    return results


# ---------------------------------------------------------------------------
# Near-miss finder (section 13 — "the primary retention lever")
# ---------------------------------------------------------------------------

REQUIRED_SOURCES = 2
REQUIRED_DAYS = 2
MASTERY_REQUIREMENT_COUNT = 3  # distinct sources, distinct days, one unaided clear


def _mastery_gap(progress):
    """What this word still needs before it masters, straight off the rule in
    _recompute_stage(): 2+ distinct sources, 2+ distinct days, 1+ unaided
    clear. Reads the counters cached on WordProgress, so no extra queries."""
    needs_new_game = progress.distinct_sources_count < REQUIRED_SOURCES
    needs_new_day = progress.distinct_days_count < REQUIRED_DAYS
    needs_unaided_clear = not progress.has_unaided_clear

    return {
        'needs_new_game': needs_new_game,
        'needs_new_day': needs_new_day,
        'needs_unaided_clear': needs_unaided_clear,
        'requirements_remaining': sum([needs_new_game, needs_new_day, needs_unaided_clear]),
    }


def _next_step(gap):
    """The single most useful thing to tell the learner to do. Ordered by what
    they can act on *right now*: switching game and dropping hints are both
    doable this minute, coming back tomorrow is not — so 'new_day' is only
    suggested when it's the only thing left. Clearing the word in a new game
    without a hint satisfies two requirements at once, hence its priority."""
    if gap['needs_new_game']:
        return 'new_game'
    if gap['needs_unaided_clear']:
        return 'unaided_clear'
    if gap['needs_new_day']:
        return 'new_day'
    return None


def find_nearest_near_miss(user_id):
    """The word closest to mastery — 'the primary retention lever' (section 13).

    Ranked by how many of the three mastery requirements are still missing, not
    by pip count: pips only track hint-free clears per game and are not what
    the mastery rule tests, so ranking on them both mis-ordered the list and
    hid every word whose clears had all been hinted (pip_count 0), even one
    unaided clear away from mastering."""
    candidates = (
        WordProgress.query
        .filter(
            WordProgress.user_id == user_id,
            WordProgress.stage != STAGE_MASTERED,
            # No correct clear yet — nothing to be "near". Encountered-only
            # words have all three counters at zero and would otherwise swamp
            # the ranking.
            WordProgress.stage != STAGE_ENCOUNTERED,
        )
        .all()
    )
    if not candidates:
        return None

    # Fewest requirements left first; among equals, the word the learner has
    # already put the most hint-free work into.
    best = min(
        candidates,
        key=lambda progress: (_mastery_gap(progress)['requirements_remaining'], -progress.pip_count),
    )
    gap = _mastery_gap(best)

    return {
        'word_sense_id': best.word_sense_id,
        'lemma': best.word_sense.lemma,
        'stage': best.stage,
        'pip_count': best.pip_count,
        'distinct_sources_count': best.distinct_sources_count,
        'distinct_days_count': best.distinct_days_count,
        'requirements_total': MASTERY_REQUIREMENT_COUNT,
        'requirements_met': MASTERY_REQUIREMENT_COUNT - gap['requirements_remaining'],
        'next_step': _next_step(gap),
        # Kept so the pre-existing mobile card keeps rendering a number rather
        # than a blank while it moves onto next_step; it now counts real
        # requirements left, not the 4-pip fiction it used to.
        'games_remaining': gap['requirements_remaining'],
        **gap,
    }


# ---------------------------------------------------------------------------
# Achievement metrics + evaluation
# ---------------------------------------------------------------------------

def _count_guessed_or_better(user_id):
    return WordProgress.query.filter(
        WordProgress.user_id == user_id,
        WordProgress.stage.in_([STAGE_GUESSED, STAGE_KNOWN, STAGE_MASTERED]),
    ).count()


def _count_mastered(user_id):
    return WordProgress.query.filter_by(user_id=user_id, stage=STAGE_MASTERED).count()


def _count_three_plus_games(user_id):
    rows = WordProgress.query.filter_by(user_id=user_id).all()
    return sum(1 for row in rows if row.pip_count >= 3)


def _count_all_four_pips(user_id):
    return WordProgress.query.filter_by(
        user_id=user_id,
        pip_bee_genius=True, pip_word_explorer=True,
        pip_think_word=True, pip_intellect_link=True,
    ).count()


def _has_no_hint_clear_ever(user_id):
    return db.session.query(WordProgressEvidence.id).join(
        WordProgress, WordProgressEvidence.word_progress_id == WordProgress.id,
    ).filter(WordProgress.user_id == user_id, WordProgressEvidence.hints_used == 0).first() is not None


def _has_meaning_only_clear_ever(user_id):
    return db.session.query(WordProgressEvidence.id).join(
        WordProgress, WordProgressEvidence.word_progress_id == WordProgress.id,
    ).filter(
        WordProgress.user_id == user_id,
        WordProgressEvidence.heaviest_hint_tier == 'light',
    ).first() is not None


def _best_consecutive_no_hint(user_id):
    value = db.session.query(db.func.max(WordProgress.consecutive_no_hint_clears)).filter(
        WordProgress.user_id == user_id,
    ).scalar()
    return value or 0


def _current_streak(user_id):
    streak = UserStreak.query.filter_by(user_id=user_id).first()
    return streak.current_streak if streak else 0


def _count_word_wizard_shelf(user_id):
    return SelfReportedWord.query.filter_by(user_id=user_id).count()


def _award_if_new(user_id, key, tier=None, context=None):
    existing = UserAchievement.query.filter_by(user_id=user_id, achievement_key=key, tier=tier).first()
    if existing:
        return None
    achievement = UserAchievement(user_id=user_id, achievement_key=key, tier=tier, context=context)
    db.session.add(achievement)
    db.session.commit()
    return {'key': key, 'tier': tier, 'context': context}


def _award_tiers(user_id, key, tiers, value, unlocked):
    for index, threshold in enumerate(tiers, start=1):
        if value >= threshold:
            result = _award_if_new(user_id, key, tier=index)
            if result:
                result['threshold'] = threshold
                unlocked.append(result)


def _evaluate_achievements(user_id):
    unlocked = []

    _award_tiers(user_id, 'word_collector', WORD_COLLECTOR_TIERS, _count_guessed_or_better(user_id), unlocked)
    _award_tiers(user_id, 'steel_trap', STEEL_TRAP_TIERS, _count_mastered(user_id), unlocked)
    _award_tiers(user_id, 'triple_threat', TRIPLE_THREAT_TIERS, _count_three_plus_games(user_id), unlocked)
    _award_tiers(user_id, 'clean_run', CLEAN_RUN_TIERS, _best_consecutive_no_hint(user_id), unlocked)
    _award_tiers(user_id, 'on_a_roll', ON_A_ROLL_TIERS, _current_streak(user_id), unlocked)
    _award_tiers(user_id, 'word_wizard', WORD_WIZARD_TIERS, _count_word_wizard_shelf(user_id), unlocked)

    if _count_all_four_pips(user_id) >= 1:
        result = _award_if_new(user_id, 'master_of_all_trades')
        if result:
            unlocked.append(result)

    if _has_no_hint_clear_ever(user_id):
        result = _award_if_new(user_id, 'no_hints')
        if result:
            unlocked.append(result)

    if _has_meaning_only_clear_ever(user_id):
        result = _award_if_new(user_id, 'meaning_master')
        if result:
            unlocked.append(result)

    rollup = get_band_rollup(user_id)
    for level, counts in rollup.items():
        if counts['mastered'] >= 1:
            result = _award_if_new(user_id, 'first_word_in_%s' % level.lower())
            if result:
                result['level'] = level
                unlocked.append(result)
        if counts['total'] > 0 and counts['mastered'] >= counts['total']:
            result = _award_if_new(user_id, 'band_cleared_%s' % level.lower())
            if result:
                result['level'] = level
                unlocked.append(result)

    well_read_count = 0
    for book_id, status in get_book_completion(user_id).items():
        if status['book_complete']:
            well_read_count += 1
            result = _award_if_new(user_id, 'book_conqueror_%d' % book_id)
            if result:
                result['book_id'] = book_id
                unlocked.append(result)
        for chapter_id, chapter_complete in status['chapters'].items():
            if chapter_complete:
                result = _award_if_new(user_id, 'chapter_master_%d' % chapter_id)
                if result:
                    result['chapter_id'] = chapter_id
                    unlocked.append(result)

    _award_tiers(user_id, 'well_read', WELL_READ_TIERS, well_read_count, unlocked)

    return unlocked


# ---------------------------------------------------------------------------
# Self-reported ("words I already know") shelf — section 8, second branch
# ---------------------------------------------------------------------------

def record_self_reported_word(user_id, surface_form):
    surface_form = (surface_form or '').strip().lower()
    if not surface_form:
        raise AttemptError('word is required', 'WORD_REQUIRED')

    existing = SelfReportedWord.query.filter_by(user_id=user_id, surface_form=surface_form).first()
    if existing:
        return {'created': False, 'shelf_count': _count_word_wizard_shelf(user_id), 'unlocked_achievements': []}

    db.session.add(SelfReportedWord(user_id=user_id, surface_form=surface_form))
    db.session.commit()

    unlocked = []
    _award_tiers(user_id, 'word_wizard', WORD_WIZARD_TIERS, _count_word_wizard_shelf(user_id), unlocked)

    return {'created': True, 'shelf_count': _count_word_wizard_shelf(user_id), 'unlocked_achievements': unlocked}


# ---------------------------------------------------------------------------
# Computed-only flags (not persisted as permanent badges — see project memory
# for why Daily Goal / Welcome Back are treated as per-day, not one-time)
# ---------------------------------------------------------------------------

def get_daily_goal_status(user_id, goal=DEFAULT_DAILY_WORD_GOAL, on_date=None):
    on_date = on_date or _today()
    words_today = (
        db.session.query(WordProgressEvidence.word_progress_id)
        .join(WordProgress, WordProgressEvidence.word_progress_id == WordProgress.id)
        .filter(WordProgress.user_id == user_id, WordProgressEvidence.occurred_on == on_date)
        .distinct()
        .count()
    )
    return {'goal': goal, 'progress': words_today, 'met': words_today >= goal}


# ---------------------------------------------------------------------------
# "It's a Hint Now!" hook — called by Phase 3's hint generator once it
# sources a synonym from a learner's own mastered word. Not wired anywhere
# yet since hint generation itself doesn't exist until Phase 3.
# ---------------------------------------------------------------------------

def award_hint_reused(source_user_id):
    return _award_if_new(source_user_id, 'its_a_hint_now')


# ---------------------------------------------------------------------------
# Read-side aggregations for IREAD_FRONT (recap, trophy page, word-collection)
# ---------------------------------------------------------------------------

# (key, category, tier titles, tiers, metric fn, description template)
ACHIEVEMENT_CATALOG = [
    ('word_collector', 'collection',
     ['Word Collector', 'Word Collector II', 'Word Hunter', 'Word Hunter II', 'Lexicon Master'],
     WORD_COLLECTOR_TIERS, _count_guessed_or_better, 'Reach {threshold} words at Guessed or better.'),
    ('steel_trap', 'mastery',
     ['Steel Trap', 'Steel Trap II', 'Steel Trap III', 'Steel Trap IV'],
     STEEL_TRAP_TIERS, _count_mastered, 'Master {threshold} words.'),
    ('triple_threat', 'mastery',
     ['Triple Threat', 'Triple Threat II', 'Triple Threat III'],
     TRIPLE_THREAT_TIERS, _count_three_plus_games, 'Clear {threshold} words in 3 or more games.'),
    ('clean_run', 'hint_efficiency',
     ['Clean Run', 'Clean Run II', 'Clean Run III'],
     CLEAN_RUN_TIERS, _best_consecutive_no_hint, '{threshold} consecutive no-hint clears.'),
    ('on_a_roll', 'consistency',
     ['On a Roll', 'On a Roll II', 'On a Roll III', 'On a Roll IV'],
     ON_A_ROLL_TIERS, _current_streak, 'Reach a {threshold}-day streak.'),
    ('word_wizard', 'self_produced',
     ['Word Wizard', 'Word Wizard II', 'Word Wizard III'],
     WORD_WIZARD_TIERS, _count_word_wizard_shelf, '{threshold} words on your "I already know" shelf.'),
    ('well_read', 'book',
     ['Well Read', 'Well Read II', 'Well Read III'],
     WELL_READ_TIERS,
     lambda user_id: sum(1 for status in get_book_completion(user_id).values() if status['book_complete']),
     'Master every leveled word in {threshold} books.'),
]

SINGLE_FIRE_CATALOG = [
    ('master_of_all_trades', 'mastery', 'Master of All Trades',
     'Clear one word in all four games.', _count_all_four_pips),
    ('no_hints', 'hint_efficiency', 'No Hints',
     'Clear a word using no hints.', lambda user_id: int(_has_no_hint_clear_ever(user_id))),
    ('meaning_master', 'hint_efficiency', 'Meaning Master',
     'Clear a word using only a meaning hint, no letters revealed.',
     lambda user_id: int(_has_meaning_only_clear_ever(user_id))),
]


def get_achievement_status(user_id):
    """Full catalog with earned/locked state and, for tiered ones, progress
    toward the next tier — 'always know how close the learner is' (section 9)."""
    earned = {
        (row.achievement_key, row.tier): row.earned_at
        for row in UserAchievement.query.filter_by(user_id=user_id).all()
    }
    catalog = []

    for key, category, tier_titles, tiers, metric_fn, description in ACHIEVEMENT_CATALOG:
        value = metric_fn(user_id)
        tiers_status = []
        for index, threshold in enumerate(tiers, start=1):
            earned_at = earned.get((key, index))
            tiers_status.append({
                'tier': index,
                'title': tier_titles[index - 1],
                'threshold': threshold,
                'earned': earned_at is not None,
                'earned_at': earned_at.isoformat() if earned_at else None,
                'progress': min(value, threshold),
            })
        catalog.append({
            'key': key,
            'category': category,
            'description': description.format(threshold='{threshold}'),
            'value': value,
            'tiers': tiers_status,
        })

    for key, category, title, description, metric_fn in SINGLE_FIRE_CATALOG:
        earned_at = earned.get((key, None))
        catalog.append({
            'key': key,
            'category': category,
            'title': title,
            'description': description,
            'earned': earned_at is not None,
            'earned_at': earned_at.isoformat() if earned_at else None,
        })

    rollup = get_band_rollup(user_id)
    for level, counts in rollup.items():
        first_key = 'first_word_in_%s' % level.lower()
        cleared_key = 'band_cleared_%s' % level.lower()
        first_earned_at = earned.get((first_key, None))
        cleared_earned_at = earned.get((cleared_key, None))
        catalog.append({
            'key': first_key, 'category': 'cefr', 'title': 'First %s Word' % level,
            'description': 'Master your first %s word.' % level,
            'earned': first_earned_at is not None,
            'earned_at': first_earned_at.isoformat() if first_earned_at else None,
        })
        catalog.append({
            'key': cleared_key, 'category': 'cefr', 'title': '%s Cleared' % level,
            'description': 'Master every tracked %s word.' % level,
            'earned': cleared_earned_at is not None,
            'earned_at': cleared_earned_at.isoformat() if cleared_earned_at else None,
            'progress': counts['mastered'], 'total': counts['total'],
        })

    book_completion = get_book_completion(user_id)

    # One lookup for every book named below. Without the title these entries are
    # N identical "Book Conqueror" cards a reader cannot tell apart, and without
    # mastered/total there is no way to show which book is closest to done --
    # which is the only version of this that makes anyone open a book.
    book_titles = {}
    if book_completion:
        book_titles = {
            row.id: row.title
            for row in Book.query.with_entities(Book.id, Book.title).filter(
                Book.id.in_(list(book_completion.keys()))
            )
        }

    for book_id, status in book_completion.items():
        key = 'book_conqueror_%d' % book_id
        earned_at = earned.get((key, None))
        catalog.append({
            'key': key, 'category': 'book', 'title': 'Book Conqueror',
            'description': 'Master every tracked word in this book.',
            'book_id': book_id,
            'book_title': book_titles.get(book_id),
            'progress': status.get('mastered', 0),
            'total': status.get('total', 0),
            'earned': earned_at is not None,
            'earned_at': earned_at.isoformat() if earned_at else None,
        })

    return catalog


def _streak_summary(user_id):
    streak = UserStreak.query.filter_by(user_id=user_id).first()
    if not streak:
        return {'current_streak': 0, 'best_streak': 0, 'grace_available': True}
    return {
        'current_streak': streak.current_streak,
        'best_streak': streak.best_streak,
        'grace_available': streak.grace_available,
    }


def get_word_progress_daily_trend(user_id, start_date, end_date):
    """Per-day evidence count and per-day newly-mastered count for a date
    range, for parent/child analytics charts. `start_date`/`end_date` are
    `date` objects, inclusive."""
    evidence_rows = (
        db.session.query(WordProgressEvidence.occurred_on, func.count(WordProgressEvidence.id))
        .join(WordProgress, WordProgress.id == WordProgressEvidence.word_progress_id)
        .filter(
            WordProgress.user_id == user_id,
            WordProgressEvidence.occurred_on >= start_date,
            WordProgressEvidence.occurred_on <= end_date,
        )
        .group_by(WordProgressEvidence.occurred_on)
        .all()
    )
    evidence_by_day = {day: count for day, count in evidence_rows}

    mastered_rows = (
        db.session.query(func.date(WordProgress.mastered_at), func.count(WordProgress.id))
        .filter(
            WordProgress.user_id == user_id,
            WordProgress.mastered_at.isnot(None),
            func.date(WordProgress.mastered_at) >= start_date,
            func.date(WordProgress.mastered_at) <= end_date,
        )
        .group_by(func.date(WordProgress.mastered_at))
        .all()
    )
    mastered_by_day = {}
    for day, count in mastered_rows:
        day = day if isinstance(day, date) else datetime.strptime(str(day), '%Y-%m-%d').date()
        mastered_by_day[day] = count

    all_days = sorted(set(evidence_by_day) | set(mastered_by_day))
    return [
        {
            'date': day.isoformat(),
            'words_practiced': evidence_by_day.get(day, 0),
            'words_mastered': mastered_by_day.get(day, 0),
        }
        for day in all_days
    ]


def get_progress_summary(user_id):
    """Headline numbers for a trophy-page / dashboard header."""
    return {
        'guessed_or_better': _count_guessed_or_better(user_id),
        'mastered': _count_mastered(user_id),
        'band_rollup': get_band_rollup(user_id),
        'streak': _streak_summary(user_id),
        'nearest_near_miss': find_nearest_near_miss(user_id),
        'words_i_know_count': _count_word_wizard_shelf(user_id),
    }


def get_word_collection(user_id):
    """Flat per-word list — enough for the frontend to group into the By
    level / By book / List views itself (section 12); Swarm is a home-page-
    only highlight, not a full-list view, so it's not served from here."""
    rows = (
        db.session.query(WordProgress, WordSense)
        .join(WordSense, WordProgress.word_sense_id == WordSense.id)
        .filter(WordProgress.user_id == user_id)
        .all()
    )

    # One query for every occurrence, not one per word. This loop used to issue
    # a SELECT per row (plus a lazy load of `occurrence.chapter`), so a reader
    # with 3,000 collected words cost ~6,000 round trips and the endpoint timed
    # out long before the client had anything to render.
    sense_ids = [sense.id for _, sense in rows]
    occurrence_by_sense = {}
    if sense_ids:
        for occurrence in (
            WordOccurrence.query
            .options(joinedload(WordOccurrence.chapter))
            .filter(WordOccurrence.word_sense_id.in_(sense_ids))
        ):
            # first() semantics: keep the earliest occurrence per sense.
            occurrence_by_sense.setdefault(occurrence.word_sense_id, occurrence)

    words = []
    for progress, sense in rows:
        occurrence = occurrence_by_sense.get(sense.id)
        chapter = occurrence.chapter if occurrence else None
        words.append({
            'word_sense_id': sense.id,
            'lemma': sense.lemma,
            'surface_form': occurrence.surface_form if occurrence else sense.lemma,
            'cefr_level': sense.effective_cefr_level,
            'is_unresolved': sense.is_unresolved,
            'stage': progress.stage,
            'pips': {
                'bee_genius': progress.pip_bee_genius,
                'word_explorer': progress.pip_word_explorer,
                'think_word': progress.pip_think_word,
                'intellect_link': progress.pip_intellect_link,
            },
            'pip_count': progress.pip_count,
            'book_id': chapter.book_id if chapter else None,
            'chapter_id': chapter.id if chapter else None,
        })

    return words


def get_self_reported_shelf(user_id):
    return [
        {'surface_form': row.surface_form, 'created_at': row.created_at.isoformat()}
        for row in SelfReportedWord.query.filter_by(user_id=user_id)
        .order_by(SelfReportedWord.created_at.desc())
        .all()
    ]


def serialize_reader_progress(reader):
    """Shared by the admin- and teacher-facing reader-progress list routes —
    a read-only summary row per reader, no editing capability here."""
    summary = get_progress_summary(reader.id)
    achievements = get_achievement_status(reader.id)
    earned_count = 0
    for entry in achievements:
        if entry.get('tiers'):
            earned_count += sum(1 for tier in entry['tiers'] if tier.get('earned'))
        elif entry.get('earned'):
            earned_count += 1

    return {
        'user_id': reader.id,
        'username': reader.username,
        'email': reader.email,
        'guessed_or_better': summary['guessed_or_better'],
        'mastered': summary['mastered'],
        'current_streak': summary['streak']['current_streak'],
        'best_streak': summary['streak']['best_streak'],
        'achievements_earned': earned_count,
        'words_i_know_count': summary['words_i_know_count'],
    }
