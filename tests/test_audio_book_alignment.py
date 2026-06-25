import unittest

from apps.audiobooks.routes import (
    mark_alignment_reviewed,
    page_can_be_approved,
    validate_alignment_json,
)


class FakeAudioBookPage:
    def __init__(self, alignment_json):
        self.image_path = '/tmp/page.png'
        self.audio_path = '/tmp/page.mp3'
        self.official_text = 'The little bird.'
        self.audio_duration_ms = 2000
        self.alignment_json = alignment_json


class AudioBookAlignmentValidationTest(unittest.TestCase):
    def valid_alignment(self):
        return {
            'version': 1,
            'language': 'en',
            'audioDurationMs': 2000,
            'officialText': 'The little bird.',
            'transcribedText': 'The little bird.',
            'similarity': 1,
            'model': {
                'provider': 'transformers.js',
                'id': 'test-model',
                'version': 'test'
            },
            'words': [
                {
                    'index': 0,
                    'text': 'The',
                    'startMs': 0,
                    'endMs': 300,
                    'status': 'matched',
                    'confidence': None
                },
                {
                    'index': 1,
                    'text': 'little',
                    'startMs': 300,
                    'endMs': 900,
                    'status': 'matched',
                    'confidence': None
                },
                {
                    'index': 2,
                    'text': 'bird',
                    'startMs': 900,
                    'endMs': 1300,
                    'status': 'matched',
                    'confidence': None
                }
            ],
            'review': {
                'requiresReview': False,
                'unmatchedOfficialWords': [],
                'extraTranscribedWords': [],
                'warnings': []
            }
        }

    def test_accepts_valid_alignment(self):
        alignment = self.valid_alignment()
        self.assertTrue(
            validate_alignment_json(
                alignment,
                audio_duration_ms=2000,
                official_text='The little bird.'
            )
        )

    def test_accepts_intro_offset_timestamps(self):
        alignment = self.valid_alignment()
        alignment['words'][0]['startMs'] = 5000
        alignment['words'][0]['endMs'] = 5300
        alignment['words'][1]['startMs'] = 5300
        alignment['words'][1]['endMs'] = 5900
        alignment['words'][2]['startMs'] = 5900
        alignment['words'][2]['endMs'] = 6300
        alignment['audioDurationMs'] = 8000
        alignment['review']['introOffsetSeconds'] = 5

        self.assertTrue(
            validate_alignment_json(
                alignment,
                audio_duration_ms=8000,
                official_text='The little bird.'
            )
        )

    def test_rejects_official_text_mismatch(self):
        alignment = self.valid_alignment()
        with self.assertRaises(ValueError) as context:
            validate_alignment_json(
                alignment,
                audio_duration_ms=2000,
                official_text='The small bird.'
            )
        self.assertIn('officialText must match', str(context.exception))

    def test_rejects_timestamp_after_audio_duration(self):
        alignment = self.valid_alignment()
        alignment['words'][2]['endMs'] = 2500
        with self.assertRaises(ValueError) as context:
            validate_alignment_json(alignment, audio_duration_ms=2000)
        self.assertIn('cannot exceed audioDurationMs', str(context.exception))

    def test_rejects_unordered_word_indexes(self):
        alignment = self.valid_alignment()
        alignment['words'][2]['index'] = 1
        with self.assertRaises(ValueError) as context:
            validate_alignment_json(alignment, audio_duration_ms=2000)
        self.assertIn('indexes must be ordered', str(context.exception))

    def test_allows_not_spoken_without_timestamps(self):
        alignment = self.valid_alignment()
        alignment['words'].append({
            'index': 3,
            'text': 'quiet',
            'startMs': None,
            'endMs': None,
            'status': 'not-spoken',
            'confidence': None
        })
        self.assertTrue(validate_alignment_json(alignment, audio_duration_ms=2000))

    def test_approval_rejects_alignment_that_requires_review(self):
        alignment = self.valid_alignment()
        alignment['review']['requiresReview'] = True
        ok, message = page_can_be_approved(FakeAudioBookPage(alignment))
        self.assertFalse(ok)
        self.assertIn('requires review', message)

    def test_approval_allows_reviewed_model_alignment(self):
        alignment = self.valid_alignment()
        alignment['review']['requiresReview'] = True
        alignment['review']['unmatchedOfficialWords'] = [
            {'index': 2, 'text': 'bird'}
        ]

        reviewed_alignment = mark_alignment_reviewed(alignment, role='admin')
        ok, message = page_can_be_approved(FakeAudioBookPage(reviewed_alignment))

        self.assertTrue(ok)
        self.assertIsNone(message)
        self.assertFalse(reviewed_alignment['review']['requiresReview'])
        self.assertIn('reviewedTimestampedAt', reviewed_alignment['review'])

    def test_approval_rejects_interpolated_estimated_timestamps(self):
        alignment = self.valid_alignment()
        alignment['words'][0]['status'] = 'interpolated'
        ok, message = page_can_be_approved(FakeAudioBookPage(alignment))
        self.assertFalse(ok)
        self.assertIn('Estimated timestamps', message)


if __name__ == '__main__':
    unittest.main()
