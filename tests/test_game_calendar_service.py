import unittest

from apps.game_calendar import (
    GAME_INTELLECT_LINK,
    GameCalendarError,
    build_calendar_template_payload,
    clean_words_from_text,
    group_words,
    normalize_game_type,
    preview_calendar_import_payload,
    validate_setting_values,
    validate_words_for_game,
)


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


if __name__ == '__main__':
    unittest.main()
