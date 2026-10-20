-- ============================================================================
-- E-commerce Analytics — Star Schema DDL
-- ----------------------------------------------------------------------------
-- This schema is written in portable ANSI SQL so it runs on both SQLite
-- (for the zero-install local demo) and PostgreSQL (production / Docker).
--
-- Structure:
--   dim_product   - products and their category
--   dim_customer  - customers, segment, geography
--   dim_date      - calendar attributes for time-series analysis
--   fact_sales    - one row per order line item (the transactional facts)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- DIMENSION: dim_product
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_product (
    product_id   INTEGER PRIMARY KEY,
    product      TEXT    NOT NULL,
    category     TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- DIMENSION: dim_customer
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT    NOT NULL,
    segment       TEXT,
    city          TEXT,
    region        TEXT
);

-- ---------------------------------------------------------------------------
-- DIMENSION: dim_date
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_date (
    date_id      INTEGER PRIMARY KEY,
    date         TEXT NOT NULL UNIQUE,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day          INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month_name   TEXT,
    weekday_name TEXT,
    is_weekend   INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- FACT: fact_sales
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_sales (
    sale_id     INTEGER PRIMARY KEY,
    order_id    TEXT    NOT NULL,
    date_id     INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    product_id  INTEGER NOT NULL,
    quantity    INTEGER NOT NULL,
    unit_price  REAL    NOT NULL,
    line_total  REAL    NOT NULL,
    status      TEXT    NOT NULL,
    revenue_flag INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (date_id)     REFERENCES dim_date (date_id),
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id),
    FOREIGN KEY (product_id)  REFERENCES dim_product (product_id)
);

-- ---------------------------------------------------------------------------
-- Indexes for analytic queries (drill by date / product / customer)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fact_date     ON fact_sales (date_id);
CREATE INDEX IF NOT EXISTS idx_fact_product  ON fact_sales (product_id);
CREATE INDEX IF NOT EXISTS idx_fact_customer ON fact_sales (customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_order    ON fact_sales (order_id);
