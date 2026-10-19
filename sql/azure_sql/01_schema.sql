-- FactoryPulse operational source system — Azure SQL Database (T-SQL)
IF SCHEMA_ID('ops') IS NULL EXEC('CREATE SCHEMA ops');
GO

CREATE TABLE ops.plants (
    plant_id VARCHAR(16) NOT NULL PRIMARY KEY,
    plant_name VARCHAR(64) NOT NULL,
    country CHAR(2) NOT NULL,
    timezone VARCHAR(48) NOT NULL,
    created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE ops.machines (
    machine_id VARCHAR(16) NOT NULL PRIMARY KEY,
    machine_name VARCHAR(64) NOT NULL,
    plant_id VARCHAR(16) NOT NULL REFERENCES ops.plants(plant_id),
    line_id VARCHAR(16) NOT NULL,
    model VARCHAR(32) NOT NULL,
    machine_type CHAR(1) NOT NULL CHECK (machine_type IN ('L','M','H')),
    criticality VARCHAR(8) NOT NULL CHECK (criticality IN ('low','medium','high')),
    ideal_cycle_seconds DECIMAL(6,2) NOT NULL,
    installed_date DATE NOT NULL,
    is_active BIT NOT NULL DEFAULT 1,
    created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX idx_machines_updated_at ON ops.machines(updated_at);
GO
CREATE TRIGGER ops.trg_machines_updated ON ops.machines
AFTER UPDATE AS
BEGIN
    SET NOCOUNT ON;
    UPDATE m SET updated_at = SYSUTCDATETIME()
    FROM ops.machines m INNER JOIN inserted i ON m.machine_id = i.machine_id;
END;
GO

CREATE TABLE ops.machine_change_log (
    change_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    machine_id VARCHAR(16) NOT NULL REFERENCES ops.machines(machine_id),
    changed_field VARCHAR(32) NOT NULL,
    old_value VARCHAR(64),
    new_value VARCHAR(64),
    change_reason VARCHAR(128),
    changed_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE ops.work_orders (
    work_order_id VARCHAR(24) NOT NULL PRIMARY KEY,
    machine_id VARCHAR(16) NOT NULL REFERENCES ops.machines(machine_id),
    wo_type VARCHAR(12) NOT NULL CHECK (wo_type IN ('preventive','corrective')),
    failure_type VARCHAR(8) NULL,
    priority VARCHAR(8) NOT NULL CHECK (priority IN ('low','medium','high','urgent')),
    opened_at DATETIME2(3) NOT NULL,
    started_at DATETIME2(3) NULL,
    closed_at DATETIME2(3) NULL,
    technician VARCHAR(64) NULL,
    labour_hours DECIMAL(6,2) NULL,
    parts_cost_eur DECIMAL(10,2) NULL,
    notes NVARCHAR(MAX) NULL,
    created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT chk_wo_times CHECK (closed_at IS NULL OR closed_at >= opened_at)
);
GO
CREATE INDEX idx_wo_updated_at ON ops.work_orders(updated_at);
GO
CREATE TRIGGER ops.trg_wo_updated ON ops.work_orders
AFTER UPDATE AS
BEGIN
    SET NOCOUNT ON;
    UPDATE w SET updated_at = SYSUTCDATETIME()
    FROM ops.work_orders w INNER JOIN inserted i ON w.work_order_id = i.work_order_id;
END;
GO

CREATE TABLE ops.production_orders (
    production_order_id VARCHAR(24) NOT NULL PRIMARY KEY,
    machine_id VARCHAR(16) NOT NULL REFERENCES ops.machines(machine_id),
    product_code VARCHAR(24) NOT NULL,
    planned_qty INT NOT NULL CHECK (planned_qty > 0),
    good_qty INT NOT NULL DEFAULT 0 CHECK (good_qty >= 0),
    scrap_qty INT NOT NULL DEFAULT 0 CHECK (scrap_qty >= 0),
    planned_start DATETIME2(3) NOT NULL,
    planned_end DATETIME2(3) NOT NULL,
    actual_start DATETIME2(3) NULL,
    actual_end DATETIME2(3) NULL,
    status VARCHAR(12) NOT NULL CHECK (status IN ('planned','running','completed','cancelled')),
    created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX idx_po_updated_at ON ops.production_orders(updated_at);
GO
CREATE TRIGGER ops.trg_po_updated ON ops.production_orders
AFTER UPDATE AS
BEGIN
    SET NOCOUNT ON;
    UPDATE p SET updated_at = SYSUTCDATETIME()
    FROM ops.production_orders p
    INNER JOIN inserted i ON p.production_order_id = i.production_order_id;
END;
GO

CREATE TABLE ops.ingestion_control (
    control_id INT IDENTITY(1,1) PRIMARY KEY,
    source_schema VARCHAR(32) NOT NULL,
    source_table VARCHAR(64) NOT NULL,
    watermark_column VARCHAR(64) NOT NULL,
    last_watermark DATETIME2(3) NOT NULL DEFAULT '1900-01-01',
    target_path VARCHAR(256) NOT NULL,
    load_type VARCHAR(16) NOT NULL DEFAULT 'incremental'
        CHECK (load_type IN ('incremental','full')),
    is_active BIT NOT NULL DEFAULT 1,
    updated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_control UNIQUE (source_schema, source_table)
);
GO

INSERT INTO ops.ingestion_control
    (source_schema, source_table, watermark_column, target_path) VALUES
    ('ops','machines','updated_at','landing/machines'),
    ('ops','work_orders','updated_at','landing/work_orders'),
    ('ops','production_orders','updated_at','landing/production_orders'),
    ('ops','plants','updated_at','landing/plants');
GO

CREATE PROCEDURE ops.usp_update_watermark
    @source_schema VARCHAR(32),
    @source_table VARCHAR(64),
    @new_watermark DATETIME2(3)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE ops.ingestion_control
    SET last_watermark = @new_watermark,
        updated_at = SYSUTCDATETIME()
    WHERE source_schema = @source_schema
      AND source_table = @source_table
      AND @new_watermark > last_watermark;
END;
GO
