-- ============================================================================
-- E-commerce Analytics — business queries
-- ----------------------------------------------------------------------------
-- These queries answer the questions an executive would ask of sales data.
-- They run unchanged on SQLite and PostgreSQL (portable ANSI SQL).
--
-- Business questions covered:
--   Q1  Total revenue / orders / units / AOV (KPIs)
--   Q2  Revenue by month (with month-over-month growth)
--   Q3  Revenue by product (top sellers)
--   Q4  Revenue by category
--   Q5  Top products by revenue
--   Q6  Average order value
--   Q7  Best / worst performing categories
--   Q8  Revenue by region (geographic analysis)
--   Q9  Customer segments (order value by segment)
--   Q10 Detailed transaction table
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Q1. Executive KPIs (revenue counts only completed/shipped orders)
-- ---------------------------------------------------------------------------
SELECT
    COUNT(DISTINCT order_id)                              AS total_orders,
    COUNT(*)                                              AS line_items,
    SUM(CASE WHEN revenue_flag = 1 THEN quantity ELSE 0 END) AS units_sold,
    ROUND(SUM(CASE WHEN revenue_flag = 1 THEN line_total ELSE 0 END), 2) AS total_revenue,
    ROUND(
        SUM(CASE WHEN revenue_flag = 1 THEN line_total ELSE 0 END)
        / NULLIF(COUNT(DISTINCT CASE WHEN revenue_flag = 1 THEN order_id END), 0),
        2
    ) AS average_order_value
FROM fact_sales;

-- ---------------------------------------------------------------------------
-- Q2. Revenue by month + month-over-month growth
-- ---------------------------------------------------------------------------
SELECT
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(f.line_total), 2) AS revenue,
    COUNT(DISTINCT f.order_id)   AS orders,
    ROUND(
        100.0 * (SUM(f.line_total) - LAG(SUM(f.line_total)) OVER (ORDER BY d.year, d.month))
        / NULLIF(LAG(SUM(f.line_total)) OVER (ORDER BY d.year, d.month), 0),
        2
    ) AS mom_growth_pct
FROM fact_sales f
JOIN dim_date d ON f.date_id = d.date_id
WHERE f.revenue_flag = 1
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

-- ---------------------------------------------------------------------------
-- Q3. Revenue by product
-- ---------------------------------------------------------------------------
SELECT
    p.product,
    p.category,
    ROUND(SUM(f.line_total), 2) AS revenue,
    SUM(f.quantity)             AS units
FROM fact_sales f
JOIN dim_product p ON f.product_id = p.product_id
WHERE f.revenue_flag = 1
GROUP BY p.product, p.category, p.product_id
ORDER BY revenue DESC;

-- ---------------------------------------------------------------------------
-- Q4. Revenue by category
-- ---------------------------------------------------------------------------
SELECT
    p.category,
    ROUND(SUM(f.line_total), 2) AS revenue,
    COUNT(DISTINCT f.order_id)  AS orders,
    ROUND(SUM(f.quantity), 0)   AS units
FROM fact_sales f
JOIN dim_product p ON f.product_id = p.product_id
WHERE f.revenue_flag = 1
GROUP BY p.category
ORDER BY revenue DESC;

-- ---------------------------------------------------------------------------
-- Q5. Top 10 products by revenue
-- ---------------------------------------------------------------------------
SELECT
    p.product,
    ROUND(SUM(f.line_total), 2) AS revenue,
    SUM(f.quantity)             AS units
FROM fact_sales f
JOIN dim_product p ON f.product_id = p.product_id
WHERE f.revenue_flag = 1
GROUP BY p.product_id, p.product
ORDER BY revenue DESC
LIMIT 10;

-- ---------------------------------------------------------------------------
-- Q6. Average order value over time (by month)
-- ---------------------------------------------------------------------------
SELECT
    d.year,
    d.month,
    ROUND(
        SUM(f.line_total) / NULLIF(COUNT(DISTINCT f.order_id), 0), 2
    ) AS average_order_value
FROM fact_sales f
JOIN dim_date d ON f.date_id = d.date_id
WHERE f.revenue_flag = 1
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- ---------------------------------------------------------------------------
-- Q7. Best / worst performing categories by revenue
-- ---------------------------------------------------------------------------
SELECT
    p.category,
    ROUND(SUM(f.line_total), 2) AS revenue,
    ROUND(SUM(f.line_total) * 100.0 /
          NULLIF((SELECT SUM(line_total) FROM fact_sales WHERE revenue_flag = 1), 0), 2)
        AS revenue_share_pct
FROM fact_sales f
JOIN dim_product p ON f.product_id = p.product_id
WHERE f.revenue_flag = 1
GROUP BY p.category
ORDER BY revenue DESC;

-- ---------------------------------------------------------------------------
-- Q8. Revenue by region (geographic analysis)
-- ---------------------------------------------------------------------------
SELECT
    c.region,
    ROUND(SUM(f.line_total), 2) AS revenue,
    COUNT(DISTINCT f.order_id)  AS orders,
    COUNT(DISTINCT f.customer_id) AS customers
FROM fact_sales f
JOIN dim_customer c ON f.customer_id = c.customer_id
WHERE f.revenue_flag = 1
GROUP BY c.region
ORDER BY revenue DESC;

-- ---------------------------------------------------------------------------
-- Q9. Customer segments — order value & behaviour
-- ---------------------------------------------------------------------------
SELECT
    c.segment,
    COUNT(DISTINCT f.customer_id) AS customers,
    ROUND(SUM(f.line_total), 2)    AS revenue,
    ROUND(AVG(f.line_total), 2)    AS avg_line_total
FROM fact_sales f
JOIN dim_customer c ON f.customer_id = c.customer_id
WHERE f.revenue_flag = 1
GROUP BY c.segment
ORDER BY revenue DESC;

-- ---------------------------------------------------------------------------
-- Q10. Detailed transaction table (for the dashboard's drill-down grid)
-- ---------------------------------------------------------------------------
SELECT
    d.date                                       AS order_date,
    f.order_id,
    c.customer_name,
    c.segment,
    p.category,
    p.product,
    f.quantity,
    f.unit_price,
    f.line_total,
    f.status
FROM fact_sales f
JOIN dim_date     d ON f.date_id     = d.date_id
JOIN dim_customer c ON f.customer_id = c.customer_id
JOIN dim_product  p ON f.product_id  = p.product_id
WHERE f.revenue_flag = 1
ORDER BY d.date DESC, f.order_id
LIMIT 500;
