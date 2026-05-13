-- ============================================================================
-- MODULE: Intelligent Inventory & Customer Engagement
-- TARGET: African POS System (Offline-First, Low-Data)
-- FEATURES:
--   1. Smart Expiry & Flash Sales (Waste Reduction)
--   2. Visual Search Metadata (Unbranded Goods)
--   3. Predictive Restocking (Seasonality aware)
--   4. Customer Soft Credit Scoring (Risk Management)
-- ============================================================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- For fuzzy text search in product names
CREATE EXTENSION IF NOT EXISTS vector;  -- If using pgvector for image embeddings (optional)

-- ============================================================================
-- 1. SMART EXPIRY & FLASH SALES
-- ============================================================================

-- Table: Batch Expiry Tracking (Enhanced)
-- Links to existing inventory_batches if not already present
CREATE TABLE IF NOT EXISTS inventory_expiry_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES inventory_batches(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES stores(id),
    product_id UUID NOT NULL REFERENCES products(id),
    expiry_date DATE NOT NULL,
    days_until_expiry INT GENERATED ALWAYS AS (expiry_date - CURRENT_DATE) STORED,
    suggested_discount_percent DECIMAL(5,2) DEFAULT 0.00,
    status VARCHAR(20) DEFAULT 'monitoring' CHECK (status IN ('monitoring', 'alerted', 'discounted', 'sold', 'expired', 'discarded')),
    alert_triggered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for Expiry
CREATE INDEX idx_expiry_date_active ON inventory_expiry_alerts(expiry_date) WHERE status IN ('monitoring', 'alerted');
CREATE INDEX idx_store_expiry ON inventory_expiry_alerts(store_id, expiry_date);

-- Table: Flash Sale Campaigns (Auto-generated or Manual)
CREATE TABLE flash_sale_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id),
    name VARCHAR(100) NOT NULL, -- e.g., "Weekend Clearance", "Near-Expiry Deal"
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    discount_type VARCHAR(20) DEFAULT 'percent' CHECK (discount_type IN ('percent', 'fixed')),
    discount_value DECIMAL(10,2) NOT NULL,
    target_criteria JSONB NOT NULL, -- e.g., {"days_until_expiry": "< 7", "category": "dairy"}
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'cancelled')),
    total_items_sold INT DEFAULT 0,
    revenue_generated DECIMAL(15,2) DEFAULT 0.00,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- 2. VISUAL SEARCH METADATA (Offline-First Approach)
-- ============================================================================

-- Table: Product Visual Signatures
-- Stores lightweight feature vectors or references to image clusters
-- Allows finding "Red Bag of Rice" even if barcode is missing
CREATE TABLE product_visual_signatures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES stores(id),
    -- Using JSONB for flexibility until pgvector is confirmed in all envs
    -- In production, use vector(512) for cosine similarity
    color_histogram JSONB, -- Dominant colors [R,G,B]
    texture_features JSONB, -- Simple texture metrics
    reference_image_url TEXT,
    embedding_version VARCHAR(20) DEFAULT 'v1',
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast JSONB querying (if not using vector extension)
CREATE INDEX idx_visual_color ON product_visual_signatures USING GIN (color_histogram);

-- Table: User Submitted Photos (For training/local matching)
CREATE TABLE product_user_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES products(id), -- Nullable if unmatched yet
    store_id UUID NOT NULL REFERENCES stores(id),
    image_path_local TEXT NOT NULL, -- Path on device
    image_hash VARCHAR(64) NOT NULL, -- Perceptual hash for duplicate detection
    uploaded_by UUID REFERENCES users(id),
    matched_product_id UUID REFERENCES products(id), -- Result of matching
    confidence_score DECIMAL(5,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_photo_hash ON product_user_photos(image_hash);

-- ============================================================================
-- 3. PREDICTIVE RESTOCKING (Seasonality & Velocity)
-- ============================================================================

-- Table: Restock Rules & Patterns
CREATE TABLE restock_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id),
    product_id UUID REFERENCES products(id), -- Null for category-level rules
    category_id UUID REFERENCES categories(id),
    
    -- Baseline Metrics
    avg_daily_sales DECIMAL(10,2),
    sales_velocity_std_dev DECIMAL(10,2), -- Volatility
    
    -- Seasonality Factors (JSONB for flexible periods)
    -- e.g., {"ramadan": 1.5, "back_to_school": 2.0, "christmas": 1.8}
    seasonal_multipliers JSONB DEFAULT '{}',
    
    -- Lead Time
    avg_supplier_lead_time_days INT DEFAULT 7,
    safety_stock_days INT DEFAULT 3,
    
    -- Reorder Point Calculation
    reorder_point DECIMAL(10,2) GENERATED ALWAYS AS (
        (avg_daily_sales * (avg_supplier_lead_time_days + safety_stock_days)) 
        -- Multiplier application happens at query time based on current date
    ) STORED,
    
    suggested_order_qty DECIMAL(10,2),
    last_restock_date DATE,
    next_predicted_stockout_date DATE,
    
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table: Restock Recommendations (Generated Daily)
CREATE TABLE restock_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id),
    product_id UUID NOT NULL REFERENCES products(id),
    pattern_id UUID REFERENCES restock_patterns(id),
    
    current_stock_qty DECIMAL(10,2) NOT NULL,
    predicted_demand_7d DECIMAL(10,2) NOT NULL,
    predicted_demand_14d DECIMAL(10,2),
    
    recommended_order_qty DECIMAL(10,2) NOT NULL,
    estimated_cost DECIMAL(15,2),
    priority_score INT CHECK (priority_score BETWEEN 1 AND 10), -- 10 = Urgent
    
    reason_code VARCHAR(50), -- 'LOW_STOCK', 'SEASONAL_SPIKE', 'PROMOTION_UPCOMING'
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'ordered', 'ignored', 'partial')),
    
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_restock_priority ON restock_recommendations(store_id, priority_score DESC) WHERE status = 'pending';

-- ============================================================================
-- 4. CUSTOMER SOFT CREDIT SCORING
-- ============================================================================

-- Table: Customer Credit Behavior Log
CREATE TABLE customer_credit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    store_id UUID NOT NULL REFERENCES stores(id),
    sale_id UUID REFERENCES sales(id),
    
    event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('credit_granted', 'partial_payment', 'full_payment', 'default_warning', 'written_off')),
    amount DECIMAL(15,2) NOT NULL,
    due_date DATE,
    paid_date DATE,
    days_overdue INT GENERATED ALWAYS AS (
        CASE WHEN paid_date IS NULL AND due_date < CURRENT_DATE THEN CURRENT_DATE - due_date ELSE 0 END
    ) STORED,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_client_credit_events ON customer_credit_events(client_id, created_at DESC);

-- Table: Customer Credit Scores (Snapshot)
CREATE TABLE customer_credit_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    store_id UUID NOT NULL REFERENCES stores(id),
    
    -- Score Components (0-100)
    repayment_history_score INT DEFAULT 0, -- 40% weight
    frequency_score INT DEFAULT 0,         -- 20% weight
    tenure_score INT DEFAULT 0,            -- 20% weight
    utilization_score INT DEFAULT 0,       -- 20% weight (Credit used vs Limit)
    
    -- Final Weighted Score
    final_score INT GENERATED ALWAYS AS (
        (repayment_history_score * 0.4) + 
        (frequency_score * 0.2) + 
        (tenure_score * 0.2) + 
        (utilization_score * 0.2)
    ) STORED,
    
    -- Risk Tier
    risk_tier VARCHAR(20) GENERATED ALWAYS AS (
        CASE 
            WHEN final_score >= 80 THEN 'LOW_RISK'
            WHEN final_score >= 60 THEN 'MEDIUM_RISK'
            WHEN final_score >= 40 THEN 'HIGH_RISK'
            ELSE 'VERY_HIGH_RISK'
        END
    ) STORED,
    
    -- Recommended Action
    suggested_credit_limit DECIMAL(15,2),
    max_credit_days INT, -- e.g., 7, 14, 30
    
    last_calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(client_id, store_id)
);

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Function: Calculate Suggested Discount based on Days to Expiry
CREATE OR REPLACE FUNCTION calc_expiry_discount(days_left INT, base_price DECIMAL)
RETURNS DECIMAL AS $$
DECLARE
    discount DECIMAL := 0;
BEGIN
    IF days_left <= 0 THEN
        RETURN 100.00; -- Expired
    ELSIF days_left <= 3 THEN
        discount := 50.00;
    ELSIF days_left <= 7 THEN
        discount := 30.00;
    ELSIF days_left <= 14 THEN
        discount := 15.00;
    ELSE
        discount := 0.00;
    END IF;
    RETURN discount;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function: Update Expiry Alerts Status (Daily Job)
CREATE OR REPLACE FUNCTION process_expiry_alerts()
RETURNS VOID AS $$
BEGIN
    -- Mark expired items
    UPDATE inventory_expiry_alerts
    SET status = 'expired', updated_at = NOW()
    WHERE days_until_expiry < 0 AND status NOT IN ('expired', 'discarded', 'sold');

    -- Trigger alerts for items entering critical zone (7 days)
    UPDATE inventory_expiry_alerts
    SET 
        status = 'alerted',
        suggested_discount_percent = calc_expiry_discount(days_until_expiry, 0), -- Price lookup needed in app layer
        alert_triggered_at = NOW(),
        updated_at = NOW()
    WHERE days_until_expiry BETWEEN 1 AND 7 
      AND status = 'monitoring';
      
    -- Reset sold items (handled by sale trigger usually, but safety net here)
    UPDATE inventory_expiry_alerts
    SET status = 'sold', updated_at = NOW()
    WHERE batch_id IN (SELECT batch_id FROM sale_items WHERE quantity > 0); -- Simplified logic
END;
$$ LANGUAGE plpgsql;

-- Function: Calculate Customer Credit Score
CREATE OR REPLACE FUNCTION calculate_customer_credit_score(p_client_id UUID, p_store_id UUID)
RETURNS VOID AS $$
DECLARE
    v_total_loans INT;
    v_on_time_payments INT;
    v_avg_days_late NUMERIC;
    v_tenure_days INT;
    v_last_purchase DATE;
    
    v_repayment_score INT := 50;
    v_frequency_score INT := 50;
    v_tenure_score INT := 50;
    v_utilization_score INT := 50;
    
    v_current_balance DECIMAL;
    v_credit_limit DECIMAL;
BEGIN
    -- 1. Repayment History (40%)
    SELECT COUNT(*), COUNT(*) FILTER (WHERE days_overdue = 0)
    INTO v_total_loans, v_on_time_payments
    FROM customer_credit_events
    WHERE client_id = p_client_id AND store_id = p_store_id AND event_type IN ('full_payment', 'partial_payment');

    IF v_total_loans > 0 THEN
        v_repayment_score := ROUND((v_on_time_payments::NUMERIC / v_total_loans) * 100);
    END IF;

    -- 2. Frequency (20%) - Purchases in last 90 days
    -- Logic simplified for brevity

    -- 3. Tenure (20%)
    SELECT MIN(created_at)::DATE, MAX(created_at)::DATE
    INTO v_tenure_days, v_last_purchase
    FROM customer_credit_events -- Or sales table
    WHERE client_id = p_client_id AND store_id = p_store_id;
    
    IF v_tenure_days IS NOT NULL THEN
        v_tenure_days := CURRENT_DATE - v_tenure_days;
        v_tenure_score := LEAST(100, v_tenure_days / 5); -- 1 point per 5 days, cap at 100
    END IF;

    -- 4. Utilization (20%)
    -- Fetch current balance vs limit from clients table
    SELECT outstanding_balance, credit_limit INTO v_current_balance, v_credit_limit
    FROM clients WHERE id = p_client_id;
    
    IF v_credit_limit > 0 THEN
        v_utilization_score := ROUND(((1 - (v_current_balance / v_credit_limit)) * 100));
        v_utilization_score := GREATEST(0, v_utilization_score);
    END IF;

    -- Upsert Score
    INSERT INTO customer_credit_scores (
        client_id, store_id, repayment_history_score, frequency_score, 
        tenure_score, utilization_score, suggested_credit_limit, last_calculated_at
    ) VALUES (
        p_client_id, p_store_id, v_repayment_score, v_frequency_score, 
        v_tenure_score, v_utilization_score, 
        CASE WHEN v_repayment_score > 80 THEN v_credit_limit * 1.2 ELSE v_credit_limit END,
        NOW()
    )
    ON CONFLICT (client_id, store_id) DO UPDATE SET
        repayment_history_score = EXCLUDED.repayment_history_score,
        frequency_score = EXCLUDED.frequency_score,
        tenure_score = EXCLUDED.tenure_score,
        utilization_score = EXCLUDED.utilization_score,
        suggested_credit_limit = EXCLUDED.suggested_credit_limit,
        last_calculated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VIEWS FOR DASHBOARDS
-- ============================================================================

-- View: Urgent Expiry Dashboard
CREATE OR REPLACE VIEW vw_urgent_expiry AS
SELECT 
    s.name as store_name,
    p.name as product_name,
    b.batch_number,
    ie.expiry_date,
    ie.days_until_expiry,
    ie.suggested_discount_percent,
    b.quantity_remaining,
    (b.quantity_remaining * p.cost_price) as potential_loss
FROM inventory_expiry_alerts ie
JOIN stores s ON ie.store_id = s.id
JOIN products p ON ie.product_id = p.id
JOIN inventory_batches b ON ie.batch_id = b.id
WHERE ie.status IN ('monitoring', 'alerted') AND ie.days_until_expiry <= 7
ORDER BY ie.days_until_expiry ASC;

-- View: Restock Priority List
CREATE OR REPLACE VIEW vw_restock_priority AS
SELECT 
    s.name as store_name,
    p.name as product_name,
    p.sku,
    rp.current_stock_qty,
    rp.predicted_demand_7d,
    rp.recommended_order_qty,
    rp.priority_score,
    rp.reason_code
FROM restock_recommendations rp
JOIN stores s ON rp.store_id = s.id
JOIN products p ON rp.product_id = p.id
WHERE rp.status = 'pending'
ORDER BY rp.priority_score DESC;

-- View: Customer Risk Profile
CREATE OR REPLACE VIEW vw_customer_risk_profile AS
SELECT 
    c.name as customer_name,
    c.phone,
    ccs.final_score,
    ccs.risk_tier,
    c.outstanding_balance,
    c.credit_limit,
    ccs.max_credit_days,
    CASE 
        WHEN ccs.risk_tier = 'LOW_RISK' THEN 'Approve up to limit'
        WHEN ccs.risk_tier = 'MEDIUM_RISK' THEN 'Approve with manager approval'
        ELSE 'Cash only or strict terms'
    END as recommended_action
FROM clients c
JOIN customer_credit_scores ccs ON c.id = ccs.client_id
WHERE ccs.store_id = CURRENT_SETTING('app.current_store_id')::UUID; -- Context dependent

-- Comments
COMMENT ON TABLE inventory_expiry_alerts IS 'Tracks batches approaching expiry to trigger flash sales';
COMMENT ON TABLE product_visual_signatures IS 'Stores image features for offline visual product search';
COMMENT ON TABLE restock_recommendations IS 'AI-driven suggestions for inventory replenishment';
COMMENT ON TABLE customer_credit_scores IS 'Proprietary credit risk score for informal traders';
