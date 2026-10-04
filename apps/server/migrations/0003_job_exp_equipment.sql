-- E07: Base/Job dual EXP + equipment (per-slot, non-instance; unique item
-- instances stay in P2 per plan v5 Appendix C).

ALTER TABLE characters
    ADD COLUMN job_level INT NOT NULL DEFAULT 1 CHECK (job_level >= 1),
    ADD COLUMN job_exp INT NOT NULL DEFAULT 0 CHECK (job_exp >= 0);

-- One equipped item per slot (P1: weapon | armor).
CREATE TABLE character_equipment (
    principal UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    slot TEXT NOT NULL CHECK (slot IN ('weapon', 'armor')),
    item TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, slot)
);
