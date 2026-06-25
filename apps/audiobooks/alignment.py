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
            })
    return transcript_words


def get_alignment_duration_ms(transcript_words, audio_duration_ms=None):
    if not transcript_words:
        return int(audio_duration_ms) if audio_duration_ms else None
    transcript_duration_ms = max(word['endMs'] for word in transcript_words)
    if audio_duration_ms:
        return max(int(audio_duration_ms), transcript_duration_ms)
    return transcript_duration_ms


def clean_transcribed_text(text):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    text = re.sub(r'([([{])\s+', r'\1', text)
    return text


def format_transcribed_text(transcript_result, transcript_words):
    segment_text = ' '.join(
        str(segment.get('text') or '').strip()
        for segment in transcript_result.get('segments') or []
        if str(segment.get('text') or '').strip()
    )
    word_text = ' '.join(word['text'] for word in transcript_words)
    return clean_transcribed_text(segment_text or word_text)


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
                    'matched'
                )
                matched_count += 1
            continue

        if tag == 'replace' and len(current_official_words) == len(current_transcript_words):
            for official_word, transcript_word in zip(current_official_words, current_transcript_words):
                if word_similarity(normalize_word(official_word['text']), transcript_word['normalized']) >= 0.72:
                    aligned_words_by_index[official_word['index']] = build_matched_word(
                        official_word,
                        transcript_word,
                        'matched'
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
    requires_review = bool(unmatched_official_words or extra_transcribed_words)

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
            'warnings': []
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

    official_text = format_transcribed_text(transcript_result, transcript_words)
    if not official_text:
        official_text = clean_transcribed_text(' '.join(word['text'] for word in transcript_words))
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
                'status': 'matched',
                'confidence': word.get('confidence'),
            }
            for index, word in enumerate(transcript_words)
        ],
        'review': {
            'requiresReview': False,
            'unmatchedOfficialWords': [],
            'extraTranscribedWords': [],
            'warnings': []
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

    transcribe_kwargs = {
        'temperature': 0,
    }
    if language:
        transcribe_kwargs['language'] = language
    if options.get('vad') is not None:
        transcribe_kwargs['vad'] = options.get('vad')

    try:
        return whisper.transcribe(model, audio, **transcribe_kwargs), {
            'provider': 'whisper-timestamped',
            'id': model_name,
            'device': device,
        }
    except TypeError:
        minimal_kwargs = {'language': language} if language else {}
        return whisper.transcribe(model, audio, **minimal_kwargs), {
            'provider': 'whisper-timestamped',
            'id': model_name,
            'device': device,
        }
    except Exception as error:
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
