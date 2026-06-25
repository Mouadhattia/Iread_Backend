import re
from datetime import date, datetime, timedelta

import pytz

from extensions import db
from models.book_text import Book_text
from models.game_calendar_entry import GameCalendarEntry
from models.school_game_setting import SchoolGameSetting


GAME_BEE_GENIUS = 'bee-genius'
GAME_WORD_EXPLORER = 'word-explorer'
GAME_THINK_WORD = 'think-word'
GAME_INTELLECT_LINK = 'intellect-link'

SUPPORTED_GAME_TYPES = (
    GAME_BEE_GENIUS,
    GAME_WORD_EXPLORER,
    GAME_THINK_WORD,
    GAME_INTELLECT_LINK,
)

GAME_RULES = {
    GAME_BEE_GENIUS: {
        'words_per_day': 3,
        'default_timer_seconds': 60,
        'requires_max_hints': False,
    },
    GAME_WORD_EXPLORER: {
        'words_per_day': 3,
        'default_timer_seconds': 60,
        'requires_max_hints': False,
    },
    GAME_THINK_WORD: {
        'words_per_day': 3,
        'default_timer_seconds': 60,
        'requires_max_hints': False,
    },
    GAME_INTELLECT_LINK: {
        'words_per_day': 9,
        'default_timer_seconds': 120,
        'requires_max_hints': True,
        'default_max_hints': 3,
    },
}

DEFAULT_GAME_TIMEZONE = 'Africa/Tunis'
WORD_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


class GameCalendarError(ValueError):
    def __init__(self, message, code, status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def game_error_response(error):
    return {'message': error.message, 'code': error.code}, error.status_code


def normalize_game_type(game_type):
    if game_type is None:
        raise GameCalendarError('game_type is required', 'GAME_TYPE_REQUIRED', 400)
    normalized = str(game_type).strip().lower().replace('_', '-')
    if normalized not in GAME_RULES:
        raise GameCalendarError('Unsupported game type', 'UNSUPPORTED_GAME_TYPE', 400)
    return normalized


def parse_positive_int(value, field_name):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise GameCalendarError(f'{field_name} must be a positive integer', 'INVALID_POSITIVE_INTEGER', 400)
    if value < 1:
        raise GameCalendarError(f'{field_name} must be greater than 0', 'INVALID_POSITIVE_INTEGER', 400)
    return value


def parse_non_negative_int(value, field_name):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise GameCalendarError(f'{field_name} must be a non-negative integer', 'INVALID_NON_NEGATIVE_INTEGER', 400)
    if value < 0:
        raise GameCalendarError(f'{field_name} must be greater than or equal to 0', 'INVALID_NON_NEGATIVE_INTEGER', 400)
    return value


def parse_optional_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in ('true', '1', 'yes', 'y', 'on'):
        return True
    if normalized in ('false', '0', 'no', 'n', 'off'):
        return False
    raise GameCalendarError('timer_enabled must be true or false', 'INVALID_TIMER_ENABLED', 400)


def parse_bool_value(value, field_name='value', default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in ('true', '1', 'yes', 'y', 'on'):
        return True
    if normalized in ('false', '0', 'no', 'n', 'off', ''):
        return False
    raise GameCalendarError(f'{field_name} must be true or false', 'INVALID_BOOLEAN', 400)


def parse_play_date(value, field_name='date'):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        raise GameCalendarError(f'{field_name} is required', 'DATE_REQUIRED', 400)
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise GameCalendarError(f'{field_name} must use YYYY-MM-DD format', 'INVALID_DATE', 400)


def parse_optional_play_date(value, field_name='date'):
    if value in (None, ''):
        return None
    return parse_play_date(value, field_name)


def get_school_local_date(school=None):
    timezone_name = getattr(school, 'timezone', None) or DEFAULT_GAME_TIMEZONE
    try:
        timezone = pytz.timezone(timezone_name)
    except pytz.UnknownTimeZoneError:
        timezone = pytz.timezone(DEFAULT_GAME_TIMEZONE)
    return datetime.now(timezone).date()


def validate_setting_values(game_type, timer_seconds=None, max_hints=None, timer_enabled=True):
    game_type = normalize_game_type(game_type)
    timer_enabled = parse_optional_bool(timer_enabled, default=True)
    if timer_seconds in (None, ''):
        timer_seconds = GAME_RULES[game_type]['default_timer_seconds']
    timer_seconds = parse_positive_int(timer_seconds, 'timer_seconds')

    if GAME_RULES[game_type]['requires_max_hints']:
        if max_hints is None:
            raise GameCalendarError('max_hints is required for intellect-link', 'MAX_HINTS_REQUIRED', 400)
        max_hints = parse_non_negative_int(max_hints, 'max_hints')
    else:
        max_hints = None

    return timer_seconds, max_hints, timer_enabled


def clean_words_from_text(text):
    if not text:
        return []
    return clean_words_from_iterable(WORD_TOKEN_RE.findall(str(text)))


def split_legacy_words_from_text(text):
    if not text:
        return []
    return str(text).strip().split()


def clean_words_from_iterable(raw_words):
    if raw_words is None:
        raise GameCalendarError('words are required', 'WORDS_REQUIRED', 400)
    if not isinstance(raw_words, list):
        raise GameCalendarError('words must be a list', 'INVALID_WORDS', 400)

    words = []
    seen = set()
    for raw_word in raw_words:
        tokens = WORD_TOKEN_RE.findall(str(raw_word or ''))
        for token in tokens:
            word = token.strip("-'").strip()
            if not word:
                continue
            key = word.casefold()
            if key in seen:
                continue
            seen.add(key)
            words.append(word)
    return words


def normalize_import_words(raw_words):
    if isinstance(raw_words, str):
        return clean_words_from_text(raw_words)
    return clean_words_from_iterable(raw_words)


def get_words_per_day(game_type):
    return GAME_RULES[normalize_game_type(game_type)]['words_per_day']


def validate_words_for_game(game_type, raw_words, status_code=400):
    game_type = normalize_game_type(game_type)
    words = clean_words_from_iterable(raw_words)
    expected_count = get_words_per_day(game_type)
    if len(words) != expected_count:
        code = 'INTELLECT_LINK_REQUIRES_NINE_WORDS' if game_type == GAME_INTELLECT_LINK else 'INVALID_GAME_WORD_COUNT'
        raise GameCalendarError(
            f'{game_type} requires exactly {expected_count} words',
            code,
            status_code
        )
    return words


def get_or_create_game_setting(school_id, game_type, timer_seconds=None, max_hints=None, timer_enabled=True):
    game_type = normalize_game_type(game_type)
    timer_seconds, max_hints, timer_enabled = validate_setting_values(
        game_type,
        timer_seconds,
        max_hints,
        timer_enabled
    )
    setting = SchoolGameSetting.query.filter_by(shcool_id=school_id, game_type=game_type).first()
    created = False
    if not setting:
        setting = SchoolGameSetting(shcool_id=school_id, game_type=game_type)
        db.session.add(setting)
        created = True

    setting.timer_seconds = timer_seconds
    setting.timer_enabled = timer_enabled
    setting.max_hints = max_hints
    setting.updated_at = datetime.now()
    return setting, created


def get_school_game_settings(school_id):
    settings = SchoolGameSetting.query.filter_by(shcool_id=school_id).all()
    return {setting.game_type: setting for setting in settings}


def serialize_game_setting(setting=None, game_type=None, school_id=None):
    if setting:
        game_type = setting.game_type
        school_id = setting.shcool_id
    game_type = normalize_game_type(game_type)
    rule = GAME_RULES[game_type]

    data = {
        'game_type': game_type,
        'school_id': school_id,
        'shcool_id': school_id,
        'configured': setting is not None,
        'timer_seconds': setting.timer_seconds if setting else None,
        'timer_enabled': setting.timer_enabled if setting else True,
        'max_hints': setting.max_hints if setting else None,
        'words_per_day': rule['words_per_day'],
        'requires_max_hints': rule['requires_max_hints'],
        'default_timer_seconds': rule['default_timer_seconds'],
        'created_at': setting.created_at.isoformat() if setting and setting.created_at else None,
        'updated_at': setting.updated_at.isoformat() if setting and setting.updated_at else None,
    }
    if rule.get('default_max_hints') is not None:
        data['default_max_hints'] = rule['default_max_hints']
    return data


def serialize_calendar_entry(entry):
    return {
        'id': entry.id,
        'school_id': entry.shcool_id,
        'shcool_id': entry.shcool_id,
        'book_id': entry.book_id,
        'game_type': entry.game_type,
        'play_date': entry.play_date.isoformat() if entry.play_date else None,
        'date': entry.play_date.isoformat() if entry.play_date else None,
        'words': list(entry.words or []),
        'created_at': entry.created_at.isoformat() if entry.created_at else None,
        'updated_at': entry.updated_at.isoformat() if entry.updated_at else None,
    }


def build_example_words(game_type, day_index=0):
    game_type = normalize_game_type(game_type)
    examples = {
        GAME_BEE_GENIUS: [
            ['reader', 'story', 'library'],
            ['teacher', 'lesson', 'chapter'],
            ['planet', 'bridge', 'garden'],
        ],
        GAME_WORD_EXPLORER: [
            ['school', 'pencil', 'notebook'],
            ['forest', 'river', 'island'],
            ['science', 'energy', 'motion'],
        ],
        GAME_THINK_WORD: [
            ['castle', 'market', 'window'],
            ['bicycle', 'journey', 'friend'],
            ['mystery', 'garden', 'letter'],
        ],
        GAME_INTELLECT_LINK: [
            ['sharing', 'kindness', 'friend', 'school', 'reader', 'story', 'lesson', 'chapter', 'library'],
            ['planet', 'orbit', 'gravity', 'moon', 'rocket', 'space', 'science', 'energy', 'motion'],
            ['garden', 'bicycle', 'bridge', 'river', 'forest', 'island', 'market', 'window', 'castle'],
        ],
    }
    game_examples = examples[game_type]
    return list(game_examples[day_index % len(game_examples)][:get_words_per_day(game_type)])


def build_calendar_template_payload(school_id, book_id, game_type, setting=None, start_date=None):
    game_type = normalize_game_type(game_type)
    rule = GAME_RULES[game_type]
    start_date = parse_optional_play_date(start_date, 'start_date') or date.today()
    settings = {
        'timer_enabled': setting.timer_enabled if setting else True,
        'timer_seconds': setting.timer_seconds if setting else rule['default_timer_seconds'],
    }
    if rule['requires_max_hints']:
        settings['max_hints'] = (
            setting.max_hints
            if setting and setting.max_hints is not None
            else rule.get('default_max_hints', 0)
        )

    return {
        'version': 1,
        'description': 'Edit the days array, then import this JSON from the game calendar dashboard.',
        'school_id': school_id,
        'shcool_id': school_id,
        'book_id': book_id,
        'game_type': game_type,
        'settings': settings,
        'days': [
            {
                'date': (start_date + timedelta(days=index)).isoformat(),
                'words': build_example_words(game_type, index),
            }
            for index in range(3)
        ],
    }


def build_calendar_export_payload(school_id, book_id, game_type, entries, setting=None):
    game_type = normalize_game_type(game_type)
    rule = GAME_RULES[game_type]
    settings = {
        'timer_enabled': setting.timer_enabled if setting else True,
        'timer_seconds': setting.timer_seconds if setting else rule['default_timer_seconds'],
    }
    if rule['requires_max_hints']:
        settings['max_hints'] = (
            setting.max_hints
            if setting and setting.max_hints is not None
            else rule.get('default_max_hints', 0)
        )

    return {
        'version': 1,
        'school_id': school_id,
        'shcool_id': school_id,
        'book_id': book_id,
        'game_type': game_type,
        'settings': settings,
        'days': [
            {
                'date': entry.play_date.isoformat() if entry.play_date else None,
                'words': list(entry.words or []),
            }
            for entry in entries
        ],
    }


def get_import_days(payload):
    if not isinstance(payload, dict):
        raise GameCalendarError('JSON root must be an object', 'INVALID_IMPORT_JSON', 400)
    days = payload.get('days')
    if days is None:
        days = payload.get('entries')
    if days is None:
        days = payload.get('calendar')
    if not isinstance(days, list):
        raise GameCalendarError('JSON must include a days array', 'INVALID_IMPORT_DAYS', 400)
    return days


def validate_import_metadata(payload, book_id, game_type):
    game_type = normalize_game_type(game_type)
    payload_game_type = payload.get('game_type') or payload.get('game')
    if payload_game_type and normalize_game_type(payload_game_type) != game_type:
        raise GameCalendarError('JSON game_type does not match selected game', 'IMPORT_GAME_MISMATCH', 400)

    payload_book_id = payload.get('book_id')
    if payload_book_id not in (None, ''):
        try:
            payload_book_id = int(payload_book_id)
        except (TypeError, ValueError):
            raise GameCalendarError('JSON book_id must be a number', 'INVALID_IMPORT_BOOK_ID', 400)
        if payload_book_id != int(book_id):
            raise GameCalendarError('JSON book_id does not match selected book', 'IMPORT_BOOK_MISMATCH', 400)


def get_import_setting_values(game_type, payload):
    settings = payload.get('settings') if isinstance(payload, dict) else None
    if settings in (None, ''):
        return None
    if not isinstance(settings, dict):
        raise GameCalendarError('settings must be an object', 'INVALID_IMPORT_SETTINGS', 400)
    timer_seconds, max_hints, timer_enabled = validate_setting_values(
        game_type,
        settings.get('timer_seconds'),
        settings.get('max_hints'),
        settings.get('timer_enabled', True),
    )
    data = {
        'timer_seconds': timer_seconds,
        'timer_enabled': timer_enabled,
    }
    if GAME_RULES[normalize_game_type(game_type)]['requires_max_hints']:
        data['max_hints'] = max_hints
    return data


def get_existing_calendar_dates(school_id, book_id, game_type, play_dates):
    if not play_dates:
        return set()
    rows = (
        GameCalendarEntry.query
        .with_entities(GameCalendarEntry.play_date)
        .filter(
            GameCalendarEntry.shcool_id == school_id,
            GameCalendarEntry.book_id == book_id,
            GameCalendarEntry.game_type == normalize_game_type(game_type),
            GameCalendarEntry.play_date.in_(list(play_dates)),
        )
        .all()
    )
    return {row[0] for row in rows}


def preview_calendar_import_payload(
    school_id,
    book_id,
    game_type,
    payload,
    overwrite=False,
    existing_dates=None,
    validate_settings=True,
):
    game_type = normalize_game_type(game_type)
    overwrite = parse_bool_value(overwrite, 'overwrite', default=False)
    validate_import_metadata(payload, book_id, game_type)
    days = get_import_days(payload)

    rows = []
    valid_entries = []
    parsed_dates = []
    seen_dates = set()
    duplicate_dates = set()

    for index, raw_day in enumerate(days, start=1):
        row = {
            'row': index,
            'valid': False,
            'status': 'invalid',
            'date': None,
            'words': [],
            'errors': [],
        }
        if not isinstance(raw_day, dict):
            row['errors'].append('Each day must be an object')
            rows.append(row)
            continue

        try:
            play_date = parse_play_date(raw_day.get('date') or raw_day.get('play_date'), 'date')
            row['date'] = play_date.isoformat()
            if play_date in seen_dates:
                duplicate_dates.add(play_date)
                row['errors'].append('Duplicate date in this JSON file')
                rows.append(row)
                continue
            seen_dates.add(play_date)

            words = validate_words_for_game(
                game_type,
                normalize_import_words(raw_day.get('words')),
            )
            row['words'] = words
            row['valid'] = True
            parsed_dates.append(play_date)
            valid_entries.append({
                'date': play_date,
                'words': words,
                'row': index,
            })
            rows.append(row)
        except GameCalendarError as error:
            row['errors'].append(error.message)
            rows.append(row)

    if existing_dates is None:
        existing_dates = get_existing_calendar_dates(school_id, book_id, game_type, parsed_dates)
    else:
        existing_dates = {
            parse_play_date(value) if not isinstance(value, date) else value
            for value in existing_dates
        }

    created = 0
    updated = 0
    skipped_existing = 0
    valid_entries_by_row = {entry['row']: entry for entry in valid_entries}
    for row in rows:
        if not row['valid']:
            continue
        entry = valid_entries_by_row[row['row']]
        exists = entry['date'] in existing_dates
        row['existing'] = exists
        if exists and not overwrite:
            row['status'] = 'skip_existing'
            skipped_existing += 1
        elif exists:
            row['status'] = 'update'
            updated += 1
        else:
            row['status'] = 'create'
            created += 1

    settings = None
    if validate_settings:
        settings = get_import_setting_values(game_type, payload)
    else:
        try:
            settings = get_import_setting_values(game_type, payload)
        except GameCalendarError:
            settings = None

    return {
        'school_id': school_id,
        'shcool_id': school_id,
        'book_id': book_id,
        'game_type': game_type,
        'overwrite': overwrite,
        'words_per_day': get_words_per_day(game_type),
        'total_days': len(days),
        'valid_days': len(valid_entries),
        'invalid_days': len([row for row in rows if not row['valid']]),
        'duplicate_dates': [value.isoformat() for value in sorted(duplicate_dates)],
        'created': created,
        'updated': updated,
        'skipped_existing': skipped_existing,
        'rows': rows,
        'valid_entries': valid_entries,
        'settings': settings,
    }


def import_calendar_payload(school_id, book_id, game_type, payload, overwrite=False, validate_settings=False):
    preview = preview_calendar_import_payload(
        school_id,
        book_id,
        game_type,
        payload,
        overwrite=overwrite,
        validate_settings=validate_settings,
    )
    if preview['invalid_days']:
        raise GameCalendarError('Fix invalid calendar rows before importing', 'INVALID_IMPORT_ROWS', 400)

    created = 0
    updated = 0
    skipped_existing = 0
    row_statuses = {
        row['row']: row['status']
        for row in preview['rows']
        if row.get('valid')
    }

    for entry_data in preview['valid_entries']:
        status = row_statuses.get(entry_data['row'])
        if status == 'skip_existing':
            skipped_existing += 1
            continue

        _, was_created = upsert_calendar_entry(
            school_id,
            book_id,
            game_type,
            entry_data['date'],
            entry_data['words'],
        )
        if was_created:
            created += 1
        else:
            updated += 1

    result = dict(preview)
    result['created'] = created
    result['updated'] = updated
    result['skipped_existing'] = skipped_existing
    return result


def get_calendar_entries_query(school_id, book_id, game_type, start_date=None, end_date=None):
    game_type = normalize_game_type(game_type)
    query = GameCalendarEntry.query.filter_by(
        shcool_id=school_id,
        book_id=book_id,
        game_type=game_type
    )
    if start_date:
        query = query.filter(GameCalendarEntry.play_date >= start_date)
    if end_date:
        query = query.filter(GameCalendarEntry.play_date <= end_date)
    return query.order_by(GameCalendarEntry.play_date.asc())


def upsert_calendar_entry(school_id, book_id, game_type, play_date, words):
    game_type = normalize_game_type(game_type)
    play_date = parse_play_date(play_date, 'play_date')
    words = validate_words_for_game(game_type, words)
    entry = GameCalendarEntry.query.filter_by(
        shcool_id=school_id,
        book_id=book_id,
        game_type=game_type,
        play_date=play_date
    ).first()
    created = False
    if not entry:
        entry = GameCalendarEntry(
            shcool_id=school_id,
            book_id=book_id,
            game_type=game_type,
            play_date=play_date,
            words=words
        )
        db.session.add(entry)
        created = True
    else:
        entry.words = list(words)
        entry.updated_at = datetime.now()
    return entry, created


def delete_calendar_entry(school_id, book_id, game_type, play_date):
    game_type = normalize_game_type(game_type)
    play_date = parse_play_date(play_date, 'play_date')
    entry = GameCalendarEntry.query.filter_by(
        shcool_id=school_id,
        book_id=book_id,
        game_type=game_type,
        play_date=play_date
    ).first()
    if not entry:
        return False
    db.session.delete(entry)
    return True


def group_words(words, group_size):
    complete_group_count = len(words) // group_size
    return [
        words[index * group_size:(index + 1) * group_size]
        for index in range(complete_group_count)
    ]


def generate_calendar_entries(school_id, book_id, game_type, start_date, overwrite=False):
    game_type = normalize_game_type(game_type)
    start_date = parse_play_date(start_date, 'start_date')
    book_text = Book_text.query.filter_by(book_id=book_id).first()
    if not book_text or not book_text.text:
        raise GameCalendarError('Book text not found', 'BOOK_TEXT_NOT_FOUND', 404)

    words = clean_words_from_text(book_text.text)
    words_per_day = get_words_per_day(game_type)
    groups = group_words(words, words_per_day)
    used_words = len(groups) * words_per_day

    created = 0
    skipped = 0
    updated = 0

    for index, word_group in enumerate(groups):
        play_date = start_date + timedelta(days=index)
        entry = GameCalendarEntry.query.filter_by(
            shcool_id=school_id,
            book_id=book_id,
            game_type=game_type,
            play_date=play_date
        ).first()

        if entry:
            if overwrite:
                entry.words = list(word_group)
                entry.updated_at = datetime.now()
                updated += 1
            else:
                skipped += 1
            continue

        db.session.add(GameCalendarEntry(
            shcool_id=school_id,
            book_id=book_id,
            game_type=game_type,
            play_date=play_date,
            words=list(word_group)
        ))
        created += 1

    return {
        'school_id': school_id,
        'shcool_id': school_id,
        'book_id': book_id,
        'game_type': game_type,
        'start_date': start_date.isoformat(),
        'end_date': (start_date + timedelta(days=len(groups) - 1)).isoformat() if groups else None,
        'words_per_day': words_per_day,
        'total_words': len(words),
        'created': created,
        'skipped': skipped,
        'updated': updated,
        'unused': len(words) - used_words,
    }


def get_player_game_payload(school_id, book_id, game_type, play_date=None, school=None):
    game_type = normalize_game_type(game_type)
    if play_date is None:
        play_date = get_school_local_date(school)
    else:
        play_date = parse_play_date(play_date)

    setting = SchoolGameSetting.query.filter_by(shcool_id=school_id, game_type=game_type).first()
    if not setting:
        raise GameCalendarError('Game settings are missing for this school', 'MISSING_GAME_SETTINGS', 409)

    entry = GameCalendarEntry.query.filter_by(
        shcool_id=school_id,
        book_id=book_id,
        game_type=game_type,
        play_date=play_date
    ).first()
    if not entry:
        raise GameCalendarError('Game calendar entry not found for this date', 'GAME_CALENDAR_ENTRY_NOT_FOUND', 404)

    words = validate_words_for_game(game_type, entry.words or [], status_code=409)
    payload = {
        'book_id': book_id,
        'school_id': school_id,
        'shcool_id': school_id,
        'game_type': game_type,
        'date': play_date.isoformat(),
        'words': words,
        'timer_seconds': setting.timer_seconds,
        'timer_enabled': setting.timer_enabled,
    }
    if game_type == GAME_INTELLECT_LINK:
        if setting.max_hints is None:
            raise GameCalendarError('max_hints is missing for intellect-link', 'MAX_HINTS_REQUIRED', 409)
        payload['max_hints'] = setting.max_hints
    return payload
