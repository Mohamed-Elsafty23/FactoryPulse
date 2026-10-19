-- FactoryPulse operational source system.
CREATE SCHEMA IF NOT EXISTS ops;
SET search_path TO ops, public;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    -- Permit explicit timestamps for deterministic historical simulation.
    -- Ordinary updates never supply updated_at and therefore receive now().
    IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
        NEW.updated_at = now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS plants (
    plant_id VARCHAR(16) PRIMARY KEY,
    plant_name VARCHAR(64) NOT NULL,
    country CHAR(2) NOT NULL,
    timezone VARCHAR(48) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_plants_updated ON plants;
CREATE TRIGGER trg_plants_updated BEFORE UPDATE ON plants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS machines (
    machine_id VARCHAR(16) PRIMARY KEY,
    machine_name VARCHAR(64) NOT NULL,
    plant_id VARCHAR(16) NOT NULL REFERENCES plants(plant_id),
    line_id VARCHAR(16) NOT NULL,
    model VARCHAR(32) NOT NULL,
    machine_type CHAR(1) NOT NULL CHECK (machine_type IN ('L', 'M', 'H')),
    criticality VARCHAR(8) NOT NULL CHECK (criticality IN ('low', 'medium', 'high')),
    ideal_cycle_seconds NUMERIC(6,2) NOT NULL,
    installed_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_machines_updated ON machines;
CREATE TRIGGER trg_machines_updated BEFORE UPDATE ON machines
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_machines_updated_at ON machines(updated_at);

CREATE TABLE IF NOT EXISTS machine_change_log (
    change_id BIGSERIAL PRIMARY KEY,
    machine_id VARCHAR(16) NOT NULL REFERENCES machines(machine_id),
    changed_field VARCHAR(32) NOT NULL,
    old_value VARCHAR(64),
    new_value VARCHAR(64),
    change_reason VARCHAR(128),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_change_log_changed_at ON machine_change_log(changed_at);

CREATE TABLE IF NOT EXISTS work_orders (
    work_order_id VARCHAR(24) PRIMARY KEY,
    machine_id VARCHAR(16) NOT NULL REFERENCES machines(machine_id),
    wo_type VARCHAR(12) NOT NULL CHECK (wo_type IN ('preventive', 'corrective')),
    failure_type VARCHAR(8),
    priority VARCHAR(8) NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    opened_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    technician VARCHAR(64),
    labour_hours NUMERIC(6,2),
    parts_cost_eur NUMERIC(10,2),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_wo_times CHECK (closed_at IS NULL OR closed_at >= opened_at)
);
DROP TRIGGER IF EXISTS trg_wo_updated ON work_orders;
CREATE TRIGGER trg_wo_updated BEFORE UPDATE ON work_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_wo_updated_at ON work_orders(updated_at);
CREATE INDEX IF NOT EXISTS idx_wo_machine ON work_orders(machine_id);

CREATE TABLE IF NOT EXISTS production_orders (
    production_order_id VARCHAR(24) PRIMARY KEY,
    machine_id VARCHAR(16) NOT NULL REFERENCES machines(machine_id),
    product_code VARCHAR(24) NOT NULL,
    planned_qty INTEGER NOT NULL CHECK (planned_qty > 0),
    good_qty INTEGER NOT NULL DEFAULT 0 CHECK (good_qty >= 0),
    scrap_qty INTEGER NOT NULL DEFAULT 0 CHECK (scrap_qty >= 0),
    planned_start TIMESTAMPTZ NOT NULL,
    planned_end TIMESTAMPTZ NOT NULL,
    actual_start TIMESTAMPTZ,
    actual_end TIMESTAMPTZ,
    status VARCHAR(12) NOT NULL CHECK (status IN ('planned', 'running', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS trg_po_updated ON production_orders;
CREATE TRIGGER trg_po_updated BEFORE UPDATE ON production_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX IF NOT EXISTS idx_po_updated_at ON production_orders(updated_at);

CREATE TABLE IF NOT EXISTS ingestion_control (
    control_id SERIAL PRIMARY KEY,
    source_schema VARCHAR(32) NOT NULL,
    source_table VARCHAR(64) NOT NULL,
    watermark_column VARCHAR(64) NOT NULL,
    last_watermark TIMESTAMPTZ NOT NULL DEFAULT '1900-01-01',
    target_path VARCHAR(256) NOT NULL,
    load_type VARCHAR(16) NOT NULL DEFAULT 'incremental'
        CHECK (load_type IN ('incremental', 'full')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_schema, source_table)
);

INSERT INTO ingestion_control
    (source_schema, source_table, watermark_column, target_path) VALUES
    ('ops', 'machines', 'updated_at', 'landing/machines'),
    ('ops', 'work_orders', 'updated_at', 'landing/work_orders'),
    ('ops', 'production_orders', 'updated_at', 'landing/production_orders'),
    ('ops', 'plants', 'updated_at', 'landing/plants')
ON CONFLICT (source_schema, source_table) DO NOTHING;
