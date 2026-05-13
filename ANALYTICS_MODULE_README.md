# African POS Analytics Module Documentation

## Overview

The Analytics Module provides comprehensive business intelligence for the African POS system, enabling retailers and traders to make data-driven decisions. It includes database views, indexes, analytical functions, and a Python service layer.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ANALYTICS MODULE                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐    ┌──────────────────┐                │
│  │  Database Layer  │    │   Service Layer  │                │
│  │                  │    │                  │                │
│  │  • Views         │◄──►│  • AnalyticsSvc  │                │
│  │  • Indexes       │    │  • Metrics       │                │
│  │  • Functions     │    │  • Reports       │                │
│  │  • Mat. Views    │    │                  │                │
│  └──────────────────┘    └──────────────────┘                │
│           ▲                       ▲                           │
│           │                       │                           │
│  ┌────────┴───────────────────────┴────────┐                 │
│  │          API Endpoints (FastAPI)        │                 │
│  └─────────────────────────────────────────┘                 │
│                       │                                       │
│  ┌────────────────────┴────────────────────┐                 │
│  │         Flutter Mobile App              │                 │
│  │    (Dashboards, Reports, Charts)        │                 │
│  └─────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

## Installation & Setup

### 1. Database Setup

Run the SQL migration to create all analytics objects:

```bash
psql -U your_user -d african_pos -f DATABASE_ANALYTICS_MODULE.sql
```

This creates:
- **20+ performance indexes** for fast queries
- **6 core analytical views** for common metrics
- **2 materialized views** for heavy computations
- **3 analytical functions** for complex calculations
- **Multiple pre-built report queries**

### 2. Python Service Integration

```python
from analytics_service import AnalyticsService, MetricType, PeriodType
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Initialize database connection
engine = create_engine("postgresql://user:pass@localhost/african_pos")
Session = sessionmaker(bind=engine)
db_session = Session()

# Initialize analytics service
analytics = AnalyticsService(db_session)
```

## Core Features

### 1. Sales Analytics

#### Daily Sales Summary
```python
from datetime import date, timedelta

summary = analytics.get_daily_sales_summary(
    store_id=1,
    start_date=date.today() - timedelta(days=30),
    end_date=date.today()
)

# Returns: List of daily metrics including:
# - total_transactions
# - gross_revenue, net_revenue
# - average_ticket_size
# - unique_customers
# - payment method breakdown
```

#### Sales Trend Analysis
```python
trends = analytics.get_sales_trend_analysis(
    store_id=1,
    start_date=date.today() - timedelta(days=90),
    end_date=date.today(),
    period=PeriodType.WEEKLY  # DAILY, WEEKLY, MONTHLY
)

# Returns:
# {
#   'trends': [...],  # Weekly data with growth %
#   'summary': {
#       'total_revenue': 125000.00,
#       'average_growth_percent': 5.2,
#       'best_period': date(2024, 1, 15),
#       'worst_period': date(2024, 1, 8)
#   }
# }
```

#### Hourly Sales Pattern (Peak Hours)
```python
hourly_pattern = analytics.get_hourly_sales_pattern(
    store_id=1,
    days_back=30
)

# Identifies peak hours for staffing optimization
# Returns: [{hour_of_day, transaction_count, revenue, ...}]
```

### 2. Product Analytics

#### Product Performance
```python
products = analytics.get_product_performance(
    store_id=1,
    category_id=5,  # Optional filter
    limit=50
)

for product in products:
    print(f"{product.product_name}:")
    print(f"  - Sold: {product.total_quantity_sold} units")
    print(f"  - Revenue: ${product.gross_revenue}")
    print(f"  - Profit Margin: {product.profit_margin_percent}%")
    print(f"  - Stock Status: {product.stock_status}")
```

#### ABC Analysis (Pareto 80/20)
```python
abc_classification = analytics.get_abc_analysis(store_id=1)

# Classifies products into:
# A: Top 70% of revenue (focus products)
# B: Next 20% of revenue
# C: Bottom 10% of revenue

for product in abc_classification[:10]:
    print(f"{product['name']}: Class {product['abc_class']} "
          f"({product['cumulative_percent']}% cumulative)")
```

#### Top Products by Metric
```python
# Top 10 by revenue
top_revenue = analytics.get_top_products(
    store_id=1,
    metric=MetricType.REVENUE,
    limit=10
)

# Top 10 by profit
top_profit = analytics.get_top_products(
    store_id=1,
    metric=MetricType.PROFIT,
    limit=10
)

# Top 10 by quantity sold
top_quantity = analytics.get_top_products(
    store_id=1,
    metric=MetricType.QUANTITY,
    limit=10
)
```

### 3. Customer Analytics

#### Customer Lifetime Value & Segmentation
```python
customers = analytics.get_customer_analytics(store_id=1)

for customer in customers:
    print(f"{customer.client_name}:")
    print(f"  - Lifetime Value: ${customer.lifetime_value}")
    print(f"  - Status: {customer.customer_status}")  # Active/At Risk/Churned
    print(f"  - Loyalty Tier: {customer.loyalty_tier}")
    print(f"  - Points: {customer.current_points}")
```

#### Customer Cohort Analysis (Retention)
```python
cohorts = analytics.get_customer_cohort_analysis(
    store_id=1,
    months_back=6
)

for cohort in cohorts:
    print(f"Cohort: {cohort['cohort_month']}")
    print(f"  Initial Customers: {cohort['initial_customers']}")
    print(f"  Retention Rates: {cohort['retention_rates']}")
```

#### Top Customers
```python
top_customers = analytics.get_top_customers(
    store_id=1,
    limit=10,
    days_back=90  # Last 90 days
)
```

### 4. Inventory Analytics

#### Inventory Health Dashboard
```python
inventory = analytics.get_inventory_health(store_id=1)

for item in inventory:
    print(f"{item.product_name}:")
    print(f"  - Current Stock: {item.current_stock}")
    print(f"  - Status: {item.stock_status}")
    print(f"  - Expiry: {item.expiry_status}")
```

#### Low Stock Alerts
```python
low_stock = analytics.get_low_stock_products(store_id=1)

# Returns products that need immediate restocking
# Sorted by urgency (Out of Stock first, then Low Stock)
```

#### Slow-Moving Inventory
```python
slow_movers = analytics.get_slow_moving_inventory(
    store_id=1,
    days_threshold=60  # No sales in 60 days
)

# Identify dead stock for clearance promotions
```

### 5. Profit & Loss Analytics

#### P&L Summary
```python
profit_loss = analytics.get_profit_loss_summary(
    store_id=1,
    start_date=date.today() - timedelta(days=30),
    end_date=date.today(),
    period=PeriodType.DAILY
)

for day in profit_loss:
    print(f"Date: {day.period_date}")
    print(f"  Revenue: ${day.revenue}")
    print(f"  COGS: ${day.cost_of_goods_sold}")
    print(f"  Gross Profit: ${day.gross_profit} ({day.gross_margin_percent}%)")
    print(f"  Expenses: ${day.operating_expenses}")
    print(f"  Net Profit: ${day.net_profit} ({day.net_margin_percent}%)")
```

#### Days Sales of Inventory (DSI)
```python
dsi = analytics.calculate_days_sales_inventory(
    store_id=1,
    product_id=123,
    period_days=30
)

print(f"DSI: {dsi} days")
# Lower DSI = faster inventory turnover
# Higher DSI = potential overstocking
```

### 6. Cash Flow Analytics

#### Detailed Cash Flow
```python
cash_flows = analytics.get_cash_flow_analysis(
    store_id=1,
    start_date=date.today() - timedelta(days=30),
    end_date=date.today()
)

for flow in cash_flows:
    print(f"{flow.flow_date}: {flow.transaction_type}")
    print(f"  In: ${flow.amount_in}, Out: ${flow.amount_out}")
    print(f"  Net: ${flow.net_flow} ({flow.payment_method})")
```

#### Cash Flow Summary
```python
summary = analytics.get_cash_flow_summary(
    store_id=1,
    start_date=date.today() - timedelta(days=30),
    end_date=date.today()
)

print(f"Total Inflow: ${summary['summary']['total_inflow']}")
print(f"Total Outflow: ${summary['summary']['total_outflow']}")
print(f"Net Cash Flow: ${summary['summary']['net_cash_flow']}")
print(f"By Payment Method: {summary['by_payment_method']}")
```

### 7. Executive Dashboard

```python
dashboard = analytics.get_executive_dashboard(store_id=1)

print(f"As of: {dashboard['as_of_date']}")
print(f"\nToday:")
print(f"  Transactions: {dashboard['today']['transactions']}")
print(f"  Revenue: ${dashboard['today']['revenue']}")
print(f"  Gross Profit: ${dashboard['today']['gross_profit']}")
print(f"  New Customers: {dashboard['today']['new_customers']}")

print(f"\nMonth-to-Date:")
print(f"  Transactions: {dashboard['month_to_date']['transactions']}")
print(f"  Revenue: ${dashboard['month_to_date']['revenue']}")

print(f"\nAlerts:")
print(f"  Low Stock Products: {dashboard['alerts']['low_stock_products']}")

print(f"\nQuick Ratios:")
print(f"  Avg Ticket: ${dashboard['quick_ratios']['avg_ticket_today']}")
print(f"  Profit Margin: {dashboard['quick_ratios']['profit_margin_today']}%")
```

## Database Views Reference

### Core Views

| View Name | Purpose | Key Metrics |
|-----------|---------|-------------|
| `v_daily_sales_summary` | Daily sales performance | Revenue, transactions, avg ticket, payment breakdown |
| `v_product_performance` | Product-level analytics | Sales qty, revenue, COGS, profit margin |
| `v_customer_analytics` | Customer insights | CLV, purchase frequency, status, loyalty |
| `v_inventory_health` | Stock monitoring | Stock levels, status, expiry tracking |
| `v_profit_loss_summary` | P&L reporting | Revenue, COGS, expenses, net profit |
| `v_cash_flow_analysis` | Cash movement | Inflows, outflows by type/method |

### Materialized Views

| View Name | Refresh Schedule | Purpose |
|-----------|-----------------|---------|
| `mv_monthly_store_performance` | Daily at 2 AM | Monthly aggregated store metrics |
| `mv_category_performance` | Daily at 2:15 AM | Category-level performance trends |

**Refresh materialized views:**
```python
analytics.refresh_materialized_views()
```

Or via SQL:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_store_performance;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_category_performance;
```

## Analytical Functions

### 1. `fn_predict_clv()` - Customer Lifetime Value Prediction

```sql
SELECT fn_predict_clv(
    p_client_id := 123,
    p_avg_purchase_value := 50.00,
    p_purchase_frequency := 4.0,  -- purchases per month
    p_customer_lifespan_months := 24
);
-- Returns predicted CLV
```

### 2. `fn_calculate_dsi()` - Days Sales of Inventory

```sql
SELECT fn_calculate_dsi(
    p_store_id := 1,
    p_product_id := 456,
    p_period_days := 30
);
-- Returns DSI (days to sell current inventory)
```

### 3. `fn_get_top_products()` - Top N Products

```sql
SELECT * FROM fn_get_top_products(
    p_store_id := 1,
    p_metric := 'profit',  -- 'revenue', 'profit', 'quantity'
    p_limit := 10,
    p_start_date := '2024-01-01',
    p_end_date := '2024-01-31'
);
```

## Pre-Built Report Queries

See `DATABASE_ANALYTICS_MODULE.sql` Section 7 for ready-to-use queries:

1. **Executive Dashboard Summary** - Today's key metrics
2. **Weekly Performance Comparison** - This week vs last week
3. **Top 10 Customers** - By revenue (last 90 days)
4. **Slow Moving Inventory** - Dead stock identification

## Performance Optimization

### Indexes Created

The module automatically creates 20+ indexes for optimal query performance:

**Sales Indexes:**
- `idx_sales_store_date` - Store + date filtering
- `idx_sales_customer_date` - Customer analytics
- `idx_sales_payment_method` - Payment analysis
- `idx_sales_analytics_composite` - Multi-column composite

**Inventory Indexes:**
- `idx_inventory_store_product` - Stock lookups
- `idx_stock_movements_product_date` - Movement history

**Customer Indexes:**
- `idx_clients_tier` - Tier-based segmentation
- `idx_client_transactions_client_date` - Transaction history

### Query Performance Tips

1. **Use date ranges**: Always filter by date to leverage indexes
2. **Limit results**: Use `LIMIT` for large datasets
3. **Materialized views**: Use for heavy aggregations
4. **Off-peak refresh**: Schedule MV refreshes during low-traffic hours

## API Integration Example (FastAPI)

```python
from fastapi import FastAPI, Depends, Query
from datetime import date
from analytics_service import AnalyticsService, MetricType, PeriodType

app = FastAPI()

def get_analytics_service():
    db_session = get_db()  # Your DB dependency
    return AnalyticsService(db_session)

@app.get("/api/analytics/dashboard/{store_id}")
async def get_dashboard(
    store_id: int,
    analytics: AnalyticsService = Depends(get_analytics_service)
):
    return analytics.get_executive_dashboard(store_id)

@app.get("/api/analytics/sales/trends")
async def get_sales_trends(
    store_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    period: str = Query("daily"),
    analytics: AnalyticsService = Depends(get_analytics_service)
):
    period_type = PeriodType(period)
    return analytics.get_sales_trend_analysis(
        store_id, start_date, end_date, period_type
    )

@app.get("/api/analytics/products/top")
async def get_top_products(
    store_id: int,
    metric: str = Query("revenue"),
    limit: int = Query(10),
    analytics: AnalyticsService = Depends(get_analytics_service)
):
    metric_type = MetricType(metric)
    return analytics.get_top_products(store_id, metric_type, limit)

@app.get("/api/analytics/inventory/low-stock")
async def get_low_stock(
    store_id: int,
    analytics: AnalyticsService = Depends(get_analytics_service)
):
    return analytics.get_low_stock_products(store_id)
```

## Mobile Integration (Flutter)

```dart
// Fetch executive dashboard
Future<Dashboard> fetchDashboard(int storeId) async {
  final response = await http.get(
    Uri.parse('/api/analytics/dashboard/$storeId')
  );
  return Dashboard.fromJson(json.decode(response.body));
}

// Display in UI
class AnalyticsDashboard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Dashboard>(
      future: fetchDashboard(storeId),
      builder: (context, snapshot) {
        if (!snapshot.hasData) return CircularProgressIndicator();
        
        final dashboard = snapshot.data!;
        return Column(
          children: [
            MetricCard(
              title: "Today's Revenue",
              value: formatCurrency(dashboard.today.revenue),
              icon: Icons.attach_money
            ),
            MetricCard(
              title: "Transactions",
              value: dashboard.today.transactions.toString(),
              icon: Icons.receipt
            ),
            // Add more widgets...
          ],
        );
      },
    );
  }
}
```

## Scheduled Reports

Set up automated report generation using Celery or pg_cron:

### Using pg_cron

```sql
-- Enable pg_cron extension
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Daily executive summary at 8 AM
SELECT cron.schedule(
    'daily-executive-report',
    '0 8 * * *',
    $$INSERT INTO report_queue (report_type, store_id, created_at)
      SELECT 'executive_summary', id, NOW() FROM stores WHERE is_active = true$$
);

-- Weekly performance every Monday at 9 AM
SELECT cron.schedule(
    'weekly-performance-report',
    '0 9 * * 1',
    $$INSERT INTO report_queue (report_type, store_id, created_at)
      SELECT 'weekly_performance', id, NOW() FROM stores WHERE is_active = true$$
);
```

### Using Celery (Python)

```python
from celery import Celery
from datetime import date, timedelta

celery_app = Celery('analytics', broker='redis://localhost:6379')

@celery_app.task
def generate_daily_reports(store_id: int):
    analytics = AnalyticsService(get_db_session())
    
    dashboard = analytics.get_executive_dashboard(store_id)
    
    # Send via email, WhatsApp, or in-app notification
    send_report_notification(
        store_id=store_id,
        report_type='daily_executive',
        data=dashboard
    )

# Schedule daily at 8 AM
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'daily-reports': {
        'task': 'analytics.tasks.generate_daily_reports',
        'schedule': crontab(hour=8, minute=0),
        'args': (1,)  # store_id
    }
}
```

## Best Practices

1. **Query Optimization**
   - Always filter by `store_id` and date range
   - Use materialized views for heavy aggregations
   - Implement pagination for large result sets

2. **Data Freshness**
   - Refresh materialized views during off-peak hours
   - Cache frequently accessed dashboards (5-15 min TTL)
   - Use real-time queries only for critical metrics

3. **Security**
   - Validate store_id to prevent cross-store data access
   - Implement role-based access to sensitive metrics
   - Audit log all analytical queries

4. **Scalability**
   - Add read replicas for analytical queries
   - Partition large tables by date (sales, transactions)
   - Archive old data (>2 years) to cold storage

## Troubleshooting

### Slow Queries

1. Check if indexes are being used:
```sql
EXPLAIN ANALYZE SELECT * FROM v_daily_sales_summary 
WHERE store_id = 1 AND sale_day >= '2024-01-01';
```

2. Refresh materialized views if stale:
```python
analytics.refresh_materialized_views()
```

3. Increase work_mem for complex aggregations:
```sql
SET work_mem = '64MB';
```

### Missing Data

1. Verify soft-delete filters (`deleted_at IS NULL`)
2. Check timezone consistency in date filters
3. Ensure sync layer has pushed latest data

## Support & Extensions

For custom analytics requirements:
- Add new views in `DATABASE_ANALYTICS_MODULE.sql`
- Extend `AnalyticsService` class with new methods
- Create specialized materialized views for heavy computations
- Integrate with BI tools (Metabase, Superset) via direct DB connection

---

**Version**: 1.0  
**Last Updated**: 2024  
**Compatible With**: PostgreSQL 12+, Python 3.8+, SQLAlchemy 1.4+
