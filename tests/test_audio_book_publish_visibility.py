import unittest
from types import SimpleNamespace
from unittest.mock import patch

from apps.audiobooks import routes


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def all(self):
        return list(self.items)

    def count(self):
        return len(self.items)


class FakePage:
    def __init__(self, page_number, alignment_status):
        self.id = page_number
        self.audio_book_id = 10
        self.page_number = page_number
        self.image_path = f'/tmp/page-{page_number}.png'
        self.image_mime_type = 'image/png'
        self.image_file_size = 100
        self.audio_path = f'/tmp/page-{page_number}.mp3'
        self.audio_mime_type = 'audio/mpeg'
        self.audio_file_size = 200
        self.official_text = f'Page {page_number} text'
        self.language = 'en'
        self.audio_duration_ms = 1000
        self.image_position = 'above'
        self.font_size = 20
        self.alignment_json = {
            'words': [
                {
                    'index': 0,
                    'text': 'Page',
                    'startMs': 0,
                    'endMs': 500,
                    'status': 'matched',
                }
            ]
        }
        self.alignment_status = alignment_status
        self.similarity = 1
        self.active = True
        self.created_at = None
        self.updated_at = None


class AudioBookPublishVisibilityTest(unittest.TestCase):
    def test_reader_serialization_only_exposes_approved_pages(self):
        approved_page = FakePage(1, 'approved')
        draft_page = FakePage(2, 'draft')
        book = SimpleNamespace(
            id=10,
            title='Reader Story',
            description='',
            cover_image_path=None,
            language='en',
            level=None,
            category=None,
            book_id=None,
            status='published',
            shcool_id=3,
            created_by_id=4,
            created_by_role='admin',
            active=True,
            published_at=None,
            created_at=None,
            updated_at=None,
        )
        fake_user_model = SimpleNamespace(query=SimpleNamespace(get=lambda _id: None))
        fake_book_model = SimpleNamespace(query=SimpleNamespace(get=lambda _id: None))

        with patch.object(routes, 'approved_pages_query', return_value=FakeQuery([approved_page])), \
            patch.object(routes, 'active_pages_query', return_value=FakeQuery([approved_page, draft_page])), \
            patch.object(routes, 'get_audio_book_progress', return_value=None), \
            patch.object(routes, 'User', fake_user_model), \
            patch.object(routes, 'Book', fake_book_model):
            reader_payload = routes.serialize_audio_book(book, include_pages=True, role='reader')
            admin_payload = routes.serialize_audio_book(book, include_pages=True, role='admin')

        self.assertEqual(reader_payload['pages_count'], 1)
        self.assertEqual(reader_payload['approved_pages_count'], 1)
        self.assertEqual([page['page_number'] for page in reader_payload['pages']], [1])
        self.assertEqual(admin_payload['pages_count'], 2)
        self.assertEqual([page['page_number'] for page in admin_payload['pages']], [1, 2])

    def test_published_book_returns_to_draft_after_content_change(self):
        book = SimpleNamespace(status='published', published_at='2026-06-24T00:00:00')

        routes.mark_audio_book_draft_for_content_change(book)

        self.assertEqual(book.status, 'draft')
        self.assertIsNone(book.published_at)


if __name__ == '__main__':
    unittest.main()
