## @file
# @brief Passport certificate issuance (PRD §2). Certificates are durable
# credentials derived from the same milestones the achievement engine already
# tracks — a CEFR band cleared, or every tracked word in a book mastered — but
# unlike achievements they carry a serial and an issue date and are meant to be
# viewed/printed as part of the learner's Global Reading Passport.
#
# Issuance is idempotent: the (user_id, milestone_key) unique constraint means
# calling any of these functions repeatedly never creates a duplicate. That
# lets us both hook issuance into gameplay (cheaply, off the already-computed
# unlocked-achievements list) and reconcile lazily when the passport is viewed
# or bulk-backfilled — without double-issuing.
from models.book import Book
from models.certificate import Certificate
from extensions import db

CEFR_BAND_KIND = 'cefr_band'
BOOK_MASTERY_KIND = 'book_mastery'


def _certificate_serial(user_id, kind, cefr_level=None, book_id=None):
    if kind == CEFR_BAND_KIND:
        return 'IRP-%s-%s' % (user_id, cefr_level)
    return 'IRP-%s-B%s' % (user_id, book_id)


def _issue_if_new(user_id, milestone_key, kind, title, cefr_level=None, book_id=None):
    existing = Certificate.query.filter_by(user_id=user_id, milestone_key=milestone_key).first()
    if existing:
        return None
    certificate = Certificate(
        user_id=user_id,
        kind=kind,
        milestone_key=milestone_key,
        title=title,
        cefr_level=cefr_level,
        book_id=book_id,
        serial=_certificate_serial(user_id, kind, cefr_level=cefr_level, book_id=book_id),
    )
    db.session.add(certificate)
    return certificate


def _book_title(book_id):
    book = Book.query.get(book_id)
    return book.title if book else ('Book #%s' % book_id)


def issue_certificates_from_unlocked(user_id, unlocked):
    """Cheap path used inside submit_attempt: map the achievements that just
    unlocked this attempt onto certificates, reusing data the engine already
    computed (no extra rollup/completion queries). Returns serialized new
    certificates."""
    issued = []
    for entry in unlocked or []:
        key = entry.get('key', '')
        if key.startswith('band_cleared_'):
            level = (entry.get('level') or key[len('band_cleared_'):]).upper()
            certificate = _issue_if_new(
                user_id, key, CEFR_BAND_KIND,
                '%s Reading Level Certificate' % level, cefr_level=level,
            )
            if certificate:
                issued.append(certificate)
        elif key.startswith('book_conqueror_'):
            book_id = entry.get('book_id')
            if book_id is None:
                try:
                    book_id = int(key[len('book_conqueror_'):])
                except (TypeError, ValueError):
                    continue
            certificate = _issue_if_new(
                user_id, 'book_conqueror_%d' % book_id, BOOK_MASTERY_KIND,
                'Book Mastery: %s' % _book_title(book_id), book_id=book_id,
            )
            if certificate:
                issued.append(certificate)

    if issued:
        db.session.commit()
    return [serialize_certificate(certificate) for certificate in issued]


def issue_certificates_for_user(user_id, commit=True):
    """Reconcile: mirror the milestone achievements already persisted for this
    reader onto certificates. A certificate should exist exactly when its
    milestone achievement (band_cleared_* / book_conqueror_*) was earned, so we
    read those rows directly rather than recomputing rollups/completion — cheap
    (O(achievements)), and correct for readers who earned milestones before
    certificates existed. Used by the backfill script and as a safety net when
    the passport is viewed. Pass commit=False to let a caller (e.g. a dry-run
    backfill) flush-and-rollback instead of persisting."""
    from models.word_progress import UserAchievement

    issued = []
    for row in UserAchievement.query.filter_by(user_id=user_id).all():
        key = row.achievement_key or ''
        if key.startswith('band_cleared_'):
            level = key[len('band_cleared_'):].upper()
            certificate = _issue_if_new(
                user_id, key, CEFR_BAND_KIND,
                '%s Reading Level Certificate' % level, cefr_level=level,
            )
        elif key.startswith('book_conqueror_'):
            try:
                book_id = int(key[len('book_conqueror_'):])
            except (TypeError, ValueError):
                continue
            certificate = _issue_if_new(
                user_id, key, BOOK_MASTERY_KIND,
                'Book Mastery: %s' % _book_title(book_id), book_id=book_id,
            )
        else:
            continue
        if certificate:
            issued.append(certificate)

    if issued:
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    return [serialize_certificate(certificate) for certificate in issued]


def serialize_certificate(certificate):
    return {
        'id': certificate.id,
        'kind': certificate.kind,
        'title': certificate.title,
        'cefr_level': certificate.cefr_level,
        'book_id': certificate.book_id,
        'serial': certificate.serial,
        'issued_at': certificate.issued_at.isoformat() if certificate.issued_at else None,
    }


def get_certificates_for_user(user_id):
    return [
        serialize_certificate(certificate)
        for certificate in Certificate.query.filter_by(user_id=user_id)
        .order_by(Certificate.issued_at.desc())
        .all()
    ]
