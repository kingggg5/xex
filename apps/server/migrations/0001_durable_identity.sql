-- V5-12 durable character identity (plan v5 §12.3 + Appendix C).
--
-- principals: the durable owner behind the browser's long-lived principal
-- cookie (32 random bytes; only the SHA-256 hash is ever stored). Provider
-- identity (D-13) links here: one principal per (provider, subject); guests
-- keep a NULL subject and are only ever addressed by their token hash.
--
-- characters: one per principal in P1 (plan v5 Appendix C leaves multi-char
-- per principal to P2). `owner_epoch` is the join fence: every join claims
-- epoch+1 and every durable write carries the epoch it observed, so a stale
-- tab or a second device cannot overwrite the live owner's state. `record`
-- is the Phase-1 snapshot of the cross-instance CharacterRecord; V5-13
-- normalizes it into bag/quest/ledger tables and this column becomes the
-- fallback blob.
--
-- character_checkpoints: §12.1 resume point (zone/position/hp) so a restart
-- can drop the player at a recent, sane location.

CREATE TABLE principals (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'guest',
    subject TEXT,
    token_hash BYTEA NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One provider account maps to at most one principal; guests (NULL subject)
-- are excluded — a million guests must never collide on (guest, NULL).
CREATE UNIQUE INDEX principals_provider_subject
    ON principals (provider, subject)
    WHERE subject IS NOT NULL;

CREATE TABLE characters (
    principal UUID PRIMARY KEY REFERENCES principals(id) ON DELETE CASCADE,
    handle TEXT NOT NULL,
    name TEXT NOT NULL,
    level INT NOT NULL DEFAULT 1 CHECK (level >= 1),
    base_exp INT NOT NULL DEFAULT 0 CHECK (base_exp >= 0),
    owner_epoch BIGINT NOT NULL DEFAULT 0,
    revision BIGINT NOT NULL DEFAULT 1,
    best_floor INT NOT NULL DEFAULT 0 CHECK (best_floor >= 0),
    content_revision TEXT NOT NULL DEFAULT '',
    record JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE character_checkpoints (
    principal UUID PRIMARY KEY REFERENCES principals(id) ON DELETE CASCADE,
    zone TEXT NOT NULL DEFAULT '',
    x REAL NOT NULL DEFAULT 0,
    z REAL NOT NULL DEFAULT 0,
    hp INT NOT NULL DEFAULT 100 CHECK (hp >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
