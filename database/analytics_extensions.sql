-- ============================================================================
-- MODULE: Advanced Analytics & Feature Extensions
-- TARGET: PostgreSQL 14+
-- PURPOSE: Support USSD, Anomaly Detection, Health Scores, and Group Buying
-- ============================================================================

-- 1. ENUMS for new feature states
CREATE TYPE IF NOT EXISTS ussd_session_state AS ENUM ('active', 'awaiting_input', 'completed', 'expired');
CREATE TYPE IF NOT EXISTS anomaly_type AS ENUM ('velocity_spike', 'void_abuse', 'off_hours_login', 'negative_margin', 'duplicate_refund');
CREATE TYPE IF NOT EXISTS health_metric_category AS ENUM ('liquidity', 'inventory_turnover', 'debt_ratio', 'growth_consistency', 'compliance');

-- ============================================================================
-- 2. USSD FALLBACK SYSTEM
-- Allows feature phone users to perform sales/check stock via *123#
-- ============================================================================
CREATE TABLE IF NOT EXISTS ussd_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES stores(id), -- Link to store/tenant
    phone_number VARCHAR(20) NOT NULL,
    session_state ussd_session_state DEFAULT 'active',
    current_menu_step VARCHAR(50), -- e.g., 'MAIN_MENU', 'ENTER_PRODUCT_ID', 'CONFIRM_SALE'
    context_data JSONB, -- Stores temporary data: {'cart': [], 'total': 0, 'customer_id': ...}
    last_interaction_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '5 minutes'),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ussd_phone_active ON ussd_sessions(phone_number, session_state) 
    WHERE session_state IN ('active', 'awaiting_input');
CREATE INDEX IF NOT EXISTS idx_ussd_expiry ON ussd_sessions(expires_at) WHERE session_state = 'active';

-- ============================================================================
-- 3. ANOMALY DETECTION & SECURITY AUDIT
-- Tracks suspicious patterns for the AI Security module
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_anomalies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES stores(id),
    user_id UUID REFERENCES users(id), -- Suspect cashier/admin
    anomaly_type anomaly_type NOT NULL,
    severity_level INT DEFAULT 1, -- 1 (Low) to 5 (Critical)
    evidence_data JSONB NOT NULL, -- Context: {'sale_id': ..., 'avg_velocity': 10, 'current_velocity': 50}
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_tenant_severity ON security_anomalies(tenant_id, severity_level DESC) WHERE is_resolved = FALSE;
CREATE INDEX IF NOT EXISTS idx_anomaly_user ON security_anomalies(user_id, detected_at DESC);

-- ============================================================================
-- 4. BUSINESS HEALTH SCORE ENGINE
-- Materialized view base tables for calculating the 0-100 Score
-- ============================================================================
CREATE TABLE IF NOT EXISTS business_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES stores(id),
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Component Scores (0-100)
    liquidity_score INT DEFAULT 0,
    inventory_score INT DEFAULT 0,
    growth_score INT DEFAULT 0,
    compliance_score INT DEFAULT 0,
    
    -- Final Weighted Score
    overall_health_score INT DEFAULT 0,
    
    -- Key Metrics used for calculation
    metrics_json JSONB, -- {'cash_ratio': 1.2, 'stock_turn_days': 15, 'revenue_growth_pct': 5.0}
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_health_snapshot_unique ON business_health_snapshots(tenant_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_health_score_desc ON business_health_snapshots(tenant_id, overall_health_score DESC);

-- ============================================================================
-- 5. GROUP BUYING / COOPERATIVE PROCUREMENT
-- Allows multiple stores to pool orders for bulk discounts
-- ============================================================================
CREATE TABLE IF NOT EXISTS group_buying_pools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organizer_id UUID NOT NULL REFERENCES users(id),
    target_product_id UUID REFERENCES products(id),
    target_quantity DECIMAL(20,4) NOT NULL,
    current_quantity DECIMAL(20,4) DEFAULT 0,
    deadline TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'open', -- open, filled, distributed, cancelled
    negotiated_price DECIMAL(15,2), -- The bulk price achieved
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS group_buying_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pool_id UUID NOT NULL REFERENCES group_buying_pools(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES stores(id),
    contributed_quantity DECIMAL(20,4) NOT NULL,
    amount_paid DECIMAL(15,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- pending, received
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pool_status ON group_buying_pools(status, deadline);
CREATE INDEX IF NOT EXISTS idx_contribution_store ON group_buying_contributions(store_id, status);

-- ============================================================================
-- 6. WHATSAPP CATALOG CACHE
-- Pre-generated JSON/Text blobs for fast sharing without heavy DB hits
-- ============================================================================
CREATE TABLE IF NOT EXISTS whatsapp_catalog_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id),
    catalog_version VARCHAR(20) NOT NULL,
    format_type VARCHAR(10) DEFAULT 'text', -- text, json, image_map
    content_hash VARCHAR(64) NOT NULL, -- To detect changes
    payload TEXT NOT NULL, -- The actual message body or JSON
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '1 hour'),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_catalog_store ON whatsapp_catalog_cache(store_id, expires_at);

-- ============================================================================
-- 7. ANALYTICAL FUNCTIONS FOR HEALTH SCORING
-- ============================================================================

-- Function: Calculate Liquidity Score (0-100)
-- Logic: Based on Cash on Hand vs Current Liabilities (Payables)
CREATE OR REPLACE FUNCTION calc_liquidity_score(p_tenant_id UUID) RETURNS INT AS $$
DECLARE
    v_cash DECIMAL;
    v_payables DECIMAL;
    v_ratio FLOAT;
BEGIN
    -- Get current cash from cash management (simplified)
    SELECT COALESCE(SUM(amount), 0) INTO v_cash 
    FROM cash_transactions 
    WHERE store_id = p_tenant_id AND type = 'deposit'; -- Simplified logic
    
    -- Get outstanding payables
    SELECT COALESCE(SUM(balance), 0) INTO v_payables
    FROM purchases
    WHERE store_id = p_tenant_id AND balance > 0;

    IF v_payables = 0 THEN RETURN 100; END IF;
    
    v_ratio := v_cash / v_payables;
    
    -- Scoring logic: Ratio > 1.5 = 100, Ratio < 0.5 = 20
    IF v_ratio >= 1.5 THEN RETURN 100;
    ELSIF v_ratio <= 0.5 THEN RETURN 20;
    ELSE RETURN ROUND((v_ratio / 1.5) * 100)::INT;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function: Detect Velocity Anomaly (Z-Score approach)
-- Returns TRUE if current hour sales deviate > 3 sigma from average
CREATE OR REPLACE FUNCTION detect_velocity_anomaly(
    p_store_id UUID, 
    p_user_id UUID
) RETURNS BOOLEAN AS $$
DECLARE
    v_current_sales INT;
    v_avg_sales FLOAT;
    v_std_dev_sales FLOAT;
    v_z_score FLOAT;
BEGIN
    -- Sales in last 30 mins
    SELECT COUNT(*) INTO v_current_sales
    FROM sales
    WHERE store_id = p_store_id 
      AND cashier_id = p_user_id
      AND created_at > (NOW() - INTERVAL '30 minutes');

    -- Average sales per 30-min window over last 7 days at this time
    SELECT AVG(cnt), STDDEV(cnt) INTO v_avg_sales, v_std_dev_sales
    FROM (
        SELECT DATE_TRUNC('hour', created_at) as hr, COUNT(*) as cnt
        FROM sales
        WHERE store_id = p_store_id
          AND cashier_id = p_user_id
          AND created_at > (NOW() - INTERVAL '7 days')
        GROUP BY 1
    ) sub;

    IF v_std_dev_sales IS NULL OR v_std_dev_sales = 0 THEN RETURN FALSE; END IF;

    v_z_score := (v_current_sales - v_avg_sales) / v_std_dev_sales;

    RETURN (v_z_score > 3.0); -- More than 3 standard deviations
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- 8. MATERIALIZED VIEW: Daily Health Aggregation
-- Refresh this every night via cron
-- ============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_store_health AS
SELECT 
    s.id as store_id,
    s.name as store_name,
    COUNT(DISTINCT sal.id) as total_sales_yesterday,
    SUM(sal.total_amount) as revenue_yesterday,
    SUM(sal.profit_amount) as profit_yesterday, -- Assumes profit column exists
    COUNT(DISTINCT CASE WHEN sa.is_resolved = FALSE THEN sa.id END) as active_alerts,
    DATE(yesterday.date) as snapshot_date
FROM stores s
CROSS JOIN LATERAL (SELECT NOW() - INTERVAL '1 day' as date) as yesterday
LEFT JOIN sales sal ON sal.store_id = s.id 
    AND sal.created_at >= yesterday.date AND sal.created_at < (yesterday.date + INTERVAL '1 day')
LEFT JOIN security_anomalies sa ON sa.tenant_id = s.id 
    AND sa.detected_at >= yesterday.date AND sa.detected_at < (yesterday.date + INTERVAL '1 day')
GROUP BY s.id, s.name, yesterday.date;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_health_store_date ON mv_daily_store_health(store_id, snapshot_date);

COMMENT ON TABLE ussd_sessions IS 'Manages stateful USSD menu sessions for feature phones';
COMMENT ON TABLE security_anomalies IS 'Stores flagged suspicious activities for review';
COMMENT ON TABLE business_health_snapshots IS 'Daily snapshots of the 0-100 business health score';
COMMENT ON TABLE group_buying_pools IS 'Cooperative buying pools for bulk procurement';
