# Intelligent Inventory & Customer Engagement Module

## Overview
This module adds **AI-driven intelligence** to the African POS system, focusing on waste reduction, stock optimization, and safe credit management for informal traders.

### Key Features Implemented
1.  **Smart Expiry & Flash Sales**: Automated tracking of perishable goods with dynamic discount suggestions to prevent waste.
2.  **Visual Search Metadata**: Support for identifying unbranded goods via image features (color/texture) when barcodes are missing.
3.  **Predictive Restocking**: Seasonality-aware demand forecasting to prevent stockouts.
4.  **Customer Soft Credit Scoring**: Proprietary risk assessment allowing traders to safely offer credit to reliable customers.

---

## Database Schema (`database/intelligent_inventory.sql`)

### Tables Created

| Table Name | Purpose | Key Columns |
| :--- | :--- | :--- |
| `inventory_expiry_alerts` | Tracks batches approaching expiry | `days_until_expiry`, `suggested_discount_percent`, `status` |
| `flash_sale_campaigns` | Manages automated clearance sales | `target_criteria` (JSONB), `revenue_generated` |
| `product_visual_signatures` | Stores image features for search | `color_histogram` (JSONB), `texture_features` |
| `product_user_photos` | Crowdsourced product images | `image_hash`, `confidence_score` |
| `restock_patterns` | Learns sales velocity & seasonality | `seasonal_multipliers` (JSONB), `reorder_point` |
| `restock_recommendations` | Daily actionable restock list | `priority_score`, `reason_code` |
| `customer_credit_events` | Ledger of credit behavior | `days_overdue`, `event_type` |
| `customer_credit_scores` | Snapshot of customer risk | `final_score`, `risk_tier`, `recommended_action` |

### Key Functions

1.  **`calc_expiry_discount(days_left, base_price)`**
    *   **Logic**: Returns discount % based on urgency (e.g., 50% off if <3 days left).
    *   **Usage**: Called by UI to display dynamic pricing.

2.  **`process_expiry_alerts()`**
    *   **Logic**: Daily cron job. Marks expired items, triggers alerts for items entering the 7-day window.
    *   **Usage**: Schedule via `pg_cron` or backend worker.

3.  **`calculate_customer_credit_score(client_id, store_id)`**
    *   **Logic**: Computes weighted score (Repayment 40%, Frequency 20%, Tenure 20%, Utilization 20%).
    *   **Output**: Updates `customer_credit_scores` with tier (Low/Medium/High Risk).

### Views for Dashboards

*   `vw_urgent_expiry`: List of items expiring in ≤7 days with potential loss calculation.
*   `vw_restock_priority`: Sorted list of products needing immediate reorder.
*   `vw_customer_risk_profile`: Quick lookup for cashiers to see if a customer is eligible for credit.

---

## Python Services (`services/intelligent_inventory.py`)

### Classes

#### 1. `SmartExpiryService`
*   **Responsibility**: Minimize spoilage losses.
*   **Key Methods**:
    *   `calculate_discount(days_left)`: Mirrors SQL logic.
    *   `get_urgent_expiries(store_id)`: Fetches data for dashboard widgets.
    *   `create_flash_sale(store_id, alert_ids)`: Bundles expiring items into a campaign.

#### 2. `VisualSearchService`
*   **Responsibility**: Enable search for unbranded goods.
*   **Key Methods**:
    *   `register_visual_signature(...)`: Saves color/texture metadata when a user snaps a photo.
    *   `find_similar_products(...)`: Matches query colors against stored signatures.

#### 3. `PredictiveRestockingService`
*   **Responsibility**: Optimize inventory levels.
*   **Key Methods**:
    *   `calculate_seasonal_multiplier(category, date)`: Applies factors for Ramadan, Back-to-School, etc.
    *   `generate_restock_recommendations(store_id)`: The core engine producing the daily to-buy list.

#### 4. `CustomerCreditScoringService`
*   **Responsibility**: Manage financial risk.
*   **Key Methods**:
    *   `update_client_score(client_id, store_id)`: Recalculates score after payments/sales.
    *   `check_credit_eligibility(client_id, amount)`: **Critical**: Called at POS before confirming a credit sale.

### Background Jobs
*   `run_daily_intelligence_jobs()`: Orchestrator function to be called by Celery/Cron nightly.

---

## Integration Guide

### 1. Migration
Run the SQL file to create tables and functions:
```bash
psql -U postgres -d african_pos -f database/intelligent_inventory.sql
```

### 2. Daily Cron Setup
Configure your server to run the orchestrator nightly:
```python
# In celery.py or crontab
@app.task
def nightly_intelligence():
    from services.intelligent_inventory import run_daily_intelligence_jobs
    run_daily_intelligence_jobs()
```

### 3. Flutter/UI Integration Points

#### A. Expiry Dashboard Widget
*   **Query**: `SELECT * FROM vw_urgent_expiry WHERE store_id = ?`
*   **Action**: Show "Create Flash Sale" button if count > 0.

#### B. Restock Tab
*   **Query**: `SELECT * FROM vw_restock_priority`
*   **UI**: Display as a checklist. Allow user to mark as "Ordered".

#### C. Credit Approval Modal
*   **Trigger**: When Cashier selects "Credit" payment.
*   **Logic**:
    ```dart
    var profile = await CreditService.getProfile(customerId);
    if (profile.riskTier == 'VERY_HIGH_RISK') {
       showError("Cash Only");
    } else if (profile.outstanding + newAmount > profile.limit) {
       showError("Limit Exceeded");
    }
    ```

#### D. Visual Search
*   **Flow**: User taps "Search by Camera" → Takes Photo → App extracts dominant colors → Calls `find_similar_products`.

---

## Business Value for African Traders

| Feature | Problem Solved | Economic Impact |
| :--- | :--- | :--- |
| **Smart Expiry** | Spoilage of milk, bread, drugs | **Recovered Revenue**: 5-15% reduction in waste |
| **Visual Search** | Lost sales due to unbranded items | **Efficiency**: Faster checkout, fewer errors |
| **Predictive Restock** | Stockouts of fast movers (Sugar, Oil) | **Increased Sales**: Never miss a sale due to empty shelf |
| **Soft Credit Score** | Bad debt from unreliable customers | **Risk Reduction**: Safe expansion of credit offerings |

---

## Performance Considerations

1.  **Indexes**: Critical indexes added on `expiry_date`, `client_id`, and `status` columns.
2.  **Generated Columns**: `days_until_expiry` and `final_score` are computed automatically by Postgres, ensuring read speed.
3.  **JSONB**: Used for flexible storage of seasonal multipliers and visual features, allowing schema evolution without migrations.
4.  **Offline Sync**: All new tables include `store_id` for easy partitioning during sync.

## Future Enhancements
*   **pgvector Integration**: Replace JSONB color histograms with true vector embeddings for higher accuracy visual search.
*   **Supplier API**: Auto-send `restock_recommendations` as purchase orders to supplier WhatsApp numbers.
*   **Group Scoring**: Aggregate credit scores for cooperative buying groups.
