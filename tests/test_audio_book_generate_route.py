import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from apps.audiobooks import routes


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakePage:
    id = 2
    audio_book_id = 1
    page_number = 1
    image_path = '/tmp/page.png'
    image_mime_type = 'image/png'
    image_file_size = 123
    audio_mime_type = 'audio/mpeg'
    audio_file_size = 456
    active = True
    created_at = None
    updated_at = None

    def __init__(self, audio_path):
        self.audio_path = audio_path
        self.audio_url = None
        self.image_url = None
        self.official_text = ''
        self.language = 'en'
        self.audio_duration_ms = 1000
        self.alignment_json = None
        self.alignment_status = 'draft'
        self.similarity = None


class AudioBookGenerateAlignmentRouteTest(unittest.TestCase):
    def test_generate_alignment_route_saves_text_from_audio(self):
        app = Flask(__name__)
        fake_audio = tempfile.NamedTemporaryFile(delete=False)
        fake_audio.close()

        page = FakePage(fake_audio.name)
        book = SimpleNamespace(id=1, language='en')
        fake_session = FakeSession()
        generated_alignment = {
            'version': 1,
            'language': 'en',
            'audioDurationMs': 2200,
            'officialText': 'Hello from audio.',
            'transcribedText': 'Hello from audio.',
            'similarity': 1,
            'model': {'provider': 'test'},
            'textSource': 'audio-transcript',
            'words': [
                {
                    'index': 0,
                    'text': 'Hello',
                    'startMs': 100,
                    'endMs': 500,
                    'status': 'matched',
                    'confidence': 0.9,
                },
                {
                    'index': 1,
                    'text': 'from',
                    'startMs': 600,
                    'endMs': 1000,
                    'status': 'matched',
                    'confidence': 0.9,
                },
                {
                    'index': 2,
                    'text': 'audio.',
                    'startMs': 1100,
                    'endMs': 2200,
                    'status': 'matched',
                    'confidence': 0.9,
                },
            ],
            'review': {
                'requiresReview': False,
                'unmatchedOfficialWords': [],
                'extraTranscribedWords': [],
                'warnings': [],
            },
        }

        try:
            with app.test_request_context(
                '/admin/audio-books/1/pages/2/generate-alignment',
                method='POST',
                json={'source_text_from_audio': True},
            ):
                with patch.object(routes, 'get_manageable_audio_book', return_value=book), \
                    patch.object(routes, 'get_book_page', return_value=page), \
                    patch.object(routes, 'generate_model_alignment', return_value=generated_alignment) as model_mock, \
                    patch.object(routes.db, 'session', fake_session):
                    response, status_code = routes.handle_generate_alignment(1, 2, 'admin')

            data = response.get_json()

            self.assertEqual(status_code, 200)
            self.assertEqual(data['page']['official_text'], 'Hello from audio.')
            self.assertEqual(data['page']['alignment_json']['officialText'], 'Hello from audio.')
            self.assertEqual(data['page']['alignment_json']['textSource'], 'audio-transcript')
            self.assertEqual(data['page']['alignment_status'], 'ready')
            self.assertEqual(data['page']['audio_duration_ms'], 2200)
            self.assertEqual(page.official_text, 'Hello from audio.')
            self.assertEqual(page.audio_duration_ms, 2200)
            self.assertEqual(fake_session.commits, 2)

            model_mock.assert_called_once_with(
                fake_audio.name,
                None,
                audio_duration_ms=1000,
                language='en',
                options={},
            )
        finally:
            os.unlink(fake_audio.name)


if __name__ == '__main__':
    unittest.main()
