"""
Load a CEFR vocabulary CSV (headword, pos, CEFR, ...) into the word_sense table.

Expects at least the columns `headword`, `pos`, `CEFR` — this matches both the
CEFR-J file (cefrj-vocabulary-profile-1.5.csv, A1-B2) and the Octanove C1/C2
companion file referenced in apps/admin/graphDBscripts/parserDataset.py.

Safe to re-run: matching (lemma, pos) rows are updated in place rather than
duplicated, and a level from a different source is never silently overwritten
(reported as a conflict instead), so loading the C1/C2 file later cannot clobber
levels already assigned by the A1-B2 file.

Usage (from the Iread_Backend project root, with the venv active):
    python scripts/ingest_cefr_source.py --source "C:\\path\\to\\cefrj-vocabulary-profile-1.5.csv" --tag cefrj-1.5
    python scripts/ingest_cefr_source.py --source "C:\\path\\to\\octanove-vocabulary-profile-c1c2-1.0.csv" --tag octanove-c1c2-1.0 --dry-run
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from extensions import db
from models.word_sense import WordSense

# Normalizes this CSV family's free-text POS labels onto spaCy's universal POS
# tag set, so later book-ingestion (spaCy-tagged) lemma+POS lookups line up
# with what's stored here.
POS_MAP = {
    'noun': 'NOUN',
    'verb': 'VERB',
    'adjective': 'ADJ',
    'adverb': 'ADV',
    'pronoun': 'PRON',
    'preposition': 'ADP',
    'determiner': 'DET',
    'conjunction': 'CCONJ',
    'number': 'NUM',
    'interjection': 'INTJ',
    'infinitive-to': 'PART',
    'modal auxiliary': 'AUX',
    'be-verb': 'AUX',
    'do-verb': 'AUX',
    'have-verb': 'AUX',
}


def normalize_pos(raw_pos):
    key = (raw_pos or '').strip().lower()
    return POS_MAP.get(key, key.upper() or 'X')


def load_rows(csv_path):
    with open(csv_path, 'r', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            headword = (row.get('headword') or '').strip().lower()
            raw_pos = row.get('pos') or ''
            level = (row.get('CEFR') or '').strip().upper()
            if not headword or not raw_pos or not level:
                continue
            yield headword, normalize_pos(raw_pos), level


def ingest(csv_path, source_tag, dry_run=False):
    created = 0
    updated = 0
    skipped_conflict = 0

    for lemma, pos, level in load_rows(csv_path):
        existing = WordSense.query.filter_by(lemma=lemma, pos=pos, sense_key='').first()

        if existing is None:
            db.session.add(WordSense(
                lemma=lemma,
                pos=pos,
                sense_key='',
                cefr_level=level,
                cefr_source=source_tag,
            ))
            created += 1
            continue

        if existing.cefr_level is None or existing.cefr_source == source_tag:
            existing.cefr_level = level
            existing.cefr_source = source_tag
            updated += 1
        else:
            skipped_conflict += 1
            print('Conflict: %s/%s already has %s from %s, %s file says %s' % (
                lemma, pos, existing.cefr_level, existing.cefr_source, source_tag, level,
            ))

    print('Created: %d, Updated: %d, Conflicts skipped: %d' % (created, updated, skipped_conflict))

    if dry_run:
        db.session.rollback()
        print('Dry run - no changes committed.')
    else:
        db.session.commit()
        print('Committed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Path to the CEFR CSV file')
    parser.add_argument('--tag', required=True, help='Source label to store in word_sense.cefr_source, e.g. cefrj-1.5')
    parser.add_argument('--dry-run', action='store_true', help='Preview counts without committing')
    args = parser.parse_args()

    with app.app_context():
        ingest(args.source, args.tag, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
