import unittest
from datetime import date, datetime

from apps.game_calendar import (
    GAME_INTELLECT_LINK,
    GAMES_MODE_FROM_START,
    GAMES_MODE_GLOBAL,
    GameCalendarError,
    build_calendar_template_payload,
    clean_words_from_text,
    get_instance_anchor_date,
    group_words,
    normalize_game_type,
    normalize_games_mode,
    preview_calendar_import_payload,
    resolve_global_play_date,
    validate_setting_values,
    validate_words_for_game,
)


class FakePackInstance:
    """Stand-in for a SchoolPackInstance row, so the date mapping can be
    exercised without a database."""

    def __init__(self, games_mode=GAMES_MODE_FROM_START, games_anchor_date=None, created_at=None):
        self.games_mode = games_mode
        self.games_anchor_date = games_anchor_date
        self.created_at = created_at


class GameCalendarServiceTest(unittest.TestCase):
    def test_normalize_game_type_accepts_supported_values(self):
        self.assertEqual(normalize_game_type('Bee_Genius'), 'bee-genius')
        self.assertEqual(normalize_game_type('word-explorer'), 'word-explorer')

    def test_normalize_game_type_rejects_unsupported_values(self):
        with self.assertRaises(GameCalendarError) as context:
            normalize_game_type('unknown-game')
        self.assertEqual(context.exception.code, 'UNSUPPORTED_GAME_TYPE')

    def test_setting_validation_requires_positive_timer(self):
        with self.assertRaises(GameCalendarError):
            validate_setting_values('think-word', 0)

    def test_intellect_link_requires_non_negative_hints(self):
        timer_seconds, max_hints, timer_enabled = validate_setting_values(GAME_INTELLECT_LINK, 120, 3)
        self.assertEqual(timer_seconds, 120)
        self.assertEqual(max_hints, 3)
        self.assertTrue(timer_enabled)

        with self.assertRaises(GameCalendarError) as context:
            validate_setting_values(GAME_INTELLECT_LINK, 120, None)
        self.assertEqual(context.exception.code, 'MAX_HINTS_REQUIRED')

        with self.assertRaises(GameCalendarError):
            validate_setting_values(GAME_INTELLECT_LINK, 120, -1)

    def test_non_intellect_games_ignore_max_hints(self):
        timer_seconds, max_hints, timer_enabled = validate_setting_values('bee-genius', 60, 8)
        self.assertEqual(timer_seconds, 60)
        self.assertIsNone(max_hints)
        self.assertTrue(timer_enabled)

    def test_word_cleaning_removes_punctuation_and_duplicate_words(self):
        words = clean_words_from_text('Planet, orbit! planet Gravity; orbit? moon')
        self.assertEqual(words, ['Planet', 'orbit', 'Gravity', 'moon'])

    def test_three_word_games_require_three_words(self):
        self.assertEqual(
            validate_words_for_game('think-word', ['one', 'two', 'three']),
            ['one', 'two', 'three']
        )
        with self.assertRaises(GameCalendarError) as context:
            validate_words_for_game('think-word', ['one', 'two'])
        self.assertEqual(context.exception.code, 'INVALID_GAME_WORD_COUNT')

    def test_intellect_link_requires_exactly_nine_words(self):
        words = [str(index) for index in range(1, 10)]
        self.assertEqual(validate_words_for_game(GAME_INTELLECT_LINK, words), words)

        with self.assertRaises(GameCalendarError) as context:
            validate_words_for_game(GAME_INTELLECT_LINK, words[:8])
        self.assertEqual(context.exception.code, 'INTELLECT_LINK_REQUIRES_NINE_WORDS')

    def test_group_words_uses_complete_groups_only(self):
        groups = group_words(['a', 'b', 'c', 'd', 'e', 'f', 'g'], 3)
        self.assertEqual(groups, [['a', 'b', 'c'], ['d', 'e', 'f']])

    def test_calendar_template_includes_example_days(self):
        payload = build_calendar_template_payload(1, 27, 'think-word')
        self.assertEqual(payload['school_id'], 1)
        self.assertEqual(payload['book_id'], 27)
        self.assertEqual(payload['game_type'], 'think-word')
        self.assertEqual(len(payload['days']), 3)
        self.assertEqual(len(payload['days'][0]['words']), 3)

    def test_import_preview_validates_duplicates_and_existing_days(self):
        payload = {
            'book_id': 27,
            'game_type': 'think-word',
            'days': [
                {'date': '2026-06-24', 'words': ['one', 'two', 'three']},
                {'date': '2026-06-24', 'words': ['four', 'five', 'six']},
                {'date': '2026-06-25', 'words': ['seven', 'eight', 'nine']},
            ],
        }
        preview = preview_calendar_import_payload(
            1,
            27,
            'think-word',
            payload,
            overwrite=False,
            existing_dates={'2026-06-25'},
        )
        self.assertEqual(preview['valid_days'], 2)
        self.assertEqual(preview['invalid_days'], 1)
        self.assertEqual(preview['created'], 1)
        self.assertEqual(preview['skipped_existing'], 1)
        self.assertEqual(preview['duplicate_dates'], ['2026-06-24'])


class GlobalScheduleMappingTest(unittest.TestCase):
    """The rules that decide which words a child sees on a given day, and
    therefore who they can fairly be ranked against."""

    MASTER_START = date(2026, 9, 1)

    def test_global_mode_plays_the_master_calendar_date_unshifted(self):
        instance = FakePackInstance(
            games_mode=GAMES_MODE_GLOBAL,
            games_anchor_date=date(2026, 10, 15)
        )
        master_date, mode, shift = resolve_global_play_date(
            instance, self.MASTER_START, date(2026, 10, 20)
        )
        # The anchor is deliberately ignored: every global-mode school must
        # land on the same master day or the shared ranking is meaningless.
        self.assertEqual(master_date, date(2026, 10, 20))
        self.assertEqual(mode, GAMES_MODE_GLOBAL)
        self.assertEqual(shift, 0)

    def test_two_global_mode_schools_land_on_the_same_master_day(self):
        early = FakePackInstance(games_mode=GAMES_MODE_GLOBAL, games_anchor_date=date(2026, 9, 1))
        late = FakePackInstance(games_mode=GAMES_MODE_GLOBAL, games_anchor_date=date(2026, 11, 3))
        play_day = date(2026, 11, 10)
        self.assertEqual(
            resolve_global_play_date(early, self.MASTER_START, play_day)[0],
            resolve_global_play_date(late, self.MASTER_START, play_day)[0],
        )

    def test_from_start_mode_replays_day_one_on_the_anchor_date(self):
        instance = FakePackInstance(games_anchor_date=date(2026, 10, 15))
        master_date, mode, shift = resolve_global_play_date(
            instance, self.MASTER_START, date(2026, 10, 15)
        )
        self.assertEqual(master_date, self.MASTER_START)
        self.assertEqual(mode, GAMES_MODE_FROM_START)
        self.assertEqual(shift, -44)

    def test_from_start_mode_advances_one_master_day_per_local_day(self):
        instance = FakePackInstance(games_anchor_date=date(2026, 10, 15))
        self.assertEqual(
            resolve_global_play_date(instance, self.MASTER_START, date(2026, 10, 18))[0],
            date(2026, 9, 4),
        )

    def test_from_start_mode_rejects_days_before_the_anchor(self):
        instance = FakePackInstance(games_anchor_date=date(2026, 10, 15))
        with self.assertRaises(GameCalendarError) as context:
            resolve_global_play_date(instance, self.MASTER_START, date(2026, 10, 14))
        self.assertEqual(context.exception.code, 'GAME_SCHEDULE_NOT_STARTED')
        self.assertEqual(context.exception.status_code, 404)

    def test_from_start_mode_without_a_master_schedule_yields_no_date(self):
        instance = FakePackInstance(games_anchor_date=date(2026, 10, 15))
        master_date, _, _ = resolve_global_play_date(instance, None, date(2026, 10, 20))
        self.assertIsNone(master_date)

    def test_anchor_falls_back_to_the_instance_creation_day(self):
        instance = FakePackInstance(created_at=datetime(2026, 7, 4, 13, 45))
        self.assertEqual(get_instance_anchor_date(instance), date(2026, 7, 4))

    def test_explicit_anchor_wins_over_creation_day(self):
        instance = FakePackInstance(
            games_anchor_date=date(2026, 10, 1),
            created_at=datetime(2026, 7, 4, 13, 45)
        )
        self.assertEqual(get_instance_anchor_date(instance), date(2026, 10, 1))

    def test_games_mode_normalisation_and_default(self):
        self.assertEqual(normalize_games_mode(None), GAMES_MODE_FROM_START)
        self.assertEqual(normalize_games_mode(''), GAMES_MODE_FROM_START)
        self.assertEqual(normalize_games_mode('GLOBAL'), GAMES_MODE_GLOBAL)
        self.assertEqual(normalize_games_mode('from-start'), GAMES_MODE_FROM_START)

    def test_games_mode_rejects_unknown_values(self):
        with self.assertRaises(GameCalendarError) as context:
            normalize_games_mode('whenever')
        self.assertEqual(context.exception.code, 'INVALID_GAMES_MODE')


class AdminRouteHelperBindingTest(unittest.TestCase):
    """Guards a name collision that took every global calendar write down.

    `apps/admin/routes.py` defines its own stricter `parse_bool_value(value,
    name)`, and a module-level def beats an import at the top of the same file.
    The game-calendar routes therefore call the service helper through the
    `parse_game_bool_value` alias; if someone drops the alias, every call
    passing `default=` raises TypeError and the routes answer a bare 500 --
    which is exactly how generate, JSON import and the leaderboard opt-in
    toggle all failed in production while every read kept working.
    """

    def test_game_bool_helper_is_the_service_one_and_takes_a_default(self):
        from apps.admin import routes
        from apps.game_calendar import parse_bool_value as service_parse_bool_value

        self.assertIs(routes.parse_game_bool_value, service_parse_bool_value)
        self.assertFalse(routes.parse_game_bool_value(None, 'overwrite', default=False))
        self.assertTrue(routes.parse_game_bool_value(None, 'opt_in', default=True))


if __name__ == '__main__':
    unittest.main()
