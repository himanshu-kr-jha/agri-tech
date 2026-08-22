-- Extensions AgriVardhak depends on. Run once at database creation.
CREATE EXTENSION IF NOT EXISTS postgis;      -- plot boundaries (DR-06)
CREATE EXTENSION IF NOT EXISTS vector;       -- scheme/news retrieval (DR-07)
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_bytes for uuid v7

-- UUIDv7: time-ordered ids (ADR-0009).
-- Postgres 18 ships uuidv7() natively; we are on 16, so this is the standard
-- implementation. Drop this function when the base image moves to 18.
CREATE OR REPLACE FUNCTION uuid_generate_v7()
RETURNS uuid
AS $$
DECLARE
    unix_ts_ms bytea;
    uuid_bytes bytea;
BEGIN
    unix_ts_ms := substring(int8send((extract(epoch FROM clock_timestamp()) * 1000)::bigint)
                            FROM 3);
    -- 10 random bytes for the rand_a / rand_b fields
    uuid_bytes := unix_ts_ms || gen_random_bytes(10);
    -- version 7: high nibble of byte 6
    uuid_bytes := set_byte(uuid_bytes, 6, (b'0111' || get_byte(uuid_bytes, 6)::bit(4))::bit(8)::int);
    -- variant 10xx: top two bits of byte 8
    uuid_bytes := set_byte(uuid_bytes, 8, (b'10'   || get_byte(uuid_bytes, 8)::bit(6))::bit(8)::int);
    RETURN encode(uuid_bytes, 'hex')::uuid;
END
$$ LANGUAGE plpgsql VOLATILE;
