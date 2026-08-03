import re
from datetime import date, datetime, timedelta

import pytz
from sqlalchemy import func

from extensions import db
from models.book_pack import Book_pack
from models.book_text import Book_text
from models.game_calendar_entry import GameCalendarEntry
from models.global_game_calendar_entry import GlobalGameCalendarEntry
from models.global_game_setting import GlobalGameSetting
from models.pack import Pack
# Pack declares `codes = relationship('Code')` by name, and models/code.py
# imports Pack back, so Pack cannot import it itself. Anything that pulls Pack
# into the mapper registry has to pull Code in too, or configuring the mappers
# fails with "expression 'Code' failed to locate a name".
from models.code import Code  # noqa: F401
from models.school_game_setting import SchoolGameSetting
from models.school_pack_instance import SchoolPackInstance


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

# How a school reads the platform-level master schedule for a global pack.
GAMES_MODE_FROM_START = 'from_start'
GAMES_MODE_GLOBAL = 'global'
SUPPORTED_GAMES_MODES = (GAMES_MODE_FROM_START, GAMES_MODE_GLOBAL)

# The calendar helpers below serve both the per-school schedule and the
# platform-level master schedule. `school_id is None` selects the master one:
# there is exactly one row per book/game/day for the whole platform, so there
# is no school to key it by. Every school-facing caller reaches these through
# `get_school_game_context`, which 403s before the school id can be None.
def is_global_scope(school_id):
    return school_id is None


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


def get_or_create_global_game_setting(game_type, timer_seconds=None, max_hints=None, timer_enabled=True):
    game_type = normalize_game_type(game_type)
    timer_seconds, max_hints, timer_enabled = validate_setting_values(
        game_type,
        timer_seconds,
        max_hints,
        timer_enabled
    )
    setting = GlobalGameSetting.query.filter_by(game_type=game_type).first()
    created = False
    if not setting:
        setting = GlobalGameSetting(game_type=game_type)
        db.session.add(setting)
        created = True

    setting.timer_seconds = timer_seconds
    setting.timer_enabled = timer_enabled
    setting.max_hints = max_hints
    setting.updated_at = datetime.now()
    return setting, created


def get_global_game_settings():
    return {setting.game_type: setting for setting in GlobalGameSetting.query.all()}


def serialize_game_setting(setting=None, game_type=None, school_id=None):
    if setting:
        game_type = setting.game_type
        school_id = getattr(setting, 'shcool_id', None)
    game_type = normalize_game_type(game_type)
    rule = GAME_RULES[game_type]

    data = {
        'game_type': game_type,
        'scope': 'school' if school_id is not None else 'global',
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
    # Master-schedule rows have no owning school; the keys stay in the payload
    # as nulls so the dashboard can render both scopes with one component.
    school_id = getattr(entry, 'shcool_id', None)
    return {
        'id': entry.id,
        'scope': 'school' if school_id is not None else 'global',
        'school_id': school_id,
        'shcool_id': school_id,
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
        'scope': 'school' if school_id is not None else 'global',
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
        'scope': 'school' if school_id is not None else 'global',
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
    model = calendar_model_for_scope(school_id)
    rows = (
        model.query
        .with_entities(model.play_date)
        .filter_by(**calendar_filters_for_scope(school_id, book_id, game_type))
        .filter(model.play_date.in_(list(play_dates)))
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


def calendar_model_for_scope(school_id):
    return GlobalGameCalendarEntry if is_global_scope(school_id) else GameCalendarEntry


def calendar_filters_for_scope(school_id, book_id, game_type):
    filters = {'book_id': book_id, 'game_type': normalize_game_type(game_type)}
    if not is_global_scope(school_id):
        filters['shcool_id'] = school_id
    return filters


def get_calendar_entries_query(school_id, book_id, game_type, start_date=None, end_date=None):
    model = calendar_model_for_scope(school_id)
    query = model.query.filter_by(**calendar_filters_for_scope(school_id, book_id, game_type))
    if start_date:
        query = query.filter(model.play_date >= start_date)
    if end_date:
        query = query.filter(model.play_date <= end_date)
    return query.order_by(model.play_date.asc())


def upsert_calendar_entry(school_id, book_id, game_type, play_date, words):
    game_type = normalize_game_type(game_type)
    play_date = parse_play_date(play_date, 'play_date')
    words = validate_words_for_game(game_type, words)
    model = calendar_model_for_scope(school_id)
    filters = calendar_filters_for_scope(school_id, book_id, game_type)
    entry = model.query.filter_by(play_date=play_date, **filters).first()
    created = False
    if not entry:
        entry = model(play_date=play_date, words=words, **filters)
        db.session.add(entry)
        created = True
    else:
        entry.words = list(words)
        entry.updated_at = datetime.now()
    return entry, created


def delete_calendar_entry(school_id, book_id, game_type, play_date):
    play_date = parse_play_date(play_date, 'play_date')
    model = calendar_model_for_scope(school_id)
    filters = calendar_filters_for_scope(school_id, book_id, game_type)
    entry = model.query.filter_by(play_date=play_date, **filters).first()
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

    model = calendar_model_for_scope(school_id)
    filters = calendar_filters_for_scope(school_id, book_id, game_type)

    created = 0
    skipped = 0
    updated = 0

    for index, word_group in enumerate(groups):
        play_date = start_date + timedelta(days=index)
        entry = model.query.filter_by(play_date=play_date, **filters).first()

        if entry:
            if overwrite:
                entry.words = list(word_group)
                entry.updated_at = datetime.now()
                updated += 1
            else:
                skipped += 1
            continue

        db.session.add(model(play_date=play_date, words=list(word_group), **filters))
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


def normalize_games_mode(value, default=GAMES_MODE_FROM_START):
    if value in (None, ''):
        return default
    normalized = str(value).strip().lower().replace('-', '_')
    if normalized not in SUPPORTED_GAMES_MODES:
        raise GameCalendarError(
            'games_mode must be one of: %s' % ', '.join(SUPPORTED_GAMES_MODES),
            'INVALID_GAMES_MODE',
            400
        )
    return normalized


def get_school_global_pack_instance_for_book(school_id, book_id):
    """The school's live subscription to a global pack that contains this book.

    A book can sit in several global packs; the earliest instance the school
    joined wins so the mapping stays stable when a school later adopts another
    pack carrying the same book.
    """
    if not school_id or not book_id:
        return None
    return (
        SchoolPackInstance.query
        .join(Pack, SchoolPackInstance.pack_id == Pack.id)
        .join(Book_pack, Book_pack.pack_id == Pack.id)
        .filter(
            SchoolPackInstance.shcool_id == school_id,
            SchoolPackInstance.active.is_(True),
            Pack.is_global_pack.is_(True),
            Pack.active.is_(True),
            Book_pack.book_id == book_id,
        )
        .order_by(SchoolPackInstance.id.asc())
        .first()
    )


def get_global_calendar_start_date(book_id):
    """Day 1 of a book's master schedule, across every game type.

    Anchoring on the book rather than one game keeps the games in the same
    relative rhythm the super admin authored -- if Intellect Link starts three
    days after Bee Genius on the master calendar, it still does for a school
    replaying from the start.
    """
    return (
        db.session.query(func.min(GlobalGameCalendarEntry.play_date))
        .filter(GlobalGameCalendarEntry.book_id == book_id)
        .scalar()
    )


def get_global_calendar_bounds(book_id, game_type=None):
    query = db.session.query(
        func.min(GlobalGameCalendarEntry.play_date),
        func.max(GlobalGameCalendarEntry.play_date),
        func.count(GlobalGameCalendarEntry.id),
    ).filter(GlobalGameCalendarEntry.book_id == book_id)
    if game_type:
        query = query.filter(GlobalGameCalendarEntry.game_type == normalize_game_type(game_type))
    start_date, end_date, total = query.one()
    return start_date, end_date, total or 0


def get_instance_anchor_date(instance):
    if getattr(instance, 'games_anchor_date', None):
        return instance.games_anchor_date
    created_at = getattr(instance, 'created_at', None)
    return created_at.date() if created_at else date.today()


def global_schedule_exists(book_id, game_type):
    return (
        GlobalGameCalendarEntry.query
        .filter_by(book_id=book_id, game_type=normalize_game_type(game_type))
        .first()
        is not None
    )


def resolve_global_play_date(instance, master_start, local_date):
    """Map a school's own calendar day onto the master schedule's day.

    In `global` mode the two are the same date, which is precisely why every
    school sees the same words on the same day and can be ranked together. In
    `from_start` mode the school's anchor day is pulled back onto master day 1
    and every later day follows the same fixed shift.

    Takes `master_start` rather than looking it up so the mapping stays a
    pure function of (mode, anchor, day).
    """
    mode = normalize_games_mode(getattr(instance, 'games_mode', None))
    if mode == GAMES_MODE_GLOBAL:
        return local_date, mode, 0

    if master_start is None:
        return None, mode, 0

    anchor = get_instance_anchor_date(instance)
    if local_date < anchor:
        raise GameCalendarError(
            'This book\'s games have not started yet for your school',
            'GAME_SCHEDULE_NOT_STARTED',
            404
        )
    shift_days = (master_start - anchor).days
    return local_date + timedelta(days=shift_days), mode, shift_days


def resolve_global_game_setting(school_id, game_type, mode):
    """Which timer/hint rules a global book plays under.

    `global` mode is a cross-school competition, so the platform's rules apply
    and the school's own setting is ignored -- otherwise a school could hand
    its readers a longer clock than everyone they are ranked against.
    """
    game_type = normalize_game_type(game_type)
    global_setting = GlobalGameSetting.query.filter_by(game_type=game_type).first()
    if mode == GAMES_MODE_GLOBAL:
        if not global_setting:
            raise GameCalendarError(
                'Platform game settings are missing for this game',
                'MISSING_GLOBAL_GAME_SETTINGS',
                409
            )
        return global_setting, True

    school_setting = SchoolGameSetting.query.filter_by(shcool_id=school_id, game_type=game_type).first()
    setting = school_setting or global_setting
    if not setting:
        raise GameCalendarError('Game settings are missing for this school', 'MISSING_GAME_SETTINGS', 409)
    return setting, school_setting is None


def get_global_player_game_payload(school_id, book_id, game_type, play_date, instance):
    game_type = normalize_game_type(game_type)
    master_date, mode, shift_days = resolve_global_play_date(
        instance,
        get_global_calendar_start_date(book_id),
        play_date
    )
    if master_date is None:
        return None

    entry = GlobalGameCalendarEntry.query.filter_by(
        book_id=book_id,
        game_type=game_type,
        play_date=master_date
    ).first()
    if not entry:
        raise GameCalendarError(
            'Game calendar entry not found for this date',
            'GAME_CALENDAR_ENTRY_NOT_FOUND',
            404
        )

    setting, from_platform = resolve_global_game_setting(school_id, game_type, mode)
    words = validate_words_for_game(game_type, entry.words or [], status_code=409)
    payload = {
        'book_id': book_id,
        'school_id': school_id,
        'shcool_id': school_id,
        'game_type': game_type,
        # `date` stays the reader's own calendar day so results, streaks and
        # the daily-run screens keep keying off the day the child played.
        'date': play_date.isoformat(),
        'master_date': master_date.isoformat(),
        'words': words,
        'timer_seconds': setting.timer_seconds,
        'timer_enabled': setting.timer_enabled,
        'scope': 'global',
        'games_mode': mode,
        'is_global_game': mode == GAMES_MODE_GLOBAL,
        'leaderboard_scope': 'global' if mode == GAMES_MODE_GLOBAL else 'school',
        'settings_source': 'platform' if from_platform else 'school',
        'schedule_shift_days': shift_days,
    }
    if game_type == GAME_INTELLECT_LINK:
        if setting.max_hints is None:
            raise GameCalendarError('max_hints is missing for intellect-link', 'MAX_HINTS_REQUIRED', 409)
        payload['max_hints'] = setting.max_hints
    return payload


def get_book_game_scope(school_id, book_id, game_type):
    """Whether this school reads the master schedule for this book/game.

    Returns the pack instance driving it, or None when the school falls back
    to the calendar it authored itself. A global pack whose book has no master
    days for this particular game still falls back, so a super admin can ship
    only some of the four games without dark-holing the rest.
    """
    if not global_schedule_exists(book_id, game_type):
        return None
    return get_school_global_pack_instance_for_book(school_id, book_id)


def get_player_game_payload(school_id, book_id, game_type, play_date=None, school=None):
    game_type = normalize_game_type(game_type)
    if play_date is None:
        play_date = get_school_local_date(school)
    else:
        play_date = parse_play_date(play_date)

    instance = get_book_game_scope(school_id, book_id, game_type)
    if instance is not None:
        payload = get_global_player_game_payload(school_id, book_id, game_type, play_date, instance)
        if payload is not None:
            return payload

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
        'scope': 'school',
        'games_mode': None,
        'is_global_game': False,
        'leaderboard_scope': 'school',
        'settings_source': 'school',
    }
    if game_type == GAME_INTELLECT_LINK:
        if setting.max_hints is None:
            raise GameCalendarError('max_hints is missing for intellect-link', 'MAX_HINTS_REQUIRED', 409)
        payload['max_hints'] = setting.max_hints
    return payload


def get_book_leaderboard_scope(school_id, book_id, game_type):
    """Where a finished round should be ranked: inside the school, or platform-wide.

    Kept separate from `get_player_game_payload` so the leaderboard endpoint
    can answer for any past day without re-validating word counts or settings.
    """
    instance = get_book_game_scope(school_id, book_id, game_type)
    if instance is None:
        return 'school', None
    mode = normalize_games_mode(getattr(instance, 'games_mode', None))
    return ('global' if mode == GAMES_MODE_GLOBAL else 'school'), instance
