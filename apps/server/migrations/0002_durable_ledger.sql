-- V5-13 durable quest, inventory and ledger (plan v5 Appendix C + §12.4).
--
-- Normalized durable state for the Phase-1 character record. The Phase-1
-- `characters.record` JSONB snapshot stays as the load-time fallback blob;
-- these tables are the authoritative normalized shape the worker keeps in
-- step, and the ledger tables are append-only so a restore can be reconciled
-- against what was granted.

-- Wallet columns live on the fenced characters row (one row per principal,
-- one owner_epoch fence for everything on it).
ALTER TABLE characters
    ADD COLUMN gold INT NOT NULL DEFAULT 0 CHECK (gold >= 0),
    ADD COLUMN coin INT NOT NULL DEFAULT 0 CHECK (coin >= 0);

-- Bag: 12 slots per character (BAG_CAPACITY), count 1..99 per slot.
CREATE TABLE bag_slots (
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    slot_index INT NOT NULL CHECK (slot_index >= 0 AND slot_index <= 11),
    item TEXT NOT NULL,
    count INT NOT NULL CHECK (count >= 1 AND count <= 99),
    PRIMARY KEY (principal, slot_index)
);

-- Uncapped quest-material pouch.
CREATE TABLE material_pouch (
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    item TEXT NOT NULL,
    count INT NOT NULL CHECK (count >= 0),
    PRIMARY KEY (principal, item)
);

-- Quest progress: one row per (character, quest); objectives as jsonb so new
-- objective ids never need a migration.
CREATE TABLE quest_progress (
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    quest_id TEXT NOT NULL,
    state TEXT NOT NULL,
    objectives JSONB NOT NULL DEFAULT '{}'::jsonb,
    step_ticks JSONB NOT NULL DEFAULT '{}'::jsonb,
    activated JSONB NOT NULL DEFAULT '[]'::jsonb,
    revision INT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, quest_id)
);

-- Entitlement: a claimable reward granted at most once per cycle. P1 quests
-- use cycle_id 'p1' (once ever); repeatable content later cycles the id.
CREATE TABLE reward_claims (
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    entitlement_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    op_id TEXT NOT NULL,
    content_revision TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, entitlement_id, cycle_id)
);

-- Durable op dedupe: the (principal, kind, op_id) triple with the request
-- digest and the exact result the client was answered. Same op_id + same
-- digest replays; a changed payload conflicts.
CREATE TABLE operation_results (
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    op_kind TEXT NOT NULL,
    op_id TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    result JSONB NOT NULL,
    content_revision TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, op_kind, op_id)
);

-- Append-only item movements (positive = granted, negative = consumed) per
-- item id; the restore-reconcile script sums these against bag/pouch.
CREATE TABLE item_ledger (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    op_id TEXT NOT NULL,
    item TEXT NOT NULL,
    delta INT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    content_revision TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only EXP movements (positive = granted); reconciled against
-- characters.base_exp.
CREATE TABLE exp_ledger (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    op_id TEXT NOT NULL,
    delta INT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    content_revision TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Transactional outbox: op events for downstream consumers (P2 CDC /
-- telemetry). Written in the same transaction as the grant; a simple
-- retention prune keeps the table finite until the P2 processor lands.
CREATE TABLE outbox (
    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal UUID NOT NULL,
    op_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which content revisions characters have been resolved against.
CREATE TABLE content_versions (
    content_hash TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX item_ledger_principal_idx ON item_ledger (principal);
CREATE INDEX exp_ledger_principal_idx ON exp_ledger (principal);
CREATE INDEX operation_results_principal_idx ON operation_results (principal);
