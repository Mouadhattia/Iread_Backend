import unittest

from apps.audiobooks.alignment import (
    AudioAlignmentError,
    build_alignment_from_audio_transcript,
    build_alignment_from_transcript,
)


class AudioBookModelAlignmentTest(unittest.TestCase):
    def transcript(self, words):
        return {
            'language': 'en',
            'segments': [
                {
                    'words': words
                }
            ]
        }

    def test_matches_model_words_to_official_text(self):
        alignment = build_alignment_from_transcript(
            'Hello brave world.',
            self.transcript([
                {'text': 'Hello', 'start': 1.2, 'end': 1.5, 'confidence': 0.92},
                {'text': 'brave', 'start': 1.6, 'end': 2.0, 'confidence': 0.9},
                {'text': 'world', 'start': 2.1, 'end': 2.4, 'confidence': 0.88},
            ]),
            audio_duration_ms=5000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        self.assertEqual(alignment['audioDurationMs'], 5000)
        self.assertFalse(alignment['review']['requiresReview'])
        self.assertEqual(alignment['words'][0]['startMs'], 1200)
        self.assertEqual(alignment['words'][2]['endMs'], 2400)
        self.assertEqual(alignment['words'][2]['text'], 'world.')
        self.assertEqual(alignment['words'][2]['status'], 'matched')

    def test_flags_unmatched_official_words_without_fake_timestamps(self):
        alignment = build_alignment_from_transcript(
            'Hello brave world.',
            self.transcript([
                {'text': 'Hello', 'start': 1.2, 'end': 1.5, 'confidence': 0.92},
                {'text': 'world', 'start': 2.1, 'end': 2.4, 'confidence': 0.88},
            ]),
            audio_duration_ms=5000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        self.assertTrue(alignment['review']['requiresReview'])
        self.assertEqual(alignment['words'][1]['text'], 'brave')
        self.assertEqual(alignment['words'][1]['status'], 'not-spoken')
        self.assertIsNone(alignment['words'][1]['startMs'])
        self.assertEqual(
            alignment['review']['unmatchedOfficialWords'],
            [{'index': 1, 'text': 'brave'}]
        )

    def test_flags_extra_transcribed_words(self):
        alignment = build_alignment_from_transcript(
            'Hello world.',
            self.transcript([
                {'text': 'Hello', 'start': 1.2, 'end': 1.5, 'confidence': 0.92},
                {'text': 'beautiful', 'start': 1.6, 'end': 2.0, 'confidence': 0.9},
                {'text': 'world', 'start': 2.1, 'end': 2.4, 'confidence': 0.88},
            ]),
            audio_duration_ms=5000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        self.assertTrue(alignment['review']['requiresReview'])
        self.assertEqual(
            alignment['review']['extraTranscribedWords'][0]['text'],
            'beautiful'
        )
        self.assertEqual(alignment['words'][1]['text'], 'world.')
        self.assertEqual(alignment['words'][1]['startMs'], 2100)

    def test_builds_official_text_from_audio_transcript(self):
        alignment = build_alignment_from_audio_transcript(
            self.transcript([
                {'text': 'Hello', 'start': 1.2, 'end': 1.5, 'confidence': 0.92},
                {'text': 'world.', 'start': 1.6, 'end': 2.0, 'confidence': 0.88},
            ]),
            audio_duration_ms=5000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        self.assertEqual(alignment['officialText'], 'Hello world.')
        self.assertEqual(alignment['transcribedText'], 'Hello world.')
        self.assertEqual(alignment['similarity'], 1)
        self.assertEqual(alignment['textSource'], 'audio-transcript')
        self.assertFalse(alignment['review']['requiresReview'])
        self.assertEqual(alignment['words'][0]['status'], 'matched')
        self.assertEqual(alignment['words'][1]['endMs'], 2000)

    def test_audio_transcript_duration_keeps_last_word_timestamp(self):
        alignment = build_alignment_from_audio_transcript(
            self.transcript([
                {'text': 'Hello', 'start': 1.2, 'end': 1.5, 'confidence': 0.92},
                {'text': 'world.', 'start': 1.6, 'end': 2.4, 'confidence': 0.88},
            ]),
            audio_duration_ms=2000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        self.assertEqual(alignment['audioDurationMs'], 2400)
        self.assertEqual(alignment['words'][1]['endMs'], 2400)

    def test_audio_transcript_alignment_requires_spoken_words(self):
        with self.assertRaises(AudioAlignmentError):
            build_alignment_from_audio_transcript(
                self.transcript([]),
                audio_duration_ms=5000,
                language='en',
                model_metadata={'provider': 'test'}
            )

    def test_audio_transcript_restores_missing_sentence_punctuation_and_capitalization(self):
        alignment = build_alignment_from_audio_transcript(
            self.transcript([
                {'text': 'hello', 'start': 0.0, 'end': 0.3, 'confidence': 0.9},
                {'text': 'world', 'start': 0.35, 'end': 0.6, 'confidence': 0.9},
                # A 1300ms silence gap here should be treated as a paragraph break.
                {'text': 'the', 'start': 1.9, 'end': 2.1, 'confidence': 0.9},
                {'text': 'end', 'start': 2.15, 'end': 2.4, 'confidence': 0.9},
            ]),
            audio_duration_ms=3000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        # First word capitalized, sentence-ending period inserted at the pause, and the
        # following word capitalized - all without changing the number of words.
        self.assertEqual(len(alignment['words']), 4)
        self.assertEqual(alignment['words'][0]['text'], 'Hello')
        self.assertEqual(alignment['words'][1]['text'], 'world.')
        self.assertTrue(alignment['words'][1]['lineBreakAfter'])
        self.assertEqual(alignment['words'][2]['text'], 'The')
        self.assertEqual(alignment['words'][3]['text'], 'end.')
        self.assertEqual(alignment['officialText'], 'Hello world.\nThe end.')
        # Timestamps for every word are untouched by the text/formatting changes.
        self.assertEqual(alignment['words'][0]['startMs'], 0)
        self.assertEqual(alignment['words'][1]['endMs'], 600)
        self.assertEqual(alignment['words'][2]['startMs'], 1900)
        self.assertEqual(alignment['words'][3]['endMs'], 2400)

    def test_audio_transcript_keeps_existing_punctuation_untouched(self):
        alignment = build_alignment_from_audio_transcript(
            self.transcript([
                {'text': 'Well,', 'start': 0.0, 'end': 0.3, 'confidence': 0.9},
                {'text': 'hello!', 'start': 0.35, 'end': 0.6, 'confidence': 0.9},
            ]),
            audio_duration_ms=1000,
            language='en',
            model_metadata={'provider': 'test'}
        )

        self.assertEqual(alignment['words'][0]['text'], 'Well,')
        self.assertEqual(alignment['words'][1]['text'], 'hello!')
        self.assertEqual(alignment['officialText'], 'Well, hello!')


if __name__ == '__main__':
    unittest.main()
