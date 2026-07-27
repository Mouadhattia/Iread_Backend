"""school billing contracts, invoices and the seat ledger

Adds the B2B school<->platform billing model: pricing presets, per-school
contracts, a local mirror of Stripe invoices, the billing identity needed to
raise an EU VAT invoice, and the seat-activation ledger that backs the
"remaining readers" counter.

Also adds Pack.currency. Existing pack prices were entered as TND amounts and
are deliberately NOT converted here -- iRead is an Irish company billing in
EUR, and the decision was to relabel and re-enter prices by hand rather than
apply a blanket FX conversion. Every pre-existing pack price should be treated
as needing review.

Revision ID: c9a2e5f81b34
Revises: b8e3c1a7f2d9
Create Date: 2026-07-27 00:00:00.000000

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9a2e5f81b34'
down_revision = 'b8e3c1a7f2d9'
branch_labels = None
depends_on = None


# The three contract tiers, seeded so the super admin has something to pick
# from on day one. Totals are max_seats * unit_price, matching the agreed
# commercial terms. Ranges are made non-overlapping (the terms as originally
# stated shared the 100 and 500 boundaries between two tiers).
CONTRACT_PLANS = (
    ('starter', 'Starter (up to 100 readers)', 1, 100, 1900, 190000, 1),
    ('growth', 'Growth (101-500 readers)', 101, 500, 1300, 650000, 2),
    ('scale', 'Scale (501-1000 readers)', 501, 1000, 800, 800000, 3),
)


def upgrade():
    op.create_table(
        'contract_plan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('min_seats', sa.Integer(), nullable=False),
        sa.Column('max_seats', sa.Integer(), nullable=False),
        sa.Column('unit_price_cents', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='EUR'),
        sa.Column('term_months', sa.Integer(), nullable=False, server_default='12'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_contract_plan_code'),
    )
    op.create_index('ix_contract_plan_active', 'contract_plan', ['active'])

    op.create_table(
        'school_billing_profile',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=True),
        sa.Column('billing_email', sa.String(length=255), nullable=True),
        sa.Column('billing_phone', sa.String(length=50), nullable=True),
        sa.Column('address_line1', sa.String(length=255), nullable=True),
        sa.Column('address_line2', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=120), nullable=True),
        sa.Column('region', sa.String(length=120), nullable=True),
        sa.Column('postal_code', sa.String(length=30), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=True),
        sa.Column('vat_number', sa.String(length=40), nullable=True),
        sa.Column('purchase_order_ref', sa.String(length=120), nullable=True),
        sa.Column('stripe_customer_id', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id'], ),
        sa.UniqueConstraint('shcool_id', name='uq_school_billing_profile_school'),
    )
    op.create_index('ix_school_billing_profile_stripe', 'school_billing_profile', ['stripe_customer_id'])

    op.create_table(
        'school_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('seat_limit', sa.Integer(), nullable=False),
        sa.Column('unit_price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='EUR'),
        sa.Column('term_start', sa.Date(), nullable=False),
        sa.Column('term_end', sa.Date(), nullable=False),
        sa.Column('grace_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='draft'),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('stripe_customer_id', sa.String(length=120), nullable=True),
        sa.Column('notes', sa.String(length=1000), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['contract_plan.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
    )
    op.create_index('ix_school_subscription_school', 'school_subscription', ['shcool_id'])
    op.create_index('ix_school_subscription_status', 'school_subscription', ['status'])
    op.create_index('ix_school_subscription_stripe', 'school_subscription', ['stripe_customer_id'])

    op.create_table(
        'school_invoice',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('number', sa.String(length=60), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='draft'),
        sa.Column('subtotal_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tax_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='EUR'),
        sa.Column('seats', sa.Integer(), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('stripe_invoice_id', sa.String(length=120), nullable=True),
        sa.Column('hosted_invoice_url', sa.String(length=500), nullable=True),
        sa.Column('invoice_pdf', sa.String(length=500), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id'], ),
        sa.ForeignKeyConstraint(['subscription_id'], ['school_subscription.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
        sa.UniqueConstraint('stripe_invoice_id', name='uq_school_invoice_stripe_id'),
    )
    op.create_index('ix_school_invoice_school', 'school_invoice', ['shcool_id'])
    op.create_index('ix_school_invoice_subscription', 'school_invoice', ['subscription_id'])
    op.create_index('ix_school_invoice_status', 'school_invoice', ['status'])

    op.create_table(
        'school_seat_activation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shcool_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('first_pack_id', sa.Integer(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=False),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.Column('release_reason', sa.String(length=120), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shcool_id'], ['shcool.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['subscription_id'], ['school_subscription.id'], ),
        sa.ForeignKeyConstraint(['first_pack_id'], ['pack.id'], ),
    )
    op.create_index('ix_seat_activation_school_open', 'school_seat_activation', ['shcool_id', 'released_at'])
    op.create_index('ix_seat_activation_school_user', 'school_seat_activation', ['shcool_id', 'user_id', 'released_at'])
    op.create_index('ix_school_seat_activation_user', 'school_seat_activation', ['user_id'])
    op.create_index('ix_school_seat_activation_subscription', 'school_seat_activation', ['subscription_id'])

    # Pack currency -- labels only, values untouched. See the module docstring.
    op.add_column('pack', sa.Column('currency', sa.String(length=3), nullable=False, server_default='EUR'))

    _seed_contract_plans()


def _seed_contract_plans():
    contract_plan = sa.table(
        'contract_plan',
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('min_seats', sa.Integer),
        sa.column('max_seats', sa.Integer),
        sa.column('unit_price_cents', sa.Integer),
        sa.column('total_cents', sa.Integer),
        sa.column('currency', sa.String),
        sa.column('term_months', sa.Integer),
        sa.column('active', sa.Boolean),
        sa.column('sort_order', sa.Integer),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    # A concrete datetime, not sa.func.now(): a SQL function cannot be
    # rendered as a literal, which breaks `flask db upgrade --sql` entirely.
    now = datetime.now()
    # multiinsert=False so the seed is also emitted under `flask db upgrade
    # --sql` (offline mode silently skips a batched bulk_insert), which is how
    # a DBA-applied deployment would review this migration.
    op.bulk_insert(contract_plan, [
        {
            'code': code,
            'name': name,
            'min_seats': min_seats,
            'max_seats': max_seats,
            'unit_price_cents': unit_price_cents,
            'total_cents': total_cents,
            'currency': 'EUR',
            'term_months': 12,
            'active': True,
            'sort_order': sort_order,
            'created_at': now,
            'updated_at': now,
        }
        for (code, name, min_seats, max_seats, unit_price_cents, total_cents, sort_order) in CONTRACT_PLANS
    ], multiinsert=False)


def downgrade():
    op.drop_column('pack', 'currency')

    op.drop_index('ix_school_seat_activation_subscription', table_name='school_seat_activation')
    op.drop_index('ix_school_seat_activation_user', table_name='school_seat_activation')
    op.drop_index('ix_seat_activation_school_user', table_name='school_seat_activation')
    op.drop_index('ix_seat_activation_school_open', table_name='school_seat_activation')
    op.drop_table('school_seat_activation')

    op.drop_index('ix_school_invoice_status', table_name='school_invoice')
    op.drop_index('ix_school_invoice_subscription', table_name='school_invoice')
    op.drop_index('ix_school_invoice_school', table_name='school_invoice')
    op.drop_table('school_invoice')

    op.drop_index('ix_school_subscription_stripe', table_name='school_subscription')
    op.drop_index('ix_school_subscription_status', table_name='school_subscription')
    op.drop_index('ix_school_subscription_school', table_name='school_subscription')
    op.drop_table('school_subscription')

    op.drop_index('ix_school_billing_profile_stripe', table_name='school_billing_profile')
    op.drop_table('school_billing_profile')

    op.drop_index('ix_contract_plan_active', table_name='contract_plan')
    op.drop_table('contract_plan')
