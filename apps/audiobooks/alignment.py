import difflib
import glob
import os
import re
import shutil
import unicodedata
from functools import lru_cache

from config import ConfigClass


WORD_PATTERN = re.compile(r'\S+')
NORMALIZE_PATTERN = re.compile(r"[^\w']+", re.UNICODE)
INTERPOLATED_TIMING_WARNING = (
    'Word-level alignment failed, so timings were estimated from segment timestamps. '
    'Review and save the timestamps before approval.'
)
SENTENCE_END_CHARS = ('.', '!', '?', '…')
CLAUSE_END_CHARS = SENTENCE_END_CHARS + (',', ';', ':')
DEFAULT_SENTENCE_PAUSE_MS = 700
DEFAULT_LINE_BREAK_PAUSE_MS = 1200


class AudioAlignmentUnavailable(RuntimeError):
    pass


class AudioAlignmentError(RuntimeError):
    pass


def prepend_path_once(path):
    if not path or not os.path.isdir(path):
        return False
    current_paths = os.environ.get('PATH', '').split(os.pathsep)
    normalized_path = os.path.normcase(os.path.abspath(path))
    if all(os.path.normcase(os.path.abspath(item or '.')) != normalized_path for item in current_paths):
        os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
    return True


def discover_windows_ffmpeg_dir():
    local_app_data = os.environ.get('LOCALAPPDATA')
    if not local_app_data:
        return None
    pattern = os.path.join(
        local_app_data,
        'Microsoft',
        'WinGet',
        'Packages',
        'Gyan.FFmpeg_*',
        'ffmpeg-*',
        'bin',
        'ffmpeg.exe'
    )
    matches = glob.glob(pattern)
    if not matches:
        return None
    matches.sort(key=lambda item: os.path.getmtime(item), reverse=True)
    return os.path.dirname(matches[0])


def ensure_ffmpeg_available():
    configured_dir = getattr(ConfigClass, 'AUDIOBOOK_FFMPEG_DIR', '') or os.environ.get('AUDIOBOOK_FFMPEG_DIR')
    if configured_dir:
        prepend_path_once(configured_dir)

    if shutil.which('ffmpeg'):
        return shutil.which('ffmpeg')

    windows_ffmpeg_dir = discover_windows_ffmpeg_dir()
    if windows_ffmpeg_dir:
        prepend_path_once(windows_ffmpeg_dir)

    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path

    raise AudioAlignmentUnavailable(
        'FFmpeg is required for audio transcription but was not found. '
        'Install FFmpeg, reopen the terminal, or set AUDIOBOOK_FFMPEG_DIR to the folder that contains ffmpeg.exe.'
    )


def split_text_words(text):
    return [
        {
            'index': index,
            'text': match.group(0),
        }
        for index, match in enumerate(WORD_PATTERN.finditer(text or ''))
    ]


def normalize_word(word):
    normalized = unicodedata.normalize('NFKC', str(word or '')).lower()
    normalized = normalized.replace('’', "'").replace('`', "'")
    normalized = NORMALIZE_PATTERN.sub('', normalized)
    return normalized.strip("'")


def get_transcript_words(transcript_result):
    transcript_words = []
    for segment in transcript_result.get('segments') or []:
        for word in segment.get('words') or []:
            text = str(word.get('text') or word.get('word') or '').strip()
            if not text:
                continue
            start = word.get('start')
            end = word.get('end')
            try:
                start_ms = int(round(float(start) * 1000))
                end_ms = int(round(float(end) * 1000))
            except (TypeError, ValueError):
                continue
            if end_ms < start_ms:
                continue
            transcript_words.append({
                'text': text,
                'normalized': normalize_word(text),
                'startMs': max(start_ms, 0),
                'endMs': max(end_ms, start_ms + 1),
                'confidence': word.get('confidence'),
                'status': word.get('status'),
            })
    return transcript_words


def get_alignment_duration_ms(transcript_words, audio_duration_ms=None):
    if not transcript_words:
        return int(audio_duration_ms) if audio_duration_ms else None
    transcript_duration_ms = max(word['endMs'] for word in transcript_words)
    if audio_duration_ms:
        return max(int(audio_duration_ms), transcript_duration_ms)
    return transcript_duration_ms


def get_sentence_pause_ms():
    return int(getattr(ConfigClass, 'AUDIOBOOK_SENTENCE_PAUSE_MS', None) or DEFAULT_SENTENCE_PAUSE_MS)


def get_line_break_pause_ms():
    return int(getattr(ConfigClass, 'AUDIOBOOK_LINE_BREAK_PAUSE_MS', None) or DEFAULT_LINE_BREAK_PAUSE_MS)


def restore_punctuation_and_breaks(words, sentence_pause_ms=None, line_break_pause_ms=None):
    """Fill in missing sentence punctuation and paragraph breaks using inter-word silence.

    Mutates each word dict in place, only ever appending to `text` and setting a
    `lineBreakAfter` flag - the number and order of words never changes, so this
    cannot desync the word-by-word audio highlighting.
    """
    sentence_pause_ms = sentence_pause_ms if sentence_pause_ms is not None else get_sentence_pause_ms()
    line_break_pause_ms = (
        line_break_pause_ms if line_break_pause_ms is not None else get_line_break_pause_ms()
    )

    word_count = len(words)
    for index, word in enumerate(words):
        is_last = index == word_count - 1
        text = word.get('text') or ''

        gap_ms = None
        if not is_last:
            next_word = words[index + 1]
            if word.get('endMs') is not None and next_word.get('startMs') is not None:
                gap_ms = next_word['startMs'] - word['endMs']

        ends_with_sentence_punct = bool(text) and text[-1] in SENTENCE_END_CHARS
        should_break = is_last or (gap_ms is not None and gap_ms >= line_break_pause_ms)
        should_end_sentence = should_break or (gap_ms is not None and gap_ms >= sentence_pause_ms)

        if should_end_sentence and text and not ends_with_sentence_punct:
            word['text'] = text.rstrip(''.join(CLAUSE_END_CHARS)) + '.'
            text = word['text']
            ends_with_sentence_punct = True

        word['lineBreakAfter'] = bool(should_break and not is_last)

        if not is_last and ends_with_sentence_punct:
            next_word = words[index + 1]
            next_text = next_word.get('text') or ''
            if next_text and next_text[0].isalpha() and next_text[0].islower():
                next_word['text'] = next_text[0].upper() + next_text[1:]

    if words:
        first_text = words[0].get('text') or ''
        if first_text and first_text[0].isalpha() and first_text[0].islower():
            words[0]['text'] = first_text[0].upper() + first_text[1:]

    return words


def clean_rendered_text(text):
    # Collapses runs of spaces/tabs, but preserves single '\n' line breaks.
    text = re.sub(r'[^\S\n]+', ' ', str(text or ''))
    text = re.sub(r' *\n+ *', '\n', text).strip()
    text = re.sub(r' +([,.;:!?])', r'\1', text)
    text = re.sub(r'([([{]) +', r'\1', text)
    return text


def render_words_to_text(words):
    parts = []
    for index, word in enumerate(words):
        parts.append(word.get('text') or '')
        if index < len(words) - 1:
            parts.append('\n' if word.get('lineBreakAfter') else ' ')
    return clean_rendered_text(''.join(parts))


def build_matched_word(official_word, transcript_word, status='matched'):
    return {
        'index': official_word['index'],
        'text': official_word['text'],
        'startMs': transcript_word['startMs'],
        'endMs': transcript_word['endMs'],
        'status': status,
        'confidence': transcript_word.get('confidence'),
    }


def build_not_spoken_word(official_word):
    return {
        'index': official_word['index'],
        'text': official_word['text'],
        'startMs': None,
        'endMs': None,
        'status': 'not-spoken',
        'confidence': None,
    }


def word_similarity(first, second):
    if not first or not second:
        return 0
    return difflib.SequenceMatcher(None, first, second, autojunk=False).ratio()


def append_extra_transcript_words(extra_words, transcript_words):
    for transcript_word in transcript_words:
        extra_words.append({
            'text': transcript_word['text'],
            'startMs': transcript_word['startMs'],
            'endMs': transcript_word['endMs'],
            'confidence': transcript_word.get('confidence'),
            'status': transcript_word.get('status'),
        })


def build_alignment_from_transcript(
    official_text,
    transcript_result,
    audio_duration_ms=None,
    language=None,
    model_metadata=None,
):
    official_words = split_text_words(official_text)
    transcript_words = get_transcript_words(transcript_result)
    has_interpolated_timings = any(word.get('status') == 'interpolated' for word in transcript_words)
    official_norm = [normalize_word(word['text']) for word in official_words]
    transcript_norm = [word['normalized'] for word in transcript_words]

    aligned_words_by_index = {}
    unmatched_official_words = []
    extra_transcribed_words = []
    matched_count = 0

    matcher = difflib.SequenceMatcher(
        None,
        official_norm,
        transcript_norm,
        autojunk=False
    )

    for tag, official_start, official_end, transcript_start, transcript_end in matcher.get_opcodes():
        current_official_words = official_words[official_start:official_end]
        current_transcript_words = transcript_words[transcript_start:transcript_end]

        if tag == 'equal':
            for official_word, transcript_word in zip(current_official_words, current_transcript_words):
                aligned_words_by_index[official_word['index']] = build_matched_word(
                    official_word,
                    transcript_word,
                    transcript_word.get('status') or 'matched'
                )
                matched_count += 1
            continue

        if tag == 'replace' and len(current_official_words) == len(current_transcript_words):
            for official_word, transcript_word in zip(current_official_words, current_transcript_words):
                if word_similarity(normalize_word(official_word['text']), transcript_word['normalized']) >= 0.72:
                    aligned_words_by_index[official_word['index']] = build_matched_word(
                        official_word,
                        transcript_word,
                        transcript_word.get('status') or 'matched'
                    )
                    matched_count += 1
                else:
                    aligned_words_by_index[official_word['index']] = build_not_spoken_word(official_word)
                    unmatched_official_words.append({
                        'index': official_word['index'],
                        'text': official_word['text'],
                    })
                    append_extra_transcript_words(extra_transcribed_words, [transcript_word])
            continue

        for official_word in current_official_words:
            aligned_words_by_index[official_word['index']] = build_not_spoken_word(official_word)
            unmatched_official_words.append({
                'index': official_word['index'],
                'text': official_word['text'],
            })
        append_extra_transcript_words(extra_transcribed_words, current_transcript_words)

    aligned_words = [
        aligned_words_by_index.get(word['index']) or build_not_spoken_word(word)
        for word in official_words
    ]
    similarity = matched_count / len(official_words) if official_words else 0
    requires_review = bool(unmatched_official_words or extra_transcribed_words or has_interpolated_timings)
    warnings = [INTERPOLATED_TIMING_WARNING] if has_interpolated_timings else []

    return {
        'version': 1,
        'language': language or transcript_result.get('language'),
        'audioDurationMs': get_alignment_duration_ms(transcript_words, audio_duration_ms),
        'officialText': official_text,
        'transcribedText': ' '.join(word['text'] for word in transcript_words),
        'similarity': similarity,
        'model': model_metadata or {},
        'words': aligned_words,
        'review': {
            'requiresReview': requires_review,
            'unmatchedOfficialWords': unmatched_official_words,
            'extraTranscribedWords': extra_transcribed_words,
            'warnings': warnings
        }
    }


def build_alignment_from_audio_transcript(
    transcript_result,
    audio_duration_ms=None,
    language=None,
    model_metadata=None,
):
    transcript_words = get_transcript_words(transcript_result)
    if not transcript_words:
        raise AudioAlignmentError('The model did not find spoken words in this audio')
    has_interpolated_timings = any(word.get('status') == 'interpolated' for word in transcript_words)

    restore_punctuation_and_breaks(transcript_words)
    official_text = render_words_to_text(transcript_words)
    if not official_text:
        raise AudioAlignmentError('The model could not generate text from this audio')

    return {
        'version': 1,
        'language': language or transcript_result.get('language'),
        'audioDurationMs': get_alignment_duration_ms(transcript_words, audio_duration_ms),
        'officialText': official_text,
        'transcribedText': official_text,
        'similarity': 1,
        'model': model_metadata or {},
        'textSource': 'audio-transcript',
        'words': [
            {
                'index': index,
                'text': word['text'],
                'startMs': word['startMs'],
                'endMs': word['endMs'],
                'status': word.get('status') or 'matched',
                'confidence': word.get('confidence'),
                'lineBreakAfter': bool(word.get('lineBreakAfter')),
            }
            for index, word in enumerate(transcript_words)
        ],
        'review': {
            'requiresReview': has_interpolated_timings,
            'unmatchedOfficialWords': [],
            'extraTranscribedWords': [],
            'warnings': [INTERPOLATED_TIMING_WARNING] if has_interpolated_timings else []
        }
    }


@lru_cache(maxsize=4)
def get_whisper_timestamped_model(model_name, device):
    try:
        import whisper_timestamped as whisper
    except ImportError as error:
        raise AudioAlignmentUnavailable(
            'whisper-timestamped is not installed. Install requirements and make sure ffmpeg is available.'
        ) from error

    return whisper.load_model(model_name, device=device)


def is_infinite_logprob_error(error):
    return 'infinite logprob' in str(error or '').lower()


def get_timestamped_transcribe_attempts(language=None, options=None):
    options = options or {}
    base_kwargs = {
        'temperature': 0,
    }
    if language:
        base_kwargs['language'] = language
    if options.get('vad') is not None:
        base_kwargs['vad'] = options.get('vad')

    stable_kwargs = dict(base_kwargs)
    stable_kwargs.update({
        'temperature': 0.2,
        'condition_on_previous_text': False,
        'compute_word_confidence': False,
    })

    minimal_kwargs = {'language': language} if language else {}
    attempts = [base_kwargs, stable_kwargs, minimal_kwargs]
    unique_attempts = []
    seen = set()
    for attempt in attempts:
        key = tuple(sorted(attempt.items()))
        if key not in seen:
            seen.add(key)
            unique_attempts.append(attempt)
    return unique_attempts


def transcribe_with_timestamped_retries(whisper, model, audio, language=None, options=None):
    last_error = None
    for transcribe_kwargs in get_timestamped_transcribe_attempts(language, options):
        try:
            return whisper.transcribe(model, audio, **transcribe_kwargs)
        except TypeError as error:
            last_error = error
        except Exception as error:
            last_error = error
            if not is_infinite_logprob_error(error):
                raise
    if last_error:
        raise last_error
    raise AudioAlignmentError('Unable to generate model alignment')


def seconds_to_float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def estimate_segment_words(text, start_seconds, end_seconds):
    words = split_text_words(text)
    if not words:
        return []

    start_ms = max(int(round(seconds_to_float(start_seconds) * 1000)), 0)
    end_ms = max(int(round(seconds_to_float(end_seconds, start_seconds) * 1000)), start_ms + len(words))
    duration_ms = max(end_ms - start_ms, len(words))
    step_ms = duration_ms / len(words)

    estimated_words = []
    for index, word in enumerate(words):
        word_start_ms = int(round(start_ms + index * step_ms))
        word_end_ms = int(round(start_ms + (index + 1) * step_ms))
        estimated_words.append({
            'text': word['text'],
            'start': word_start_ms / 1000,
            'end': max(word_end_ms, word_start_ms + 1) / 1000,
            'confidence': None,
            'status': 'interpolated',
        })
    return estimated_words


def run_openai_whisper_segment_fallback(model, audio, language=None):
    try:
        import whisper as openai_whisper
    except ImportError as error:
        raise AudioAlignmentUnavailable(
            'whisper-timestamped failed and openai-whisper fallback is not installed.'
        ) from error

    transcribe_kwargs = {
        'temperature': 0,
        'condition_on_previous_text': False,
    }
    if language:
        transcribe_kwargs['language'] = language

    try:
        result = openai_whisper.transcribe(model, audio, **transcribe_kwargs)
    except TypeError:
        minimal_kwargs = {'language': language} if language else {}
        result = openai_whisper.transcribe(model, audio, **minimal_kwargs)

    segments = []
    for segment in result.get('segments') or []:
        text = str(segment.get('text') or '').strip()
        if not text:
            continue
        estimated_segment = dict(segment)
        estimated_segment['words'] = estimate_segment_words(
            text,
            segment.get('start'),
            segment.get('end')
        )
        segments.append(estimated_segment)

    fallback_result = dict(result)
    fallback_result['segments'] = segments
    return fallback_result


def run_whisper_timestamped(audio_path, language=None, options=None):
    if not audio_path or not os.path.exists(audio_path):
        raise AudioAlignmentError('Audio file is missing')

    ensure_ffmpeg_available()

    try:
        import whisper_timestamped as whisper
    except ImportError as error:
        raise AudioAlignmentUnavailable(
            'whisper-timestamped is not installed. Install requirements and make sure ffmpeg is available.'
        ) from error

    options = options or {}
    model_name = options.get('model') or ConfigClass.AUDIOBOOK_ALIGNMENT_MODEL
    device = options.get('device') or ConfigClass.AUDIOBOOK_ALIGNMENT_DEVICE
    model = get_whisper_timestamped_model(model_name, device)

    try:
        audio = whisper.load_audio(audio_path)
    except FileNotFoundError as error:
        raise AudioAlignmentUnavailable(
            'Unable to run FFmpeg for this audio file. Reopen the terminal after installing FFmpeg, '
            'or set AUDIOBOOK_FFMPEG_DIR to the folder that contains ffmpeg.exe.'
        ) from error
    except Exception as error:
        raise AudioAlignmentError(f'Unable to read audio file: {error}') from error

    metadata = {
        'provider': 'whisper-timestamped',
        'id': model_name,
        'device': device,
    }

    try:
        return transcribe_with_timestamped_retries(
            whisper,
            model,
            audio,
            language=language,
            options=options,
        ), metadata
    except Exception as error:
        if is_infinite_logprob_error(error):
            fallback_metadata = dict(metadata)
            fallback_metadata.update({
                'provider': 'openai-whisper-segment-fallback',
                'fallbackFrom': 'whisper-timestamped',
                'warning': INTERPOLATED_TIMING_WARNING,
            })
            return run_openai_whisper_segment_fallback(model, audio, language=language), fallback_metadata
        raise AudioAlignmentError(f'Unable to generate model alignment: {error}') from error


def generate_model_alignment(audio_path, official_text=None, audio_duration_ms=None, language=None, options=None):
    transcript_result, model_metadata = run_whisper_timestamped(
        audio_path,
        language=language,
        options=options
    )
    if not str(official_text or '').strip():
        return build_alignment_from_audio_transcript(
            transcript_result,
            audio_duration_ms=audio_duration_ms,
            language=language,
            model_metadata=model_metadata,
        )
    return build_alignment_from_transcript(
        official_text,
        transcript_result,
        audio_duration_ms=audio_duration_ms,
        language=language,
        model_metadata=model_metadata,
    )
