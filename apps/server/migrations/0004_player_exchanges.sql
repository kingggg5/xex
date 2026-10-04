-- Pair receipt and both character writes share a transaction. IDs survive retries/restarts.
CREATE TABLE player_exchanges (
    id TEXT PRIMARY KEY,
    principals JSONB NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
