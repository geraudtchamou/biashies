-- African POS & Business Management System - Database Schema
-- PostgreSQL 14+ with multi-tenancy support
-- All tables include tenant_id for data isolation

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CORE ENTITIES
-- ============================================================================

-- Users (Traders, Staff, Cashiers)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(20) UNIQUE,
    password_hash VARCHAR(255),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'cashier', 'inventory_manager', 'sales_rep')),
    permissions JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    pin_hash VARCHAR(255), -- For cashier quick login
    biometric_enabled BOOLEAN DEFAULT FALSE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT users_tenant_check CHECK (tenant_id IS NOT NULL)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone);

-- Traders (Business Owners)
CREATE TABLE traders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    business_name VARCHAR(255) NOT NULL,
    business_registration_number VARCHAR(100),
    tax_id VARCHAR(100),
    logo_url VARCHAR(500),
    bio TEXT,
    description TEXT,
    operating_hours JSONB, -- {"monday": {"open": "08:00", "close": "18:00"}, ...}
    documents JSONB, -- Array of document URLs
    default_currency VARCHAR(3) NOT NULL DEFAULT 'XAF',
    supported_currencies VARCHAR(3)[],
    primary_language VARCHAR(5) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'Africa/Douala',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_traders_user ON traders(user_id);

-- Stores (Multiple stores per trader)
CREATE TABLE stores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    trader_id UUID NOT NULL REFERENCES traders(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50), -- Short code for quick identification
    logo_url VARCHAR(500),
    address TEXT,
    city VARCHAR(100),
    region VARCHAR(100),
    country VARCHAR(2) NOT NULL,
    postal_code VARCHAR(20),
    phone VARCHAR(20),
    email VARCHAR(255),
    currency VARCHAR(3) NOT NULL DEFAULT 'XAF',
    tax_rules JSONB, -- {"vat_rate": 19.25, "local_taxes": [...]}
    operating_hours JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stores_tenant ON stores(tenant_id);
CREATE INDEX idx_stores_trader ON stores(trader_id);

-- ============================================================================
-- PRODUCTS & INVENTORY
-- ============================================================================

-- Product Categories
CREATE TABLE product_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES product_categories(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_product_categories_tenant ON product_categories(tenant_id);
CREATE INDEX idx_product_categories_store ON product_categories(store_id);

-- Products (Base product without variants)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    category_id UUID REFERENCES product_categories(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    sku VARCHAR(100), -- Stock Keeping Unit
    barcode VARCHAR(100), -- EAN/UPC barcode
    qr_code VARCHAR(500), -- Generated QR code URL
    brand VARCHAR(100),
    costing_method VARCHAR(20) DEFAULT 'average' CHECK (costing_method IN ('fifo', 'lifo', 'average')),
    base_price DECIMAL(15, 2) NOT NULL,
    cost_price DECIMAL(15, 2), -- Cost of goods sold
    min_selling_price DECIMAL(15, 2), -- Minimum allowed selling price
    tax_rate DECIMAL(5, 2) DEFAULT 0, -- Product-specific tax rate
    is_taxable BOOLEAN DEFAULT TRUE,
    track_inventory BOOLEAN DEFAULT TRUE,
    low_stock_threshold INTEGER DEFAULT 10,
    auto_reorder_enabled BOOLEAN DEFAULT FALSE,
    reorder_quantity INTEGER,
    supplier_id UUID, -- References suppliers table
    images JSONB, -- Array of image URLs
    attributes JSONB, -- {"size": ["S", "M", "L"], "color": ["Red", "Blue"]}
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_tenant ON products(tenant_id);
CREATE INDEX idx_products_store ON products(store_id);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_barcode ON products(barcode);

-- Product Variants (Size, Color, Brand, etc.)
CREATE TABLE product_variants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku VARCHAR(100) UNIQUE,
    barcode VARCHAR(100),
    variant_options JSONB NOT NULL, -- {"size": "M", "color": "Red"}
    price_adjustment DECIMAL(15, 2) DEFAULT 0, -- Price difference from base
    cost_price_adjustment DECIMAL(15, 2) DEFAULT 0,
    quantity_in_stock INTEGER DEFAULT 0,
    quantity_reserved INTEGER DEFAULT 0, -- For pending sales
    quantity_incoming INTEGER DEFAULT 0, -- From purchase orders
    reorder_level INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_product_variants_tenant ON product_variants(tenant_id);
CREATE INDEX idx_product_variants_product ON product_variants(product_id);
CREATE INDEX idx_product_variants_sku ON product_variants(sku);
CREATE INDEX idx_product_variants_barcode ON product_variants(barcode);

-- Inventory Batches (For FIFO/LIFO and expiry tracking)
CREATE TABLE inventory_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
    batch_number VARCHAR(100),
    quantity_received INTEGER NOT NULL,
    quantity_remaining INTEGER NOT NULL,
    unit_cost DECIMAL(15, 2) NOT NULL,
    expiry_date DATE, -- For perishable goods
    manufacture_date DATE,
    received_from UUID, -- Purchase order ID
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_inventory_batches_tenant ON inventory_batches(tenant_id);
CREATE INDEX idx_inventory_batches_store ON inventory_batches(store_id);
CREATE INDEX idx_inventory_batches_variant ON inventory_batches(variant_id);
CREATE INDEX idx_inventory_batches_expiry ON inventory_batches(expiry_date);

-- Stock Movements (Audit trail for all inventory changes)
CREATE TABLE stock_movements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
    movement_type VARCHAR(50) NOT NULL CHECK (movement_type IN ('sale', 'purchase', 'return', 'adjustment', 'transfer', 'damage', 'expiry')),
    quantity INTEGER NOT NULL, -- Positive for in, negative for out
    reference_type VARCHAR(50), -- 'sale', 'purchase_order', etc.
    reference_id UUID, -- ID of the referencing entity
    batch_id UUID REFERENCES inventory_batches(id) ON DELETE SET NULL,
    reason TEXT, -- For adjustments
    performed_by UUID REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stock_movements_tenant ON stock_movements(tenant_id);
CREATE INDEX idx_stock_movements_store ON stock_movements(store_id);
CREATE INDEX idx_stock_movements_variant ON stock_movements(variant_id);
CREATE INDEX idx_stock_movements_type ON stock_movements(movement_type);

-- Suppliers
CREATE TABLE suppliers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(20),
    address TEXT,
    city VARCHAR(100),
    country VARCHAR(2),
    tax_id VARCHAR(100),
    payment_terms INTEGER DEFAULT 30, -- Days
    credit_limit DECIMAL(15, 2),
    currency VARCHAR(3) DEFAULT 'XAF',
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_suppliers_tenant ON suppliers(tenant_id);

-- ============================================================================
-- CLIENTS (CRM)
-- ============================================================================

-- Clients/Customers
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(20),
    alternate_phone VARCHAR(20),
    address TEXT,
    city VARCHAR(100),
    country VARCHAR(2),
    date_of_birth DATE,
    gender VARCHAR(10),
    id_type VARCHAR(50), -- National ID, Passport, etc.
    id_number VARCHAR(100),
    tags VARCHAR(100)[], -- For segmentation
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_clients_tenant ON clients(tenant_id);
CREATE INDEX idx_clients_store ON clients(store_id);
CREATE INDEX idx_clients_phone ON clients(phone);
CREATE INDEX idx_clients_email ON clients(email);

-- Client Credit Management
CREATE TABLE client_credit_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    credit_limit DECIMAL(15, 2) DEFAULT 0,
    current_balance DECIMAL(15, 2) DEFAULT 0,
    overdue_balance DECIMAL(15, 2) DEFAULT 0,
    credit_status VARCHAR(20) DEFAULT 'good' CHECK (credit_status IN ('good', 'warning', 'blocked')),
    last_payment_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_client_credit_profiles_tenant ON client_credit_profiles(tenant_id);
CREATE INDEX idx_client_credit_profiles_client ON client_credit_profiles(client_id);

-- ============================================================================
-- SALES TRANSACTIONS
-- ============================================================================

-- Sales Orders/Invoices
CREATE TABLE sales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    sale_number VARCHAR(50) UNIQUE NOT NULL, -- Auto-generated: STORE-YYYYMMDD-0001
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    cashier_id UUID REFERENCES users(id) ON DELETE SET NULL,
    sale_type VARCHAR(20) DEFAULT 'retail' CHECK (sale_type IN ('retail', 'wholesale', 'online', 'quote')),
    status VARCHAR(20) DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'voided', 'refunded', 'partial_refund')),
    
    -- Financials
    subtotal DECIMAL(15, 2) NOT NULL,
    discount_total DECIMAL(15, 2) DEFAULT 0,
    tax_total DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,
    amount_paid DECIMAL(15, 2) NOT NULL,
    balance_due DECIMAL(15, 2) DEFAULT 0,
    
    -- Payment details
    payment_status VARCHAR(20) DEFAULT 'paid' CHECK (payment_status IN ('paid', 'partial', 'unpaid', 'overdue')),
    payment_methods JSONB, -- [{"method": "cash", "amount": 5000}, {"method": "mobile_money", "amount": 5000}]
    
    -- Notes
    notes TEXT,
    internal_notes TEXT,
    
    -- Timestamps
    sale_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP WITH TIME ZONE, -- For credit sales
    voided_at TIMESTAMP WITH TIME ZONE,
    voided_by UUID REFERENCES users(id),
    void_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sales_tenant ON sales(tenant_id);
CREATE INDEX idx_sales_store ON sales(store_id);
CREATE INDEX idx_sales_client ON sales(client_id);
CREATE INDEX idx_sales_date ON sales(sale_date);
CREATE INDEX idx_sales_number ON sales(sale_number);
CREATE INDEX idx_sales_status ON sales(status);

-- Sale Items (Line items)
CREATE TABLE sale_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    sale_id UUID NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    variant_id UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    product_name VARCHAR(255) NOT NULL, -- Snapshot at time of sale
    variant_name VARCHAR(255), -- Snapshot at time of sale
    
    quantity DECIMAL(10, 2) NOT NULL,
    unit_price DECIMAL(15, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) DEFAULT 0,
    discount_amount DECIMAL(15, 2) DEFAULT 0,
    tax_rate DECIMAL(5, 2) DEFAULT 0,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    subtotal DECIMAL(15, 2) NOT NULL,
    total DECIMAL(15, 2) NOT NULL,
    
    -- Cost tracking for profit calculation
    unit_cost DECIMAL(15, 2), -- COGS at time of sale
    total_cost DECIMAL(15, 2), -- quantity * unit_cost
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sale_items_tenant ON sale_items(tenant_id);
CREATE INDEX idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX idx_sale_items_variant ON sale_items(variant_id);

-- Sale Returns
CREATE TABLE sale_returns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    return_number VARCHAR(50) UNIQUE NOT NULL,
    original_sale_id UUID NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    processed_by UUID REFERENCES users(id),
    
    return_type VARCHAR(20) DEFAULT 'refund' CHECK (return_type IN ('refund', 'exchange', 'store_credit')),
    status VARCHAR(20) DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'rejected')),
    
    subtotal DECIMAL(15, 2) NOT NULL,
    tax_total DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,
    
    reason TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sale_returns_tenant ON sale_returns(tenant_id);
CREATE INDEX idx_sale_returns_sale ON sale_returns(original_sale_id);

-- ============================================================================
-- PURCHASES
-- ============================================================================

-- Purchase Orders
CREATE TABLE purchases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    supplier_id UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    purchase_number VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'received', 'partial', 'cancelled')),
    
    subtotal DECIMAL(15, 2) NOT NULL,
    discount_total DECIMAL(15, 2) DEFAULT 0,
    tax_total DECIMAL(15, 2) DEFAULT 0,
    shipping_cost DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,
    amount_paid DECIMAL(15, 2) DEFAULT 0,
    balance_due DECIMAL(15, 2) DEFAULT 0,
    
    payment_status VARCHAR(20) DEFAULT 'unpaid' CHECK (payment_status IN ('paid', 'partial', 'unpaid')),
    expected_delivery_date DATE,
    received_date TIMESTAMP WITH TIME ZONE,
    received_by UUID REFERENCES users(id),
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_purchases_tenant ON purchases(tenant_id);
CREATE INDEX idx_purchases_store ON purchases(store_id);
CREATE INDEX idx_purchases_supplier ON purchases(supplier_id);
CREATE INDEX idx_purchases_status ON purchases(status);

-- Purchase Order Items
CREATE TABLE purchase_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    purchase_id UUID NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    variant_id UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    product_name VARCHAR(255) NOT NULL,
    variant_name VARCHAR(255),
    
    quantity_ordered INTEGER NOT NULL,
    quantity_received INTEGER DEFAULT 0,
    unit_cost DECIMAL(15, 2) NOT NULL,
    discount_percent DECIMAL(5, 2) DEFAULT 0,
    tax_rate DECIMAL(5, 2) DEFAULT 0,
    subtotal DECIMAL(15, 2) NOT NULL,
    total DECIMAL(15, 2) NOT NULL,
    
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_purchase_items_tenant ON purchase_items(tenant_id);
CREATE INDEX idx_purchase_items_purchase ON purchase_items(purchase_id);

-- ============================================================================
-- EXPENSES
-- ============================================================================

-- Expense Categories
CREATE TABLE expense_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parent_id UUID REFERENCES expense_categories(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_expense_categories_tenant ON expense_categories(tenant_id);

-- Expenses
CREATE TABLE expenses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    category_id UUID REFERENCES expense_categories(id) ON DELETE SET NULL,
    expense_number VARCHAR(50) UNIQUE NOT NULL,
    
    amount DECIMAL(15, 2) NOT NULL,
    tax_amount DECIMAL(15, 2) DEFAULT 0,
    total_amount DECIMAL(15, 2) NOT NULL,
    
    payment_method VARCHAR(50) DEFAULT 'cash' CHECK (payment_method IN ('cash', 'mobile_money', 'bank_transfer', 'card', 'credit')),
    payment_reference VARCHAR(100), -- Transaction ID, check number, etc.
    
    vendor_name VARCHAR(255), -- For non-registered vendors
    vendor_contact VARCHAR(255),
    
    expense_date DATE NOT NULL,
    receipt_url VARCHAR(500), -- Photo of receipt
    description TEXT NOT NULL,
    notes TEXT,
    
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_expenses_tenant ON expenses(tenant_id);
CREATE INDEX idx_expenses_store ON expenses(store_id);
CREATE INDEX idx_expenses_category ON expenses(category_id);
CREATE INDEX idx_expenses_date ON expenses(expense_date);

-- ============================================================================
-- LOYALTY PROGRAM
-- ============================================================================

-- Loyalty Programs
CREATE TABLE loyalty_programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Points configuration
    points_per_currency_unit DECIMAL(10, 2) DEFAULT 1, -- e.g., 1 point per 100 XAF
    currency_unit DECIMAL(10, 2) DEFAULT 100, -- The unit for earning points
    points_value DECIMAL(10, 2) DEFAULT 1, -- Value of 1 point in currency
    min_points_redemption INTEGER DEFAULT 100,
    max_discount_percent DECIMAL(5, 2) DEFAULT 20, -- Max discount via points
    
    -- Expiration
    points_expiry_months INTEGER, -- NULL = never expire
    expiry_policy VARCHAR(50) DEFAULT 'rolling' CHECK (expiry_policy IN ('rolling', 'fixed')),
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_loyalty_programs_tenant ON loyalty_programs(tenant_id);

-- Loyalty Tiers
CREATE TABLE loyalty_tiers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    program_id UUID NOT NULL REFERENCES loyalty_programs(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- Bronze, Silver, Gold, Platinum
    description TEXT,
    icon_url VARCHAR(500),
    
    -- Qualification criteria
    min_lifetime_spend DECIMAL(15, 2) DEFAULT 0,
    min_lifetime_points INTEGER DEFAULT 0,
    min_transactions INTEGER DEFAULT 0,
    
    -- Tier benefits
    points_multiplier DECIMAL(5, 2) DEFAULT 1, -- Extra points multiplier
    discount_percent DECIMAL(5, 2) DEFAULT 0, -- Automatic discount
    birthday_bonus_points INTEGER DEFAULT 0,
    exclusive_access BOOLEAN DEFAULT FALSE,
    free_delivery BOOLEAN DEFAULT FALSE,
    
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_loyalty_tiers_tenant ON loyalty_tiers(tenant_id);
CREATE INDEX idx_loyalty_tiers_program ON loyalty_tiers(program_id);

-- Client Loyalty Accounts
CREATE TABLE client_loyalty_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES loyalty_programs(id) ON DELETE CASCADE,
    tier_id UUID REFERENCES loyalty_tiers(id) ON DELETE SET NULL,
    
    current_points INTEGER DEFAULT 0,
    lifetime_points_earned INTEGER DEFAULT 0,
    lifetime_points_spent INTEGER DEFAULT 0,
    lifetime_spend DECIMAL(15, 2) DEFAULT 0,
    transaction_count INTEGER DEFAULT 0,
    
    last_activity_at TIMESTAMP WITH TIME ZONE,
    tier_upgraded_at TIMESTAMP WITH TIME ZONE,
    next_review_date DATE, -- For tier downgrade review
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(client_id, program_id)
);

CREATE INDEX idx_client_loyalty_accounts_tenant ON client_loyalty_accounts(tenant_id);
CREATE INDEX idx_client_loyalty_accounts_client ON client_loyalty_accounts(client_id);
CREATE INDEX idx_client_loyalty_accounts_program ON client_loyalty_accounts(program_id);

-- Loyalty Transactions (Points earned/spent)
CREATE TABLE loyalty_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL REFERENCES client_loyalty_accounts(id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('earn', 'redeem', 'adjustment', 'expire', 'bonus', 'refund')),
    
    points INTEGER NOT NULL, -- Positive for earn, negative for redeem
    balance_after INTEGER NOT NULL,
    
    reference_type VARCHAR(50), -- 'sale', 'manual', 'promotion'
    reference_id UUID, -- Sale ID or other reference
    
    description TEXT,
    notes TEXT,
    performed_by UUID REFERENCES users(id),
    expires_at TIMESTAMP WITH TIME ZONE, -- When these points expire
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_loyalty_transactions_tenant ON loyalty_transactions(tenant_id);
CREATE INDEX idx_loyalty_transactions_account ON loyalty_transactions(account_id);
CREATE INDEX idx_loyalty_transactions_type ON loyalty_transactions(transaction_type);

-- ============================================================================
-- CASH MANAGEMENT
-- ============================================================================

-- Cash Registers/Sessions
CREATE TABLE cash_registers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    register_name VARCHAR(100),
    
    opening_balance DECIMAL(15, 2) NOT NULL,
    closing_balance DECIMAL(15, 2),
    expected_balance DECIMAL(15, 2),
    variance DECIMAL(15, 2),
    
    opened_by UUID REFERENCES users(id),
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_by UUID REFERENCES users(id),
    closed_at TIMESTAMP WITH TIME ZONE,
    
    status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'closed', 'suspended')),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cash_registers_tenant ON cash_registers(tenant_id);
CREATE INDEX idx_cash_registers_store ON cash_registers(store_id);

-- Cash Transactions (Non-sales)
CREATE TABLE cash_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    register_id UUID NOT NULL REFERENCES cash_registers(id) ON DELETE CASCADE,
    transaction_type VARCHAR(50) NOT NULL CHECK (transaction_type IN ('deposit', 'withdrawal', 'float', 'petty_cash', 'transfer')),
    
    amount DECIMAL(15, 2) NOT NULL,
    payment_method VARCHAR(50) DEFAULT 'cash',
    
    description TEXT NOT NULL,
    reference VARCHAR(100),
    receipt_url VARCHAR(500),
    
    performed_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cash_transactions_tenant ON cash_transactions(tenant_id);
CREATE INDEX idx_cash_transactions_register ON cash_transactions(register_id);

-- ============================================================================
-- REPORTING & ANALYTICS
-- ============================================================================

-- Report Schedules
CREATE TABLE report_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    
    report_type VARCHAR(50) NOT NULL, -- 'daily_sales', 'weekly_profit', 'monthly_inventory'
    frequency VARCHAR(20) NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'custom')),
    
    -- Schedule config
    day_of_week INTEGER, -- 0-6 for weekly
    day_of_month INTEGER, -- 1-31 for monthly
    time_of_day TIME DEFAULT '08:00:00',
    
    -- Delivery
    delivery_method VARCHAR(50) DEFAULT 'in_app' CHECK (delivery_method IN ('in_app', 'email', 'sms', 'whatsapp')),
    recipients JSONB, -- Array of email/phone numbers
    format VARCHAR(20) DEFAULT 'summary' CHECK (format IN ('summary', 'detailed', 'pdf', 'excel')),
    
    filters JSONB, -- Custom filters for the report
    is_active BOOLEAN DEFAULT TRUE,
    
    last_run_at TIMESTAMP WITH TIME ZONE,
    next_run_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_report_schedules_tenant ON report_schedules(tenant_id);
CREATE INDEX idx_report_schedules_user ON report_schedules(user_id);

-- Generated Reports (Cached results)
CREATE TABLE generated_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    schedule_id UUID REFERENCES report_schedules(id) ON DELETE SET NULL,
    
    report_type VARCHAR(50) NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    
    summary_data JSONB NOT NULL, -- Key metrics
    detailed_data JSONB, -- Full data if needed
    
    file_url VARCHAR(500), -- PDF/Excel file if generated
    file_format VARCHAR(20),
    
    generated_by UUID REFERENCES users(id),
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE -- When to purge old reports
);

CREATE INDEX idx_generated_reports_tenant ON generated_reports(tenant_id);
CREATE INDEX idx_generated_reports_type ON generated_reports(report_type);
CREATE INDEX idx_generated_reports_period ON generated_reports(period_start, period_end);

-- ============================================================================
-- CHAT & MESSAGING
-- ============================================================================

-- Chat Conversations (for chat-based reporting)
CREATE TABLE chat_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_type VARCHAR(50) DEFAULT 'assistant' CHECK (conversation_type IN ('assistant', 'support', 'broadcast')),
    
    title VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_conversations_tenant ON chat_conversations(tenant_id);
CREATE INDEX idx_chat_conversations_user ON chat_conversations(user_id);

-- Chat Messages
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    
    message_type VARCHAR(20) NOT NULL CHECK (message_type IN ('user', 'assistant', 'system', 'report')),
    content TEXT NOT NULL,
    
    -- For report messages
    report_data JSONB, -- Embedded report data
    report_file_url VARCHAR(500),
    
    -- Metadata
    command_type VARCHAR(50), -- Parsed command type
    entities JSONB, -- Extracted entities (dates, stores, etc.)
    
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_chat_messages_tenant ON chat_messages(tenant_id);
CREATE INDEX idx_chat_messages_conversation ON chat_messages(conversation_id);
CREATE INDEX idx_chat_messages_type ON chat_messages(message_type);

-- ============================================================================
-- AUDIT & SECURITY
-- ============================================================================

-- Audit Log (Track all changes)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('create', 'update', 'delete', 'view', 'export')),
    
    old_values JSONB, -- Previous state (for updates/deletes)
    new_values JSONB, -- New state (for creates/updates)
    changed_fields VARCHAR(100)[], -- Which fields changed
    
    performed_by UUID REFERENCES users(id),
    performed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_date ON audit_logs(performed_at);

-- Sync Queue (For offline-online sync)
CREATE TABLE sync_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    device_id VARCHAR(100) NOT NULL, -- Unique device identifier
    
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    operation VARCHAR(20) NOT NULL CHECK (operation IN ('create', 'update', 'delete')),
    
    payload JSONB NOT NULL, -- The actual data change
    local_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, -- Client-side timestamp
    server_timestamp TIMESTAMP WITH TIME ZONE,
    
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'conflict')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_sync_queue_tenant ON sync_queue(tenant_id);
CREATE INDEX idx_sync_queue_device ON sync_queue(device_id);
CREATE INDEX idx_sync_queue_status ON sync_queue(status);
CREATE INDEX idx_sync_queue_created ON sync_queue(created_at);

-- Device Registrations
CREATE TABLE device_registrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    
    device_id VARCHAR(100) NOT NULL UNIQUE,
    device_name VARCHAR(255),
    device_type VARCHAR(50), -- 'android', 'ios', 'web'
    os_version VARCHAR(50),
    app_version VARCHAR(50),
    
    push_token VARCHAR(500), -- For push notifications
    last_sync_at TIMESTAMP WITH TIME ZONE,
    last_active_at TIMESTAMP WITH TIME ZONE,
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_device_registrations_tenant ON device_registrations(tenant_id);
CREATE INDEX idx_device_registrations_device ON device_registrations(device_id);

-- ============================================================================
-- SYSTEM CONFIGURATION
-- ============================================================================

-- Exchange Rates (For multi-currency support)
CREATE TABLE exchange_rates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    
    base_currency VARCHAR(3) NOT NULL,
    target_currency VARCHAR(3) NOT NULL,
    rate DECIMAL(15, 6) NOT NULL,
    
    source VARCHAR(50), -- 'central_bank', 'api', 'manual'
    effective_date DATE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_exchange_rates_tenant ON exchange_rates(tenant_id);
CREATE INDEX idx_exchange_rates_currencies ON exchange_rates(base_currency, target_currency);
CREATE INDEX idx_exchange_rates_date ON exchange_rates(effective_date);

-- Promotions & Discounts
CREATE TABLE promotions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL,
    description TEXT,
    promotion_type VARCHAR(50) NOT NULL CHECK (promotion_type IN ('percentage_off', 'fixed_amount', 'buy_x_get_y', 'bundle', 'free_shipping')),
    
    -- Configuration
    discount_value DECIMAL(15, 2), -- Percentage or fixed amount
    buy_quantity INTEGER, -- For buy X get Y
    get_quantity INTEGER,
    get_product_ids UUID[], -- For buy X get Y
    
    -- Conditions
    min_purchase_amount DECIMAL(15, 2),
    applicable_product_ids UUID[], -- NULL = all products
    applicable_category_ids UUID[], -- NULL = all categories
    applicable_tier_ids UUID[], -- Customer tiers eligible
    
    -- Promo codes
    promo_code VARCHAR(50), -- NULL = automatic
    usage_limit INTEGER,
    usage_count INTEGER DEFAULT 0,
    limit_per_customer INTEGER,
    
    -- Timing
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    active_days VARCHAR(7)[], -- ['mon', 'tue', ...]
    active_hours_start TIME,
    active_hours_end TIME,
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_promotions_tenant ON promotions(tenant_id);
CREATE INDEX idx_promotions_store ON promotions(store_id);
CREATE INDEX idx_promotions_dates ON promotions(start_date, end_date);
CREATE INDEX idx_promotions_code ON promotions(promo_code);

-- ============================================================================
-- UTILITY FUNCTIONS & TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply to tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_traders_updated_at BEFORE UPDATE ON traders FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_stores_updated_at BEFORE UPDATE ON stores FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_product_variants_updated_at BEFORE UPDATE ON product_variants FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to generate sale number
CREATE OR REPLACE FUNCTION generate_sale_number()
RETURNS TRIGGER AS $$
DECLARE
    store_code VARCHAR;
    date_str VARCHAR;
    seq_num INTEGER;
BEGIN
    SELECT code INTO store_code FROM stores WHERE id = NEW.store_id;
    IF store_code IS NULL THEN
        store_code := 'STORE';
    END IF;
    
    date_str := TO_CHAR(NEW.sale_date, 'YYYYMMDD');
    
    SELECT COALESCE(MAX(CAST(SUBSTRING(sale_number FROM '.+-([0-9]+)$' AS INTEGER)), 0) + 1
    INTO seq_num
    FROM sales
    WHERE store_id = NEW.store_id 
      AND sale_date::date = NEW.sale_date::date;
    
    NEW.sale_number := store_code || '-' || date_str || '-' || LPAD(seq_num::text, 4, '0');
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER before_sale_insert BEFORE INSERT ON sales FOR EACH ROW EXECUTE FUNCTION generate_sale_number();

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Product stock overview
CREATE VIEW product_stock_view AS
SELECT 
    p.id,
    p.name,
    p.sku,
    pv.variant_options,
    SUM(pv.quantity_in_stock) as total_stock,
    SUM(pv.quantity_reserved) as reserved,
    SUM(pv.quantity_incoming) as incoming,
    p.low_stock_threshold,
    CASE 
        WHEN SUM(pv.quantity_in_stock) <= p.low_stock_threshold THEN 'low'
        WHEN SUM(pv.quantity_in_stock) = 0 THEN 'out_of_stock'
        ELSE 'in_stock'
    END as stock_status
FROM products p
LEFT JOIN product_variants pv ON p.id = pv.product_id
WHERE p.is_active AND pv.is_active
GROUP BY p.id, p.name, p.sku, pv.variant_options, p.low_stock_threshold;

-- Daily sales summary
CREATE VIEW daily_sales_summary AS
SELECT 
    s.store_id,
    DATE(s.sale_date) as sale_date,
    COUNT(*) as total_transactions,
    SUM(s.total_amount) as total_revenue,
    SUM(s.amount_paid) as total_collected,
    SUM(s.balance_due) as total_receivables,
    AVG(s.total_amount) as average_transaction_value
FROM sales s
WHERE s.status != 'voided'
GROUP BY s.store_id, DATE(s.sale_date);

-- Profit by product (daily)
CREATE VIEW daily_product_profit AS
SELECT 
    si.sale_id,
    si.variant_id,
    si.product_name,
    DATE(s.sale_date) as sale_date,
    si.quantity,
    si.unit_price,
    si.unit_cost,
    (si.unit_price - si.unit_cost) * si.quantity as gross_profit,
    (((si.unit_price - si.unit_cost) / NULLIF(si.unit_price, 0)) * 100) as profit_margin_percent
FROM sale_items si
JOIN sales s ON si.sale_id = s.id
WHERE s.status != 'voided';

-- Client loyalty overview
CREATE VIEW client_loyalty_overview AS
SELECT 
    c.id as client_id,
    c.first_name || ' ' || c.last_name as client_name,
    c.phone,
    cla.current_points,
    cla.lifetime_points_earned,
    cla.lifetime_spend,
    lt.name as tier_name,
    lt.discount_percent as tier_discount
FROM clients c
JOIN client_loyalty_accounts cla ON c.id = cla.client_id
LEFT JOIN loyalty_tiers lt ON cla.tier_id = lt.id
WHERE c.is_active AND cla.current_points > 0;

-- Comments on tables for documentation
COMMENT ON TABLE users IS 'System users including traders, staff, and cashiers';
COMMENT ON TABLE traders IS 'Business owners/traders who own the stores';
COMMENT ON TABLE stores IS 'Individual retail locations per trader';
COMMENT ON TABLE products IS 'Base products without variants';
COMMENT ON TABLE product_variants IS 'Product variations (size, color, etc.)';
COMMENT ON TABLE sales IS 'Sales transactions/invoices';
COMMENT ON TABLE sale_items IS 'Line items within a sale';
COMMENT ON TABLE clients IS 'Customer records for CRM';
COMMENT ON TABLE loyalty_programs IS 'Loyalty points program configuration';
COMMENT ON TABLE loyalty_tiers IS 'Customer tiers within loyalty program';
COMMENT ON TABLE expenses IS 'Business expenses tracking';
COMMENT ON TABLE purchases IS 'Purchase orders from suppliers';
COMMENT ON TABLE cash_registers IS 'Cash register sessions';
COMMENT ON TABLE audit_logs IS 'Complete audit trail of all changes';
COMMENT ON TABLE sync_queue IS 'Queue for offline-online synchronization';
