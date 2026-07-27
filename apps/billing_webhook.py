## @file
# @brief Stripe webhook receiver.
#
# Deliberately its own blueprint, unauthenticated and outside /admin: Stripe
# posts here server-to-server with no session, and authenticity is established
# by the signature header rather than by a login. The signature check is the
# only thing standing between this endpoint and anyone marking any invoice
# paid, so it is never optional -- construct_webhook_event() refuses to run
# without a signing secret configured.
import logging

from flask import Blueprint, jsonify, request

from apps.stripe_billing import (
    StripeNotConfigured,
    construct_webhook_event,
    handle_webhook_event,
)
from extensions import db

billing = Blueprint('billing', __name__, url_prefix='/billing')


@billing.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    signature = request.headers.get('Stripe-Signature')

    if not signature:
        return jsonify({'message': 'Missing signature'}), 400

    try:
        event = construct_webhook_event(payload, signature)
    except StripeNotConfigured as error:
        logging.error('Stripe webhook rejected: %s', error)
        return jsonify({'message': str(error)}), 503
    except ValueError as error:
        # Malformed JSON.
        logging.warning('Stripe webhook payload could not be parsed: %s', error)
        return jsonify({'message': 'Invalid payload'}), 400
    except Exception as error:
        # SignatureVerificationError and anything else: never say which, and
        # never process it.
        logging.warning('Stripe webhook signature verification failed: %s', error)
        return jsonify({'message': 'Invalid signature'}), 400

    try:
        result = handle_webhook_event(event)
    except Exception as error:
        db.session.rollback()
        logging.error('Stripe webhook handling failed: %s', error, exc_info=True)
        # A 500 makes Stripe retry with backoff, which is what we want for a
        # transient database problem.
        return jsonify({'message': 'Webhook handling failed'}), 500

    return jsonify({'received': True, 'result': result}), 200
