## @file
# @brief Resolves book vocabulary into WordSense rows and records where each
# sense occurs (T6-T9, T11). Reused by scripts/ingest_book_vocabulary.py and,
# later, by any route that needs resolved word payloads instead of raw
# whitespace-split strings.
import re

import spacy

from extensions import db
from models.book_text import Book_text
from models.chapter import Chapter
from models.word_occurrence import WordOccurrence
from models.word_sense import WordSense

_nlp = None

# spaCy's universal POS set has a few splits the CEFR source doesn't
# distinguish (see scripts/ingest_cefr_source.py POS_MAP) — collapse those so
# a book-ingested token can still match a CEFR-sourced word_sense row.
POS_ALIASES = {
    'SCONJ': 'CCONJ',
}

# Tokens that aren't real learnable words for this purpose.
SKIP_POS = {'PUNCT', 'SPACE', 'SYM', 'X', 'NUM'}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*$")


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load('en_core_web_sm')
    return _nlp


def normalize_pos(spacy_pos):
    return POS_ALIASES.get(spacy_pos, spacy_pos)


def get_or_create_default_chapter(book_id):
    """Every book has exactly one 'Full text' chapter until real
    admin-authored chapter splitting exists (T4 follow-up)."""
    chapter = Chapter.query.filter_by(book_id=book_id, chapter_index=1).first()
    if chapter:
        return chapter

    book_text = Book_text.query.filter_by(book_id=book_id).first()
    chapter = Chapter(
        book_id=book_id,
        chapter_index=1,
        title='Full text',
        text=book_text.text if book_text else None,
    )
    db.session.add(chapter)
    db.session.flush()
    return chapter


def resolve_word_sense(lemma, pos):
    """Resolve to lemma+POS always (T8's pragmatic rule) — sense-level
    disambiguation is left for a future, sense-aware CEFR source; sense_key
    stays '' until then. Creates an unresolved (cefr_level=None) row when the
    CEFR source has no match, rather than defaulting a level (T12)."""
    lemma = lemma.strip().lower()
    existing = WordSense.query.filter_by(lemma=lemma, pos=pos, sense_key='').first()
    if existing:
        return existing, False

    word_sense = WordSense(lemma=lemma, pos=pos, sense_key='')
    db.session.add(word_sense)
    db.session.flush()
    return word_sense, True


def record_occurrence(word_sense, chapter, surface_form, example_line=None):
    existing = WordOccurrence.query.filter_by(
        word_sense_id=word_sense.id,
        chapter_id=chapter.id,
    ).first()
    if existing:
        if example_line and not existing.example_line:
            existing.example_line = example_line
        return existing, False

    occurrence = WordOccurrence(
        word_sense=word_sense,
        chapter=chapter,
        surface_form=surface_form,
        example_line=example_line,
    )
    db.session.add(occurrence)
    return occurrence, True


def ingest_book_vocabulary_list(book_id):
    """Ingest Book_text.text — today's universal vocabulary source, one
    target term per line. It's a curated word/name list, not prose, so there
    is no real sentence to record as example_line; occurrences are captured
    without one rather than fabricating false context."""
    book_text = Book_text.query.filter_by(book_id=book_id).first()
    if not book_text or not book_text.text:
        return {'terms': 0, 'tokens': 0, 'senses_created': 0, 'occurrences_created': 0}

    chapter = get_or_create_default_chapter(book_id)
    nlp = get_nlp()

    terms = 0
    tokens = 0
    senses_created = 0
    occurrences_created = 0

    lines = [line.strip() for line in book_text.text.splitlines() if line.strip()]
    for line in lines:
        terms += 1
        doc = nlp(line)

        for token in doc:
            if not WORD_RE.match(token.text):
                continue
            if token.pos_ in SKIP_POS:
                continue

            tokens += 1
            pos = normalize_pos(token.pos_)
            word_sense, sense_created = resolve_word_sense(token.lemma_, pos)
            _, occ_created = record_occurrence(word_sense, chapter, surface_form=token.text)
            senses_created += int(sense_created)
            occurrences_created += int(occ_created)

    db.session.commit()
    return {
        'terms': terms,
        'tokens': tokens,
        'senses_created': senses_created,
        'occurrences_created': occurrences_created,
    }


def get_resolved_words_for_book(book_id):
    """Read path: resolved word-sense payloads for a book, replacing the
    naive whitespace split behind get_book_games. Not yet wired into any
    route — built so that swap can happen as its own, explicit step."""
    chapter = Chapter.query.filter_by(book_id=book_id, chapter_index=1).first()
    if not chapter:
        return []

    results = []
    for occurrence in chapter.word_occurrences:
        sense = occurrence.word_sense
        results.append({
            'surface_form': occurrence.surface_form,
            'lemma': sense.lemma,
            'pos': sense.pos,
            'cefr_level': sense.effective_cefr_level,
            'cefr_source': sense.cefr_source,
            'definition': sense.definition,
            'is_unresolved': sense.is_unresolved,
        })
    return results
