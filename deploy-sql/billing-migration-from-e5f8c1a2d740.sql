-- Running upgrade e5f8c1a2d740 -> b3f7d9a1c6e2

ALTER TABLE school_pack_instance ADD COLUMN public BOOL NOT NULL DEFAULT 0;

ALTER TABLE school_pack_instance ADD COLUMN display_name VARCHAR(255);

ALTER TABLE school_pack_instance ALTER COLUMN public DROP DEFAULT;

UPDATE alembic_version SET version_num='b3f7d9a1c6e2' WHERE alembic_version.version_num = 'e5f8c1a2d740';

-- Running upgrade b3f7d9a1c6e2 -> a1c4f8e2b7d3

ALTER TABLE school_public_page ADD COLUMN show_public_packs BOOL NOT NULL DEFAULT 1;

ALTER TABLE school_public_page ALTER COLUMN show_public_packs DROP DEFAULT;

UPDATE alembic_version SET version_num='a1c4f8e2b7d3' WHERE alembic_version.version_num = 'b3f7d9a1c6e2';

-- Running upgrade a1c4f8e2b7d3 -> b8e3c1a7f2d9

CREATE TABLE admin_audit_logs (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    actor_id INTEGER, 
    actor_username VARCHAR(150), 
    actor_role VARCHAR(30), 
    action VARCHAR(60) NOT NULL, 
    target_type VARCHAR(60) NOT NULL, 
    target_id INTEGER, 
    details TEXT, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id)
);

UPDATE alembic_version SET version_num='b8e3c1a7f2d9' WHERE alembic_version.version_num = 'a1c4f8e2b7d3';

-- Running upgrade b8e3c1a7f2d9 -> c9a2e5f81b34

CREATE TABLE contract_plan (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    code VARCHAR(40) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    min_seats INTEGER NOT NULL, 
    max_seats INTEGER NOT NULL, 
    unit_price_cents INTEGER NOT NULL, 
    total_cents INTEGER NOT NULL, 
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR', 
    term_months INTEGER NOT NULL DEFAULT '12', 
    active BOOL NOT NULL DEFAULT 1, 
    sort_order INTEGER NOT NULL DEFAULT '0', 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_contract_plan_code UNIQUE (code)
);

CREATE INDEX ix_contract_plan_active ON contract_plan (active);

CREATE TABLE school_billing_profile (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    shcool_id INTEGER NOT NULL, 
    legal_name VARCHAR(255), 
    billing_email VARCHAR(255), 
    billing_phone VARCHAR(50), 
    address_line1 VARCHAR(255), 
    address_line2 VARCHAR(255), 
    city VARCHAR(120), 
    region VARCHAR(120), 
    postal_code VARCHAR(30), 
    country VARCHAR(2), 
    vat_number VARCHAR(40), 
    purchase_order_ref VARCHAR(120), 
    stripe_customer_id VARCHAR(120), 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(shcool_id) REFERENCES shcool (id), 
    CONSTRAINT uq_school_billing_profile_school UNIQUE (shcool_id)
);

CREATE INDEX ix_school_billing_profile_stripe ON school_billing_profile (stripe_customer_id);

CREATE TABLE school_subscription (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    shcool_id INTEGER NOT NULL, 
    plan_id INTEGER, 
    seat_limit INTEGER NOT NULL, 
    unit_price_cents INTEGER NOT NULL DEFAULT '0', 
    total_cents INTEGER NOT NULL DEFAULT '0', 
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR', 
    term_start DATE NOT NULL, 
    term_end DATE NOT NULL, 
    grace_days INTEGER NOT NULL DEFAULT '30', 
    status VARCHAR(30) NOT NULL DEFAULT 'draft', 
    auto_renew BOOL NOT NULL DEFAULT 0, 
    stripe_customer_id VARCHAR(120), 
    notes VARCHAR(1000), 
    created_by INTEGER, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(shcool_id) REFERENCES shcool (id), 
    FOREIGN KEY(plan_id) REFERENCES contract_plan (id), 
    FOREIGN KEY(created_by) REFERENCES user (id)
);

CREATE INDEX ix_school_subscription_school ON school_subscription (shcool_id);

CREATE INDEX ix_school_subscription_status ON school_subscription (status);

CREATE INDEX ix_school_subscription_stripe ON school_subscription (stripe_customer_id);

CREATE TABLE school_invoice (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    shcool_id INTEGER NOT NULL, 
    subscription_id INTEGER, 
    number VARCHAR(60), 
    status VARCHAR(30) NOT NULL DEFAULT 'draft', 
    subtotal_cents INTEGER NOT NULL DEFAULT '0', 
    tax_cents INTEGER NOT NULL DEFAULT '0', 
    total_cents INTEGER NOT NULL DEFAULT '0', 
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR', 
    seats INTEGER, 
    period_start DATE, 
    period_end DATE, 
    stripe_invoice_id VARCHAR(120), 
    hosted_invoice_url VARCHAR(500), 
    invoice_pdf VARCHAR(500), 
    issued_at DATETIME, 
    due_at DATETIME, 
    paid_at DATETIME, 
    created_by INTEGER, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(shcool_id) REFERENCES shcool (id), 
    FOREIGN KEY(subscription_id) REFERENCES school_subscription (id), 
    FOREIGN KEY(created_by) REFERENCES user (id), 
    CONSTRAINT uq_school_invoice_stripe_id UNIQUE (stripe_invoice_id)
);

CREATE INDEX ix_school_invoice_school ON school_invoice (shcool_id);

CREATE INDEX ix_school_invoice_subscription ON school_invoice (subscription_id);

CREATE INDEX ix_school_invoice_status ON school_invoice (status);

CREATE TABLE school_seat_activation (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    shcool_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    subscription_id INTEGER, 
    first_pack_id INTEGER, 
    activated_at DATETIME NOT NULL, 
    released_at DATETIME, 
    release_reason VARCHAR(120), 
    source VARCHAR(40), 
    PRIMARY KEY (id), 
    FOREIGN KEY(shcool_id) REFERENCES shcool (id), 
    FOREIGN KEY(user_id) REFERENCES user (id), 
    FOREIGN KEY(subscription_id) REFERENCES school_subscription (id), 
    FOREIGN KEY(first_pack_id) REFERENCES pack (id)
);

CREATE INDEX ix_seat_activation_school_open ON school_seat_activation (shcool_id, released_at);

CREATE INDEX ix_seat_activation_school_user ON school_seat_activation (shcool_id, user_id, released_at);

CREATE INDEX ix_school_seat_activation_user ON school_seat_activation (user_id);

CREATE INDEX ix_school_seat_activation_subscription ON school_seat_activation (subscription_id);

ALTER TABLE pack ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'EUR';

INSERT INTO contract_plan (code, name, min_seats, max_seats, unit_price_cents, total_cents, currency, term_months, active, sort_order, created_at, updated_at) VALUES ('starter', 'Starter (up to 100 readers)', 1, 100, 1900, 190000, 'EUR', 12, true, 1, '2026-07-27 15:41:31.042268', '2026-07-27 15:41:31.042268');

INSERT INTO contract_plan (code, name, min_seats, max_seats, unit_price_cents, total_cents, currency, term_months, active, sort_order, created_at, updated_at) VALUES ('growth', 'Growth (101-500 readers)', 101, 500, 1300, 650000, 'EUR', 12, true, 2, '2026-07-27 15:41:31.042268', '2026-07-27 15:41:31.042268');

INSERT INTO contract_plan (code, name, min_seats, max_seats, unit_price_cents, total_cents, currency, term_months, active, sort_order, created_at, updated_at) VALUES ('scale', 'Scale (501-1000 readers)', 501, 1000, 800, 800000, 'EUR', 12, true, 3, '2026-07-27 15:41:31.042268', '2026-07-27 15:41:31.042268');

UPDATE alembic_version SET version_num='c9a2e5f81b34' WHERE alembic_version.version_num = 'b8e3c1a7f2d9';

