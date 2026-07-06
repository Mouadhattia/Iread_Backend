"""
Resolve a book's vocabulary (Book_text.text) into word_sense rows and record
occurrences against a default chapter (T6-T9, T11).

Safe to re-run: chapters, word-senses, and occurrences are all looked up
before being created, so running this again just confirms nothing changed.

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/ingest_book_vocabulary.py --book-id 27
    python scripts/ingest_book_vocabulary.py --all
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from apps.word_ingestion import ingest_book_vocabulary_list
from models.book import Book


def ingest_one(book):
    stats = ingest_book_vocabulary_list(book.id)
    print('Book %d (%s): %d terms, %d tokens, %d new senses, %d new occurrences' % (
        book.id, book.title, stats['terms'], stats['tokens'],
        stats['senses_created'], stats['occurrences_created'],
    ))
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--book-id', type=int, help='Ingest a single book by id')
    group.add_argument('--all', action='store_true', help='Ingest every book that has Book_text')
    args = parser.parse_args()

    with app.app_context():
        if args.all:
            books = Book.query.all()
            totals = {'terms': 0, 'tokens': 0, 'senses_created': 0, 'occurrences_created': 0}
            for book in books:
                stats = ingest_one(book)
                for key in totals:
                    totals[key] += stats[key]
            print('---')
            print('Totals: %d terms, %d tokens, %d new senses, %d new occurrences across %d books' % (
                totals['terms'], totals['tokens'], totals['senses_created'],
                totals['occurrences_created'], len(books),
            ))
        else:
            book = Book.query.get(args.book_id)
            if not book:
                print('No book with id %d' % args.book_id)
                sys.exit(1)
            ingest_one(book)


if __name__ == '__main__':
    main()
