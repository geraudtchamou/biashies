-- ============================================================================
-- AFRICAN POS ANALYTICS MODULE
-- Comprehensive views, indexes, and analytical queries for business intelligence
-- Supports: Sales, Inventory, Profit, Customer, Employee, and Cash Flow Analysis
-- ============================================================================

-- ============================================================================
-- SECTION 1: PERFORMANCE INDEXES
-- Critical for fast analytics on large datasets
-- ============================================================================

-- Sales performance indexes
CREATE INDEX IF NOT EXISTS idx_sales_store_date ON sales(store_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_customer_date ON sales(client_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_status_date ON sales(status, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_payment_method ON sales(payment_method, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_sales_items_sale_id ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_product_id ON sale_items(product_id);

-- Inventory & Product indexes
CREATE INDEX IF NOT EXISTS idx_inventory_store_product ON inventory_levels(store_id, product_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id, is_active);
CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product_date ON stock_movements(product_id, movement_date);
CREATE INDEX IF NOT EXISTS idx_stock_movements_type ON stock_movements(movement_type);

-- Customer analytics indexes
CREATE INDEX IF NOT EXISTS idx_clients_tier ON clients(loyalty_tier_id);
CREATE INDEX IF NOT EXISTS idx_clients_created_date ON clients(created_at);
CREATE INDEX IF NOT EXISTS idx_client_transactions_client_date ON client_transactions(client_id, transaction_date);

-- Financial indexes
CREATE INDEX IF NOT EXISTS idx_expenses_category_date ON expenses(category_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_store_date ON expenses(store_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier_date ON purchases(supplier_id, purchase_date);

-- Composite indexes for common analytical queries
CREATE INDEX IF NOT EXISTS idx_sales_analytics_composite 
ON sales(store_id, sale_date, status, payment_method);
CREATE INDEX IF NOT EXISTS idx_profit_analytics_composite 
ON sale_items(product_id, sale_date, cost_price, selling_price);

-- ============================================================================
-- SECTION 2: CORE ANALYTICAL VIEWS
-- Pre-computed views for common business metrics
-- ============================================================================

-- ----------------------------------------------------------------------------
-- VIEW: Daily Sales Summary
-- Revenue, transactions, average ticket size per store per day
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_sales_summary AS
SELECT 
    s.store_id,
    st.name AS store_name,
    DATE(s.sale_date) AS sale_day,
    COUNT(DISTINCT s.id) AS total_transactions,
    COUNT(DISTINCT s.client_id) AS unique_customers,
    SUM(s.total_amount) AS gross_revenue,
    SUM(s.discount_amount) AS total_discounts,
    SUM(s.tax_amount) AS total_tax,
    SUM(s.total_amount - s.discount_amount) AS net_revenue,
    AVG(s.total_amount) AS average_ticket_size,
    SUM(CASE WHEN s.payment_method = 'cash' THEN s.total_amount ELSE 0 END) AS cash_revenue,
    SUM(CASE WHEN s.payment_method = 'mobile_money' THEN s.total_amount ELSE 0 END) AS mobile_money_revenue,
    SUM(CASE WHEN s.payment_method = 'card' THEN s.total_amount ELSE 0 END) AS card_revenue,
    SUM(CASE WHEN s.payment_method = 'credit' THEN s.total_amount ELSE 0 END) AS credit_revenue,
    COUNT(CASE WHEN s.status = 'completed' THEN 1 END) AS completed_sales,
    COUNT(CASE WHEN s.status = 'voided' THEN 1 END) AS voided_sales,
    COUNT(CASE WHEN s.status = 'refunded' THEN 1 END) AS refunded_sales
FROM sales s
JOIN stores st ON s.store_id = st.id
WHERE s.deleted_at IS NULL
GROUP BY s.store_id, st.name, DATE(s.sale_date);

-- ----------------------------------------------------------------------------
-- VIEW: Product Performance Analytics
-- Best sellers, profit margins, turnover rates per product
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_product_performance AS
SELECT 
    p.id AS product_id,
    p.name AS product_name,
    p.sku,
    p.category_id,
    c.name AS category_name,
    p.store_id,
    st.name AS store_name,
    COUNT(DISTINCT si.sale_id) AS number_of_sales,
    SUM(si.quantity) AS total_quantity_sold,
    SUM(si.quantity * si.selling_price) AS gross_revenue,
    SUM(si.quantity * si.cost_price) AS total_cogs,
    SUM(si.quantity * (si.selling_price - si.cost_price)) AS gross_profit,
    ROUND(
        CASE 
            WHEN SUM(si.quantity * si.selling_price) > 0 
            THEN (SUM(si.quantity * (si.selling_price - si.cost_price)) / SUM(si.quantity * si.selling_price)) * 100
            ELSE 0 
        END, 2
    ) AS profit_margin_percent,
    AVG(si.selling_price) AS avg_selling_price,
    AVG(si.cost_price) AS avg_cost_price,
    MIN(s.sale_date) AS first_sale_date,
    MAX(s.sale_date) AS last_sale_date,
    p.reorder_level,
    p.is_active
FROM products p
JOIN stores st ON p.store_id = st.id
LEFT JOIN categories c ON p.category_id = c.id
LEFT JOIN sale_items si ON p.id = si.product_id
LEFT JOIN sales s ON si.sale_id = s.id AND s.status = 'completed' AND s.deleted_at IS NULL
WHERE p.deleted_at IS NULL
GROUP BY p.id, p.name, p.sku, p.category_id, c.name, p.store_id, st.name, p.reorder_level, p.is_active;

-- ----------------------------------------------------------------------------
-- VIEW: Customer Lifetime Value & Segmentation
-- CLV, purchase frequency, recency, tier analysis
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_customer_analytics AS
SELECT 
    cl.id AS client_id,
    cl.name AS client_name,
    cl.phone,
    cl.email,
    cl.loyalty_tier_id,
    lt.name AS tier_name,
    cl.store_id,
    st.name AS store_name,
    COUNT(DISTINCT s.id) AS total_purchases,
    SUM(s.total_amount) AS lifetime_value,
    AVG(s.total_amount) AS average_purchase_value,
    MIN(s.sale_date) AS first_purchase_date,
    MAX(s.sale_date) AS last_purchase_date,
    CURRENT_DATE - MAX(s.sale_date) AS days_since_last_purchase,
    ROUND(
        CASE 
            WHEN MIN(s.sale_date) != MAX(s.sale_date)
            THEN COUNT(DISTINCT s.id)::NUMERIC / 
                 NULLIF(EXTRACT(DAY FROM (MAX(s.sale_date) - MIN(s.sale_date))), 0) * 30
            ELSE 0 
        END, 2
    ) AS purchases_per_month,
    SUM(lp.points_earned) - SUM(COALESCE(lp.points_redeemed, 0)) AS current_points,
    CASE 
        WHEN CURRENT_DATE - MAX(s.sale_date) <= 30 THEN 'Active'
        WHEN CURRENT_DATE - MAX(s.sale_date) <= 90 THEN 'At Risk'
        ELSE 'Churned'
    END AS customer_status
FROM clients cl
JOIN stores st ON cl.store_id = st.id
LEFT JOIN loyalty_tiers lt ON cl.loyalty_tier_id = lt.id
LEFT JOIN sales s ON cl.id = s.client_id AND s.status = 'completed' AND s.deleted_at IS NULL
LEFT JOIN loyalty_transactions lp ON cl.id = lp.client_id
WHERE cl.deleted_at IS NULL
GROUP BY cl.id, cl.name, cl.phone, cl.email, cl.loyalty_tier_id, lt.name, cl.store_id, st.name;

-- ----------------------------------------------------------------------------
-- VIEW: Inventory Health & Stock Movement
-- Stock levels, turnover, dead stock, low stock alerts
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_inventory_health AS
SELECT 
    p.id AS product_id,
    p.name AS product_name,
    p.sku,
    p.store_id,
    st.name AS store_name,
    COALESCE(SUM(sm.quantity_change), 0) + p.initial_stock AS current_stock,
    p.reorder_level,
    p.reorder_quantity,
    CASE 
        WHEN COALESCE(SUM(sm.quantity_change), 0) + p.initial_stock <= 0 THEN 'Out of Stock'
        WHEN COALESCE(SUM(sm.quantity_change), 0) + p.initial_stock <= p.reorder_level THEN 'Low Stock'
        WHEN COALESCE(SUM(sm.quantity_change), 0) + p.initial_stock > p.reorder_level * 2 THEN 'Overstocked'
        ELSE 'Healthy'
    END AS stock_status,
    COUNT(DISTINCT CASE WHEN sm.movement_type = 'sale' THEN sm.id END) AS sales_count,
    COUNT(DISTINCT CASE WHEN sm.movement_type = 'purchase' THEN sm.id END) AS purchase_count,
    COUNT(DISTINCT CASE WHEN sm.movement_type = 'adjustment' THEN sm.id END) AS adjustment_count,
    SUM(CASE WHEN sm.movement_type = 'sale' THEN ABS(sm.quantity_change) ELSE 0 END) AS total_sold,
    SUM(CASE WHEN sm.movement_type = 'purchase' THEN sm.quantity_change ELSE 0 END) AS total_purchased,
    p.expiry_date,
    CASE 
        WHEN p.expiry_date IS NOT NULL AND p.expiry_date < CURRENT_DATE THEN 'Expired'
        WHEN p.expiry_date IS NOT NULL AND p.expiry_date < CURRENT_DATE + INTERVAL '30 days' THEN 'Expiring Soon'
        ELSE 'Valid'
    END AS expiry_status
FROM products p
JOIN stores st ON p.store_id = st.id
LEFT JOIN stock_movements sm ON p.id = sm.product_id
WHERE p.deleted_at IS NULL
GROUP BY p.id, p.name, p.sku, p.store_id, st.name, p.initial_stock, p.reorder_level, p.reorder_quantity, p.expiry_date;

-- ----------------------------------------------------------------------------
-- VIEW: Profit & Loss Summary (Daily/Monthly)
-- Revenue, COGS, Expenses, Net Profit with margins
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_profit_loss_summary AS
WITH daily_revenue AS (
    SELECT 
        store_id,
        DATE(sale_date) AS period_date,
        SUM(total_amount - discount_amount) AS net_revenue,
        SUM(tax_amount) AS total_tax
    FROM sales
    WHERE status = 'completed' AND deleted_at IS NULL
    GROUP BY store_id, DATE(sale_date)
),
daily_cogs AS (
    SELECT 
        p.store_id,
        DATE(s.sale_date) AS period_date,
        SUM(si.quantity * si.cost_price) AS total_cogs
    FROM sale_items si
    JOIN sales s ON si.sale_id = s.id
    JOIN products p ON si.product_id = p.id
    WHERE s.status = 'completed' AND s.deleted_at IS NULL AND p.deleted_at IS NULL
    GROUP BY p.store_id, DATE(s.sale_date)
),
daily_expenses AS (
    SELECT 
        store_id,
        DATE(expense_date) AS period_date,
        SUM(amount) AS total_expenses
    FROM expenses
    WHERE deleted_at IS NULL
    GROUP BY store_id, DATE(expense_date)
)
SELECT 
    dr.store_id,
    st.name AS store_name,
    dr.period_date,
    COALESCE(dr.net_revenue, 0) AS revenue,
    COALESCE(dc.total_cogs, 0) AS cost_of_goods_sold,
    COALESCE(dr.net_revenue, 0) - COALESCE(dc.total_cogs, 0) AS gross_profit,
    ROUND(
        CASE 
            WHEN COALESCE(dr.net_revenue, 0) > 0 
            THEN ((COALESCE(dr.net_revenue, 0) - COALESCE(dc.total_cogs, 0)) / dr.net_revenue) * 100
            ELSE 0 
        END, 2
    ) AS gross_margin_percent,
    COALESCE(de.total_expenses, 0) AS operating_expenses,
    COALESCE(dr.net_revenue, 0) - COALESCE(dc.total_cogs, 0) - COALESCE(de.total_expenses, 0) AS net_profit,
    ROUND(
        CASE 
            WHEN COALESCE(dr.net_revenue, 0) > 0 
            THEN ((COALESCE(dr.net_revenue, 0) - COALESCE(dc.total_cogs, 0) - COALESCE(de.total_expenses, 0)) / dr.net_revenue) * 100
            ELSE 0 
        END, 2
    ) AS net_margin_percent
FROM daily_revenue dr
JOIN stores st ON dr.store_id = st.id
LEFT JOIN daily_cogs dc ON dr.store_id = dc.store_id AND dr.period_date = dc.period_date
LEFT JOIN daily_expenses de ON dr.store_id = de.store_id AND dr.period_date = de.period_date;

-- ----------------------------------------------------------------------------
-- VIEW: Cash Flow Analysis
-- Cash in, cash out, net flow by day
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cash_flow_analysis AS
SELECT 
    store_id,
    DATE(transaction_date) AS flow_date,
    transaction_type,
    SUM(amount_in) AS total_in,
    SUM(amount_out) AS total_out,
    SUM(amount_in) - SUM(amount_out) AS net_flow,
    payment_method,
    reference_id,
    description
FROM (
    -- Sales (Cash In)
    SELECT 
        store_id,
        sale_date AS transaction_date,
        'sale' AS transaction_type,
        total_amount AS amount_in,
        0 AS amount_out,
        payment_method,
        id::TEXT AS reference_id,
        'Sale Transaction' AS description
    FROM sales
    WHERE status = 'completed' AND deleted_at IS NULL AND payment_method IN ('cash', 'mobile_money')
    
    UNION ALL
    
    -- Expenses (Cash Out)
    SELECT 
        store_id,
        expense_date AS transaction_date,
        'expense' AS transaction_type,
        0 AS amount_in,
        amount AS amount_out,
        payment_method,
        id::TEXT AS reference_id,
        category_id::TEXT || ' - ' || description AS description
    FROM expenses
    WHERE deleted_at IS NULL
    
    UNION ALL
    
    -- Purchases (Cash Out)
    SELECT 
        store_id,
        purchase_date AS transaction_date,
        'purchase' AS transaction_type,
        0 AS amount_in,
        total_amount AS amount_out,
        payment_method,
        id::TEXT AS reference_id,
        'Purchase from supplier' AS description
    FROM purchases
    WHERE status = 'completed' AND deleted_at IS NULL
) AS cash_transactions
GROUP BY store_id, DATE(transaction_date), transaction_type, payment_method, reference_id, description;

-- ============================================================================
-- SECTION 3: ADVANCED ANALYTICAL QUERIES
-- Complex queries for deep business insights
-- ============================================================================

-- ----------------------------------------------------------------------------
-- QUERY: Sales Trend Analysis (Day-over-Day, Week-over-Week, Month-over-Month)
-- ----------------------------------------------------------------------------
-- Usage: Replace :store_id and :date_range as needed
/*
SELECT 
    period,
    total_revenue,
    LAG(total_revenue, 1) OVER (ORDER BY period) AS previous_period_revenue,
    total_revenue - LAG(total_revenue, 1) OVER (ORDER BY period) AS revenue_change,
    ROUND(
        ((total_revenue - LAG(total_revenue, 1) OVER (ORDER BY period)) / 
        NULLIF(LAG(total_revenue, 1) OVER (ORDER BY period), 0)) * 100, 2
    ) AS growth_percent
FROM (
    SELECT 
        DATE_TRUNC('day', sale_date) AS period,
        SUM(total_amount - discount_amount) AS total_revenue
    FROM sales
    WHERE store_id = :store_id 
      AND sale_date >= :start_date 
      AND sale_date <= :end_date
      AND status = 'completed'
      AND deleted_at IS NULL
    GROUP BY DATE_TRUNC('day', sale_date)
    ORDER BY period
) AS daily_revenue;
*/

-- ----------------------------------------------------------------------------
-- QUERY: ABC Analysis (Product Classification by Revenue Contribution)
-- Classifies products into A (top 70%), B (next 20%), C (bottom 10%)
-- ----------------------------------------------------------------------------
/*
WITH product_revenue AS (
    SELECT 
        p.id,
        p.name,
        p.sku,
        SUM(si.quantity * si.selling_price) AS total_revenue,
        RANK() OVER (ORDER BY SUM(si.quantity * si.selling_price) DESC) AS revenue_rank
    FROM products p
    JOIN sale_items si ON p.id = si.product_id
    JOIN sales s ON si.sale_id = s.id
    WHERE p.store_id = :store_id
      AND s.status = 'completed'
      AND s.deleted_at IS NULL
      AND p.deleted_at IS NULL
    GROUP BY p.id, p.name, p.sku
),
total_revenue AS (
    SELECT SUM(total_revenue) AS grand_total FROM product_revenue
),
cumulative AS (
    SELECT 
        pr.*,
        SUM(pr.total_revenue) OVER (ORDER BY pr.revenue_rank) AS cumulative_revenue,
        tr.grand_total
    FROM product_revenue pr, total_revenue tr
)
SELECT 
    id,
    name,
    sku,
    total_revenue,
    ROUND((cumulative_revenue / grand_total) * 100, 2) AS cumulative_percent,
    CASE 
        WHEN (cumulative_revenue / grand_total) <= 0.70 THEN 'A'
        WHEN (cumulative_revenue / grand_total) <= 0.90 THEN 'B'
        ELSE 'C'
    END AS abc_class
FROM cumulative
ORDER BY revenue_rank;
*/

-- ----------------------------------------------------------------------------
-- QUERY: Customer Cohort Analysis (Retention by Month)
-- ----------------------------------------------------------------------------
/*
WITH customer_cohorts AS (
    SELECT 
        client_id,
        DATE_TRUNC('month', MIN(sale_date)) AS cohort_month
    FROM sales
    WHERE status = 'completed' AND deleted_at IS NULL
    GROUP BY client_id
),
customer_activity AS (
    SELECT 
        s.client_id,
        cc.cohort_month,
        DATE_TRUNC('month', s.sale_date) AS activity_month,
        EXTRACT(MONTH FROM AGE(DATE_TRUNC('month', s.sale_date), cc.cohort_month)) AS months_since_first_purchase
    FROM sales s
    JOIN customer_cohorts cc ON s.client_id = cc.client_id
    WHERE s.status = 'completed' AND s.deleted_at IS NULL
)
SELECT 
    cohort_month,
    months_since_first_purchase,
    COUNT(DISTINCT client_id) AS active_customers,
    ROUND(
        COUNT(DISTINCT client_id)::NUMERIC / 
        NULLIF(FIRST_VALUE(COUNT(DISTINCT client_id)) OVER (PARTITION BY cohort_month ORDER BY months_since_first_purchase), 0) * 100, 2
    ) AS retention_rate
FROM customer_activity
GROUP BY cohort_month, months_since_first_purchase
ORDER BY cohort_month, months_since_first_purchase;
*/

-- ----------------------------------------------------------------------------
-- QUERY: Moving Average Sales (7-day, 30-day)
-- ----------------------------------------------------------------------------
/*
SELECT 
    sale_day,
    daily_revenue,
    ROUND(AVG(daily_revenue) OVER (ORDER BY sale_day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS moving_avg_7d,
    ROUND(AVG(daily_revenue) OVER (ORDER BY sale_day ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 2) AS moving_avg_30d
FROM (
    SELECT 
        DATE(sale_date) AS sale_day,
        SUM(total_amount - discount_amount) AS daily_revenue
    FROM sales
    WHERE store_id = :store_id
      AND status = 'completed'
      AND deleted_at IS NULL
    GROUP BY DATE(sale_date)
) AS daily_sales
ORDER BY sale_day;
*/

-- ----------------------------------------------------------------------------
-- QUERY: Hourly Sales Pattern (Peak Hours Analysis)
-- ----------------------------------------------------------------------------
/*
SELECT 
    EXTRACT(HOUR FROM sale_time) AS hour_of_day,
    COUNT(*) AS transaction_count,
    SUM(total_amount) AS total_revenue,
    AVG(total_amount) AS average_ticket,
    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 2) AS percent_of_daily_sales
FROM sales
WHERE store_id = :store_id
  AND status = 'completed'
  AND deleted_at IS NULL
  AND sale_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY EXTRACT(HOUR FROM sale_time)
ORDER BY hour_of_day;
*/

-- ----------------------------------------------------------------------------
-- QUERY: Supplier Performance Analysis
-- ----------------------------------------------------------------------------
/*
SELECT 
    s.id AS supplier_id,
    s.name AS supplier_name,
    COUNT(DISTINCT p.id) AS products_supplied,
    COUNT(DISTINCT pu.id) AS total_purchases,
    SUM(pu.total_amount) AS total_purchase_value,
    AVG(pu.total_amount) AS average_purchase_value,
    SUM(CASE WHEN pu.status = 'completed' THEN 1 ELSE 0 END) AS completed_orders,
    SUM(CASE WHEN pu.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
    ROUND(
        SUM(CASE WHEN pu.status = 'completed' THEN 1 ELSE 0 END)::NUMERIC / 
        NULLIF(COUNT(DISTINCT pu.id), 0) * 100, 2
    ) AS fulfillment_rate,
    AVG(EXTRACT(DAY FROM (pu.expected_delivery_date - pu.purchase_date))) AS avg_lead_time_days
FROM suppliers s
LEFT JOIN products p ON s.id = p.supplier_id AND p.deleted_at IS NULL
LEFT JOIN purchases pu ON s.id = pu.supplier_id AND pu.deleted_at IS NULL
WHERE s.deleted_at IS NULL
GROUP BY s.id, s.name
ORDER BY total_purchase_value DESC;
*/

-- ----------------------------------------------------------------------------
-- QUERY: Employee/Sales Rep Performance
-- ----------------------------------------------------------------------------
/*
SELECT 
    u.id AS user_id,
    u.full_name,
    u.role,
    COUNT(DISTINCT s.id) AS total_sales,
    SUM(s.total_amount) AS total_revenue,
    AVG(s.total_amount) AS average_sale_value,
    SUM(si.quantity * (si.selling_price - si.cost_price)) AS total_profit_generated,
    COUNT(DISTINCT s.client_id) AS unique_customers_served,
    ROUND(
        COUNT(DISTINCT s.client_id)::NUMERIC / NULLIF(COUNT(DISTINCT s.id), 0) * 100, 2
    ) AS customer_return_rate
FROM users u
LEFT JOIN sales s ON u.id = s.created_by AND s.status = 'completed' AND s.deleted_at IS NULL
LEFT JOIN sale_items si ON s.id = si.sale_id
WHERE u.deleted_at IS NULL
  AND u.role IN ('cashier', 'sales_rep', 'admin')
GROUP BY u.id, u.full_name, u.role
ORDER BY total_revenue DESC;
*/

-- ============================================================================
-- SECTION 4: MATERIALIZED VIEWS FOR HEAVY QUERIES
-- Refresh periodically for better performance
-- ============================================================================

-- Materialized View: Monthly Store Performance Snapshot
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_store_performance AS
SELECT 
    store_id,
    DATE_TRUNC('month', sale_date) AS month,
    COUNT(DISTINCT id) AS total_transactions,
    COUNT(DISTINCT client_id) AS unique_customers,
    SUM(total_amount - discount_amount) AS net_revenue,
    SUM(tax_amount) AS total_tax_collected,
    AVG(total_amount) AS average_ticket_size,
    COUNT(CASE WHEN payment_method = 'cash' THEN 1 END) AS cash_transactions,
    COUNT(CASE WHEN payment_method = 'mobile_money' THEN 1 END) AS mobile_money_transactions,
    COUNT(CASE WHEN status = 'refunded' THEN 1 END) AS refund_count,
    SUM(CASE WHEN status = 'refunded' THEN total_amount ELSE 0 END) AS refund_amount
FROM sales
WHERE status IN ('completed', 'refunded') AND deleted_at IS NULL
GROUP BY store_id, DATE_TRUNC('month', sale_date);

-- Indexes on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_monthly_store_perf 
ON mv_monthly_store_performance(store_id, month);

-- Materialized View: Product Category Performance
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_category_performance AS
SELECT 
    p.category_id,
    c.name AS category_name,
    p.store_id,
    DATE_TRUNC('month', s.sale_date) AS month,
    COUNT(DISTINCT p.id) AS active_products,
    SUM(si.quantity) AS total_units_sold,
    SUM(si.quantity * si.selling_price) AS total_revenue,
    SUM(si.quantity * (si.selling_price - si.cost_price)) AS total_profit,
    ROUND(
        (SUM(si.quantity * (si.selling_price - si.cost_price)) / 
        NULLIF(SUM(si.quantity * si.selling_price), 0)) * 100, 2
    ) AS profit_margin_percent
FROM products p
JOIN categories c ON p.category_id = c.id
JOIN sale_items si ON p.id = si.product_id
JOIN sales s ON si.sale_id = s.id
WHERE p.deleted_at IS NULL 
  AND c.deleted_at IS NULL 
  AND s.status = 'completed' 
  AND s.deleted_at IS NULL
GROUP BY p.category_id, c.name, p.store_id, DATE_TRUNC('month', s.sale_date));

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_category_perf 
ON mv_category_performance(category_id, store_id, month);

-- ============================================================================
-- SECTION 5: ANALYTICAL FUNCTIONS
-- Reusable functions for complex calculations
-- ============================================================================

-- Function: Calculate Customer Lifetime Value Prediction
CREATE OR REPLACE FUNCTION fn_predict_clv(
    p_client_id BIGINT,
    p_avg_purchase_value NUMERIC,
    p_purchase_frequency NUMERIC,
    p_customer_lifespan_months NUMERIC DEFAULT 24
) RETURNS NUMERIC AS $$
DECLARE
    predicted_clv NUMERIC;
BEGIN
    -- CLV = Average Purchase Value × Purchase Frequency × Customer Lifespan
    predicted_clv := p_avg_purchase_value * p_purchase_frequency * p_customer_lifespan_months;
    RETURN ROUND(predicted_clv, 2);
END;
$$ LANGUAGE plpgsql;

-- Function: Calculate Days Sales of Inventory (DSI)
CREATE OR REPLACE FUNCTION fn_calculate_dsi(
    p_store_id BIGINT,
    p_product_id BIGINT,
    p_period_days INTEGER DEFAULT 30
) RETURNS NUMERIC AS $$
DECLARE
    avg_inventory NUMERIC;
    cogs NUMERIC;
    dsi NUMERIC;
BEGIN
    -- Get average inventory for the period
    SELECT COALESCE(AVG(quantity_on_hand), 0)
    INTO avg_inventory
    FROM inventory_snapshots
    WHERE store_id = p_store_id
      AND product_id = p_product_id
      AND snapshot_date >= CURRENT_DATE - INTERVAL '1 day' * p_period_days;
    
    -- Get COGS for the period
    SELECT COALESCE(SUM(si.quantity * si.cost_price), 0)
    INTO cogs
    FROM sale_items si
    JOIN sales s ON si.sale_id = s.id
    WHERE s.store_id = p_store_id
      AND si.product_id = p_product_id
      AND s.status = 'completed'
      AND s.deleted_at IS NULL
      AND s.sale_date >= CURRENT_DATE - INTERVAL '1 day' * p_period_days;
    
    -- DSI = (Average Inventory / COGS) × Days in Period
    IF cogs > 0 THEN
        dsi := (avg_inventory / cogs) * p_period_days;
    ELSE
        dsi := NULL;
    END IF;
    
    RETURN ROUND(dsi, 2);
END;
$$ LANGUAGE plpgsql;

-- Function: Get Top N Products by Metric
CREATE OR REPLACE FUNCTION fn_get_top_products(
    p_store_id BIGINT,
    p_metric TEXT DEFAULT 'revenue', -- 'revenue', 'profit', 'quantity'
    p_limit INTEGER DEFAULT 10,
    p_start_date DATE DEFAULT CURRENT_DATE - INTERVAL '30 days',
    p_end_date DATE DEFAULT CURRENT_DATE
) RETURNS TABLE (
    product_id BIGINT,
    product_name TEXT,
    metric_value NUMERIC,
    rank_position INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH ranked_products AS (
        SELECT 
            p.id AS product_id,
            p.name AS product_name,
            CASE 
                WHEN p_metric = 'revenue' THEN SUM(si.quantity * si.selling_price)
                WHEN p_metric = 'profit' THEN SUM(si.quantity * (si.selling_price - si.cost_price))
                WHEN p_metric = 'quantity' THEN SUM(si.quantity)::NUMERIC
                ELSE 0
            END AS metric_value,
            RANK() OVER (ORDER BY 
                CASE 
                    WHEN p_metric = 'revenue' THEN SUM(si.quantity * si.selling_price)
                    WHEN p_metric = 'profit' THEN SUM(si.quantity * (si.selling_price - si.cost_price))
                    WHEN p_metric = 'quantity' THEN SUM(si.quantity)::NUMERIC
                    ELSE 0
                END DESC
            ) AS rank_position
        FROM products p
        JOIN sale_items si ON p.id = si.product_id
        JOIN sales s ON si.sale_id = s.id
        WHERE p.store_id = p_store_id
          AND s.sale_date BETWEEN p_start_date AND p_end_date
          AND s.status = 'completed'
          AND s.deleted_at IS NULL
          AND p.deleted_at IS NULL
        GROUP BY p.id, p.name
    )
    SELECT rp.product_id, rp.product_name, rp.metric_value, rp.rank_position::INTEGER
    FROM ranked_products rp
    WHERE rp.rank_position <= p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SECTION 6: AUTOMATED REFRESH JOBS
-- Schedule periodic refresh of materialized views
-- ============================================================================

-- Note: In production, use pg_cron or external scheduler (Celery, etc.)
-- Example pg_cron job (requires pg_cron extension):
/*
-- Refresh monthly store performance daily at 2 AM
SELECT cron.schedule(
    'refresh-monthly-store-perf',
    '0 2 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_store_performance'
);

-- Refresh category performance daily at 2:15 AM
SELECT cron.schedule(
    'refresh-category-perf',
    '15 2 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_category_performance'
);
*/

-- ============================================================================
-- SECTION 7: USAGE EXAMPLES & REPORT QUERIES
-- Ready-to-use analytical reports
-- ============================================================================

-- Report: Executive Dashboard Summary (Today)
/*
SELECT 
    (SELECT COUNT(*) FROM sales WHERE DATE(sale_date) = CURRENT_DATE AND status = 'completed' AND deleted_at IS NULL) AS today_transactions,
    (SELECT COALESCE(SUM(total_amount - discount_amount), 0) FROM sales WHERE DATE(sale_date) = CURRENT_DATE AND status = 'completed' AND deleted_at IS NULL) AS today_revenue,
    (SELECT COALESCE(SUM(quantity * (selling_price - cost_price)), 0) FROM sale_items si JOIN sales s ON si.sale_id = s.id WHERE DATE(s.sale_date) = CURRENT_DATE AND s.status = 'completed' AND s.deleted_at IS NULL) AS today_gross_profit,
    (SELECT COUNT(*) FROM clients WHERE DATE(created_at) = CURRENT_DATE AND deleted_at IS NULL) AS new_customers_today,
    (SELECT COUNT(*) FROM products p JOIN inventory_levels il ON p.id = il.product_id WHERE il.quantity_on_hand <= p.reorder_level AND p.deleted_at IS NULL) AS low_stock_products;
*/

-- Report: Weekly Performance Comparison (This Week vs Last Week)
/*
WITH this_week AS (
    SELECT 
        COUNT(*) AS transactions,
        SUM(total_amount - discount_amount) AS revenue
    FROM sales
    WHERE sale_date >= DATE_TRUNC('week', CURRENT_DATE)
      AND sale_date < DATE_TRUNC('week', CURRENT_DATE) + INTERVAL '7 days'
      AND status = 'completed'
      AND deleted_at IS NULL
),
last_week AS (
    SELECT 
        COUNT(*) AS transactions,
        SUM(total_amount - discount_amount) AS revenue
    FROM sales
    WHERE sale_date >= DATE_TRUNC('week', CURRENT_DATE) - INTERVAL '7 days'
      AND sale_date < DATE_TRUNC('week', CURRENT_DATE)
      AND status = 'completed'
      AND deleted_at IS NULL
)
SELECT 
    tw.transactions AS this_week_transactions,
    lw.transactions AS last_week_transactions,
    tw.revenue AS this_week_revenue,
    lw.revenue AS last_week_revenue,
    ROUND(((tw.transactions - lw.transactions)::NUMERIC / NULLIF(lw.transactions, 0)) * 100, 2) AS transactions_growth_percent,
    ROUND(((tw.revenue - lw.revenue)::NUMERIC / NULLIF(lw.revenue, 0)) * 100, 2) AS revenue_growth_percent
FROM this_week tw, last_week lw;
*/

-- Report: Top 10 Customers by Revenue (Last 90 Days)
/*
SELECT 
    cl.id,
    cl.name,
    cl.phone,
    COUNT(s.id) AS purchases,
    SUM(s.total_amount) AS total_spent,
    AVG(s.total_amount) AS avg_purchase,
    MAX(s.sale_date) AS last_purchase
FROM clients cl
JOIN sales s ON cl.id = s.client_id
WHERE s.sale_date >= CURRENT_DATE - INTERVAL '90 days'
  AND s.status = 'completed'
  AND s.deleted_at IS NULL
  AND cl.deleted_at IS NULL
GROUP BY cl.id, cl.name, cl.phone
ORDER BY total_spent DESC
LIMIT 10;
*/

-- Report: Slow Moving Inventory (No sales in last 60 days)
/*
SELECT 
    p.id,
    p.name,
    p.sku,
    p.store_id,
    COALESCE(il.quantity_on_hand, 0) AS current_stock,
    p.initial_stock,
    p.reorder_level,
    MAX(s.sale_date) AS last_sale_date,
    CURRENT_DATE - MAX(s.sale_date) AS days_since_last_sale
FROM products p
LEFT JOIN inventory_levels il ON p.id = il.product_id
LEFT JOIN sale_items si ON p.id = si.product_id
LEFT JOIN sales s ON si.sale_id = s.id AND s.status = 'completed'
WHERE p.deleted_at IS NULL
GROUP BY p.id, p.name, p.sku, p.store_id, il.quantity_on_hand, p.initial_stock, p.reorder_level
HAVING MAX(s.sale_date) < CURRENT_DATE - INTERVAL '60 days' OR MAX(s.sale_date) IS NULL
ORDER BY days_since_last_sale DESC NULLS FIRST;
*/

-- ============================================================================
-- END OF ANALYTICS MODULE
-- ============================================================================
