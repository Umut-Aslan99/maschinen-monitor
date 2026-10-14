-- Maschinen-Monitor schema. Times are UTC (timestamptz); shifts are computed in Europe/Berlin by the app.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE machine (
    id        text PRIMARY KEY,
    name      text NOT NULL,
    kind      text NOT NULL,
    cycle_s   double precision NOT NULL,
    position  int NOT NULL
);

-- Telemetry in long format: one row per machine, signal and sample.
CREATE TABLE telemetry (
    time        timestamptz NOT NULL,
    machine_id  text NOT NULL REFERENCES machine (id),
    signal      text NOT NULL,
    value       double precision NOT NULL,
    UNIQUE (machine_id, signal, time)          -- MQTT may deliver twice: inserts are idempotent
);
SELECT create_hypertable('telemetry', by_range('time', INTERVAL '1 day'));
ALTER TABLE telemetry SET (timescaledb.compress, timescaledb.compress_segmentby = 'machine_id, signal',
                           timescaledb.compress_orderby = 'time DESC');
SELECT add_compression_policy('telemetry', INTERVAL '2 days');
SELECT add_retention_policy('telemetry', INTERVAL '14 days');

-- One-minute aggregates for longer chart ranges, kept up to date by TimescaleDB (recent minutes computed on the fly).
CREATE MATERIALIZED VIEW telemetry_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 minute', time) AS bucket, machine_id, signal,
       avg(value) AS avg, min(value) AS min, max(value) AS max
FROM telemetry GROUP BY 1, 2, 3 WITH NO DATA;
SELECT add_continuous_aggregate_policy('telemetry_1m', start_offset => INTERVAL '3 days',
                                       end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute');

-- State changes reported by the machine; an operator may classify an unexplained stop later.
CREATE TABLE state_event (
    machine_id     text NOT NULL REFERENCES machine (id),
    time           timestamptz NOT NULL,
    state          text NOT NULL CHECK (state IN ('run', 'down', 'setup', 'planned', 'off')),
    reason         text,
    classified_at  timestamptz,
    PRIMARY KEY (machine_id, time)
);

CREATE TABLE part_event (
    machine_id  text NOT NULL REFERENCES machine (id),
    time        timestamptz NOT NULL,
    good        boolean NOT NULL,
    UNIQUE (machine_id, time)
);
SELECT create_hypertable('part_event', by_range('time', INTERVAL '7 days'));
SELECT add_retention_policy('part_event', INTERVAL '30 days');

CREATE TABLE alarm (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    machine_id  text NOT NULL REFERENCES machine (id),
    code        text NOT NULL,                   -- reason code (machine alarm) or signal key (limit rule)
    source      text NOT NULL CHECK (source IN ('machine', 'rule')),
    severity    text NOT NULL CHECK (severity IN ('warning', 'critical')),
    text        text NOT NULL,
    raised_at   timestamptz NOT NULL,
    cleared_at  timestamptz,
    acked_at    timestamptz,
    UNIQUE (machine_id, code, raised_at)
);
CREATE INDEX alarm_open ON alarm (machine_id, code) WHERE cleared_at IS NULL;
CREATE INDEX alarm_raised ON alarm (raised_at DESC);

-- Web Push subscriptions ("alarms on your phone"); deleted after 24 hours.
CREATE TABLE push_subscription (
    endpoint    text PRIMARY KEY,
    p256dh      text NOT NULL,
    auth        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_sent   timestamptz
);
