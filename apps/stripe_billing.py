## @file
# @brief Stripe integration for school contracts (B2B).
#
# Scope note: this bills *schools* for their seat licence. It is unrelated to
# the legacy invoicing microservice (invoicing.iread.education), which bills
# *parents* for packs and has no concept of a school. Do not merge the two
# without a migration plan -- they have different customers, products and
# lifecycles.
#
# Why Stripe Invoicing rather than Stripe Subscriptions: a school pays an
# annual licence against a purchase order, typically by bank transfer, after
# their finance office approves it. Subscriptions auto-charge a stored card,
# which most schools cannot provide. `collection_method='send_invoice'` gives
# them a hosted invoice with a due date, payable by card or SEPA, and a PDF
# their accounts department can file.
#
# Every function here is a no-op-with-error when STRIPE_SECRET_KEY is unset,
# so the rest of the app runs normally on a machine with no Stripe access.
import logging
from datetime import datetime, timedelta

from config import ConfigClass
from extensions import db
from models.school_billing_profile import SchoolBillingProfile
from models.school_invoice import (
    INVOICE_DRAFT,
    INVOICE_OPEN,
    INVOICE_PAID,
    INVOICE_UNCOLLECTIBLE,
    INVOICE_VOID,
    SchoolInvoice,
)
from models.school_subscription import STATUS_ACTIVE, STATUS_PENDING_PAYMENT

try:
    import stripe
except ImportError:  # pragma: no cover - stripe is an install-time dependency
    stripe = None


class StripeNotConfigured(Exception):
    """Raised when a Stripe-backed action is attempted without credentials."""


##
# @brief Returns the configured stripe module, or raises StripeNotConfigured.
def get_stripe():
    if stripe is None:
        raise StripeNotConfigured('The stripe package is not installed on this server.')
    secret_key = getattr(ConfigClass, 'STRIPE_SECRET_KEY', '')
    if not secret_key:
        raise StripeNotConfigured(
            'Stripe is not configured. Set STRIPE_SECRET_KEY in the environment.'
        )
    stripe.api_key = secret_key
    return stripe


def is_configured():
    return bool(stripe is not None and getattr(ConfigClass, 'STRIPE_SECRET_KEY', ''))


##
# @brief Read a field from a Stripe response.
#
# Stripe's SDK returns StripeObject, which supports both attribute and mapping
# access, but webhook payloads round-tripped through JSON are plain dicts. Going
# through one accessor everywhere means the same code path serves live API
# responses, webhook bodies and test doubles.
def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


##
# @brief Build the Stripe address dict from a school's billing profile.
# Stripe Tax needs at least a country to determine VAT treatment.
def _address_from_profile(profile):
    if profile is None:
        return None
    address = {
        'line1': profile.address_line1,
        'line2': profile.address_line2,
        'city': profile.city,
        'state': profile.region,
        'postal_code': profile.postal_code,
        'country': profile.country,
    }
    return {key: value for key, value in address.items() if value}


##
# @brief Find or create the Stripe Customer for a school, keeping its details
# in step with the billing profile.
#
# The Stripe customer id is stored on the billing profile so a school keeps one
# customer across contracts -- Stripe's dashboard then shows the school's whole
# billing history in one place.
def ensure_customer(school, profile=None):
    api = get_stripe()

    if profile is None:
        profile = SchoolBillingProfile.query.filter_by(shcool_id=school.id).first()
    if profile is None:
        raise ValueError(
            'Add billing details for this school before raising an invoice: '
            'an EU VAT invoice needs a legal name, address and country.'
        )
    if not profile.country:
        raise ValueError('A billing country is required before invoicing (e.g. IE).')

    payload = {
        'name': profile.legal_name or school.name,
        'email': profile.billing_email,
        'metadata': {'school_id': str(school.id), 'school_name': school.name},
    }
    address = _address_from_profile(profile)
    if address:
        payload['address'] = address

    if profile.stripe_customer_id:
        customer = api.Customer.modify(profile.stripe_customer_id, **payload)
    else:
        customer = api.Customer.create(**payload)
        profile.stripe_customer_id = customer.id
        db.session.add(profile)

    _sync_tax_id(api, profile)
    return customer


##
# @brief Attach the school's VAT number to its Stripe customer.
#
# This is what makes EU B2B reverse charge work: with a valid VAT number for a
# business outside Ireland, Stripe Tax zero-rates the invoice and marks it
# "reverse charge". Without one the customer is treated as a consumer and
# charged Irish VAT.
def _sync_tax_id(api, profile):
    if not profile.vat_number or not profile.stripe_customer_id:
        return
    try:
        existing = api.Customer.list_tax_ids(profile.stripe_customer_id, limit=100)
        for tax_id in existing.get('data', []):
            if tax_id.get('value') == profile.vat_number:
                return
            # A school's VAT number changing is rare but must not leave the old
            # one attached, or Stripe may apply the wrong treatment.
            api.Customer.delete_tax_id(profile.stripe_customer_id, tax_id.get('id'))
        api.Customer.create_tax_id(
            profile.stripe_customer_id, type='eu_vat', value=profile.vat_number
        )
    except Exception as error:
        # A malformed VAT number should not block invoicing -- Stripe will
        # simply charge VAT normally, which is the safe default.
        logging.warning('Could not sync VAT number for school profile %s: %s',
                        profile.id, error)


##
# @brief Raise and send the annual licence invoice for a contract.
#
# Creates the invoice item, finalizes the invoice and emails it to the school,
# then mirrors the result locally. The local SchoolInvoice row is written from
# Stripe's response rather than from our own assumptions, so the tax figures
# shown in the dashboard are the ones actually charged.
#
# @return the local SchoolInvoice row.
def create_and_send_invoice(subscription, school, created_by=None, description=None):
    api = get_stripe()

    profile = SchoolBillingProfile.query.filter_by(shcool_id=school.id).first()
    customer = ensure_customer(school, profile)
    db.session.flush()

    seats = subscription.seat_limit
    currency = (subscription.currency or ConfigClass.BILLING_CURRENCY).lower()
    amount_cents = int(subscription.total_cents or 0)
    if amount_cents <= 0:
        raise ValueError('This contract has no value to invoice. Set a contract total first.')

    line_description = description or (
        'iRead annual licence — %s reader places (%s to %s)' % (
            seats,
            subscription.term_start.isoformat() if subscription.term_start else '',
            subscription.term_end.isoformat() if subscription.term_end else ''
        )
    )

    invoice_kwargs = {
        'customer': customer.id,
        'collection_method': 'send_invoice',
        'days_until_due': ConfigClass.INVOICE_DUE_DAYS,
        'currency': currency,
        'metadata': {
            'school_id': str(school.id),
            'subscription_id': str(subscription.id),
            'seats': str(seats),
        },
        'pending_invoice_items_behavior': 'exclude',
    }
    if ConfigClass.STRIPE_TAX_ENABLED:
        invoice_kwargs['automatic_tax'] = {'enabled': True}

    invoice = api.Invoice.create(**invoice_kwargs)
    invoice_id = _get(invoice, 'id')

    # Attach the line to this specific invoice so a second, concurrent invoice
    # for another contract cannot swallow it.
    api.InvoiceItem.create(
        customer=_get(customer, 'id'),
        invoice=invoice_id,
        currency=currency,
        amount=amount_cents,
        description=line_description,
    )

    invoice = api.Invoice.finalize_invoice(invoice_id)
    invoice = api.Invoice.send_invoice(_get(invoice, 'id', invoice_id))

    local_invoice = upsert_invoice_from_stripe(invoice, school_id=school.id,
                                               subscription_id=subscription.id,
                                               seats=seats, created_by=created_by)

    # The contract is now awaiting payment; the seat cap applies immediately so
    # a school is never blocked while its finance office processes the invoice.
    if subscription.status not in (STATUS_ACTIVE,):
        subscription.status = STATUS_PENDING_PAYMENT
        db.session.add(subscription)

    db.session.flush()
    _notify(lambda: _notifications().notify_licence_invoice_issued(school.id, local_invoice))

    return local_invoice


##
# @brief Imported lazily -- apps.notifications pulls in a wide slice of the
# model graph that this module otherwise has no use for.
def _notifications():
    import apps.notifications as notifications
    return notifications


##
# @brief Run a notification side effect without letting it break the billing
# action that triggered it. A failed notification must never roll back a
# successfully raised invoice.
def _notify(callback):
    try:
        callback()
    except Exception as error:
        logging.warning('Billing notification failed: %s', error, exc_info=True)


##
# @brief Void an invoice that should never be paid (raised in error).
def void_invoice(local_invoice):
    api = get_stripe()
    if not local_invoice.stripe_invoice_id:
        local_invoice.status = INVOICE_VOID
        db.session.add(local_invoice)
        return local_invoice
    invoice = api.Invoice.void_invoice(local_invoice.stripe_invoice_id)
    return upsert_invoice_from_stripe(invoice, school_id=local_invoice.shcool_id,
                                      subscription_id=local_invoice.subscription_id,
                                      seats=local_invoice.seats)


def _timestamp_to_datetime(value):
    return datetime.fromtimestamp(value) if value else None


def _date_from_timestamp(value):
    moment = _timestamp_to_datetime(value)
    return moment.date() if moment else None


##
# @brief Mirror a Stripe invoice object into the local SchoolInvoice table.
#
# Keyed on stripe_invoice_id so it is safe to call repeatedly -- webhooks can
# arrive out of order and more than once, and Stripe explicitly requires
# handlers to be idempotent.
def upsert_invoice_from_stripe(invoice, school_id=None, subscription_id=None,
                               seats=None, created_by=None):
    stripe_id = _get(invoice, 'id')
    local_invoice = SchoolInvoice.query.filter_by(stripe_invoice_id=stripe_id).first()

    def field(name, default=None):
        return _get(invoice, name, default)

    metadata = field('metadata') or {}
    resolved_school_id = school_id or _int_or_none(metadata.get('school_id'))
    resolved_subscription_id = subscription_id or _int_or_none(metadata.get('subscription_id'))
    resolved_seats = seats if seats is not None else _int_or_none(metadata.get('seats'))

    if local_invoice is None:
        if resolved_school_id is None:
            # An invoice raised outside this app (or for the legacy B2C flow)
            # has nothing to attach to locally; ignore rather than guess.
            return None
        local_invoice = SchoolInvoice(
            shcool_id=resolved_school_id,
            subscription_id=resolved_subscription_id,
            stripe_invoice_id=stripe_id,
            created_by=created_by,
        )

    local_invoice.number = field('number') or local_invoice.number
    local_invoice.status = _map_status(field('status'))
    local_invoice.subtotal_cents = field('subtotal') or 0
    local_invoice.tax_cents = field('tax') or 0
    local_invoice.total_cents = field('total') or 0
    local_invoice.currency = (field('currency') or ConfigClass.BILLING_CURRENCY).upper()
    local_invoice.hosted_invoice_url = field('hosted_invoice_url')
    local_invoice.invoice_pdf = field('invoice_pdf')
    local_invoice.due_at = _timestamp_to_datetime(field('due_date'))
    local_invoice.issued_at = (
        _timestamp_to_datetime(field('status_transitions', {}).get('finalized_at')
                               if isinstance(field('status_transitions'), dict) else None)
        or local_invoice.issued_at
        or datetime.now()
    )
    if resolved_seats is not None:
        local_invoice.seats = resolved_seats
    if resolved_subscription_id and local_invoice.subscription_id is None:
        local_invoice.subscription_id = resolved_subscription_id

    period_start = field('period_start')
    period_end = field('period_end')
    if period_start:
        local_invoice.period_start = _date_from_timestamp(period_start)
    if period_end:
        local_invoice.period_end = _date_from_timestamp(period_end)

    if local_invoice.status == INVOICE_PAID and local_invoice.paid_at is None:
        transitions = field('status_transitions')
        paid_at = transitions.get('paid_at') if isinstance(transitions, dict) else None
        local_invoice.paid_at = _timestamp_to_datetime(paid_at) or datetime.now()

    db.session.add(local_invoice)
    return local_invoice


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


##
# @brief Stripe's invoice statuses map 1:1 onto ours, with 'uncollectible'
# spelled the same and anything unknown treated as a draft.
def _map_status(status):
    known = {
        'draft': INVOICE_DRAFT,
        'open': INVOICE_OPEN,
        'paid': INVOICE_PAID,
        'void': INVOICE_VOID,
        'uncollectible': INVOICE_UNCOLLECTIBLE,
    }
    return known.get(status, INVOICE_DRAFT)


##
# @brief Verify a webhook payload and return the parsed event.
#
# Refuses outright when no signing secret is configured: an unverified endpoint
# would let anyone POST an "invoice.paid" event and activate a contract for
# free.
def construct_webhook_event(payload, signature_header):
    api = get_stripe()
    secret = getattr(ConfigClass, 'STRIPE_WEBHOOK_SECRET', '')
    if not secret:
        raise StripeNotConfigured(
            'STRIPE_WEBHOOK_SECRET is not set; refusing to process unverified webhooks.'
        )
    return api.Webhook.construct_event(payload, signature_header, secret)


##
# @brief Apply a verified Stripe event to local state.
#
# Handles the invoice lifecycle only. Unknown event types are ignored rather
# than erroring, so enabling extra events in the Stripe dashboard cannot break
# the endpoint.
#
# @return a short string describing what was done, for the response body.
def handle_webhook_event(event):
    event_type = _get(event, 'type')
    data_object = _get(_get(event, 'data', {}) or {}, 'object')

    if not event_type or not event_type.startswith('invoice.'):
        return 'ignored:%s' % event_type

    local_invoice = upsert_invoice_from_stripe(data_object)
    if local_invoice is None:
        return 'ignored:unknown-invoice'

    if event_type == 'invoice.paid':
        _activate_subscription_for(local_invoice)
        db.session.flush()
        _notify(lambda: _notifications().notify_licence_invoice_paid(
            local_invoice.shcool_id, local_invoice))

    db.session.commit()
    return 'handled:%s' % event_type


##
# @brief A paid licence invoice puts its contract live.
def _activate_subscription_for(local_invoice):
    subscription = local_invoice.subscription
    if subscription is None:
        return
    subscription.status = STATUS_ACTIVE
    db.session.add(subscription)


##
# @brief Contracts whose term has ended, for the (Phase 4) expiry sweep.
def find_expired_subscriptions(as_of=None):
    from models.school_subscription import SchoolSubscription  # local: avoids a cycle
    as_of = as_of or datetime.now().date()
    return (
        SchoolSubscription.query
        .filter(SchoolSubscription.term_end < as_of)
        .filter(SchoolSubscription.status.in_((STATUS_ACTIVE, STATUS_PENDING_PAYMENT)))
        .all()
    )


##
# @brief Whether a contract is inside its post-term grace window.
def is_in_grace(subscription, as_of=None):
    if subscription is None or subscription.term_end is None:
        return False
    as_of = as_of or datetime.now().date()
    grace_end = subscription.term_end + timedelta(days=subscription.grace_days or 0)
    return subscription.term_end < as_of <= grace_end
