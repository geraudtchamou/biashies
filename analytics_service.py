"""
AFRICAN POS ANALYTICS SERVICE LAYER
Comprehensive analytics module for business intelligence
Supports: Sales, Inventory, Profit, Customer, and Cash Flow Analysis
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, asdict
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics available for analysis"""
    REVENUE = "revenue"
    PROFIT = "profit"
    QUANTITY = "quantity"
    TRANSACTIONS = "transactions"
    CUSTOMERS = "customers"


class PeriodType(str, Enum):
    """Time period types for reporting"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass
class SalesMetrics:
    """Sales performance metrics"""
    total_transactions: int
    gross_revenue: Decimal
    net_revenue: Decimal
    total_discounts: Decimal
    total_tax: Decimal
    average_ticket_size: Decimal
    unique_customers: int
    completed_sales: int
    voided_sales: int
    refunded_sales: int
    refund_rate: Decimal


@dataclass
class ProductMetrics:
    """Product performance metrics"""
    product_id: int
    product_name: str
    sku: str
    total_quantity_sold: int
    gross_revenue: Decimal
    total_cogs: Decimal
    gross_profit: Decimal
    profit_margin_percent: Decimal
    number_of_sales: int
    stock_status: str


@dataclass
class CustomerMetrics:
    """Customer analytics metrics"""
    client_id: int
    client_name: str
    lifetime_value: Decimal
    total_purchases: int
    average_purchase_value: Decimal
    days_since_last_purchase: int
    customer_status: str  # Active, At Risk, Churned
    loyalty_tier: str
    current_points: int


@dataclass
class ProfitLossMetrics:
    """Profit & Loss metrics"""
    period_date: date
    revenue: Decimal
    cost_of_goods_sold: Decimal
    gross_profit: Decimal
    gross_margin_percent: Decimal
    operating_expenses: Decimal
    net_profit: Decimal
    net_margin_percent: Decimal


@dataclass
class InventoryHealth:
    """Inventory health metrics"""
    product_id: int
    product_name: str
    current_stock: int
    reorder_level: int
    stock_status: str  # Out of Stock, Low Stock, Healthy, Overstocked
    expiry_status: str  # Valid, Expiring Soon, Expired
    total_sold: int
    total_purchased: int


@dataclass
class CashFlowEntry:
    """Cash flow transaction entry"""
    flow_date: date
    transaction_type: str  # sale, expense, purchase
    amount_in: Decimal
    amount_out: Decimal
    net_flow: Decimal
    payment_method: str
    description: str


class AnalyticsService:
    """
    Main analytics service for African POS system
    Provides comprehensive business intelligence across all modules
    """
    
    def __init__(self, db_session):
        """
        Initialize analytics service
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
    
    # =========================================================================
    # SALES ANALYTICS
    # =========================================================================
    
    def get_daily_sales_summary(
        self,
        store_id: int,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get daily sales summary for a date range
        
        Returns:
            List of daily sales metrics including revenue, transactions, averages
        """
        query = """
        SELECT * FROM v_daily_sales_summary
        WHERE store_id = :store_id
          AND sale_day BETWEEN :start_date AND :end_date
        ORDER BY sale_day
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'start_date': start_date,
            'end_date': end_date
        })
        
        return [dict(row) for row in result.fetchall()]
    
    def get_sales_trend_analysis(
        self,
        store_id: int,
        start_date: date,
        end_date: date,
        period: PeriodType = PeriodType.DAILY
    ) -> Dict[str, Any]:
        """
        Analyze sales trends with growth calculations
        
        Returns:
            Trend data with period-over-period growth percentages
        """
        period_trunc = {
            PeriodType.DAILY: 'day',
            PeriodType.WEEKLY: 'week',
            PeriodType.MONTHLY: 'month'
        }[period]
        
        query = f"""
        WITH period_sales AS (
            SELECT 
                DATE_TRUNC(:period_type, sale_date) AS period,
                COUNT(*) AS transactions,
                SUM(total_amount - discount_amount) AS revenue,
                SUM(quantity * (selling_price - cost_price)) AS profit
            FROM sales s
            JOIN sale_items si ON s.id = si.sale_id
            WHERE s.store_id = :store_id
              AND s.sale_date BETWEEN :start_date AND :end_date
              AND s.status = 'completed'
              AND s.deleted_at IS NULL
            GROUP BY DATE_TRUNC(:period_type, sale_date)
        )
        SELECT 
            period,
            transactions,
            revenue,
            profit,
            LAG(revenue, 1) OVER (ORDER BY period) AS prev_period_revenue,
            ROUND(
                ((revenue - LAG(revenue, 1) OVER (ORDER BY period)) / 
                NULLIF(LAG(revenue, 1) OVER (ORDER BY period), 0)) * 100, 2
            ) AS growth_percent
        FROM period_sales
        ORDER BY period
        """
        
        result = self.db.execute(query, {
            'period_type': period_trunc,
            'store_id': store_id,
            'start_date': start_date,
            'end_date': end_date
        })
        
        trends = []
        for row in result.fetchall():
            trends.append({
                'period': row.period,
                'transactions': row.transactions,
                'revenue': float(row.revenue),
                'profit': float(row.profit),
                'previous_revenue': float(row.prev_period_revenue) if row.prev_period_revenue else None,
                'growth_percent': float(row.growth_percent) if row.growth_percent else None
            })
        
        # Calculate overall summary
        total_revenue = sum(t['revenue'] for t in trends)
        avg_growth = sum(t['growth_percent'] for t in trends if t['growth_percent']) / len([t for t in trends if t['growth_percent']]) if trends else 0
        
        return {
            'trends': trends,
            'summary': {
                'total_revenue': float(total_revenue),
                'total_transactions': sum(t['transactions'] for t in trends),
                'average_growth_percent': float(avg_growth) if avg_growth else 0,
                'best_period': max(trends, key=lambda x: x['revenue'])['period'] if trends else None,
                'worst_period': min(trends, key=lambda x: x['revenue'])['period'] if trends else None
            }
        }
    
    def get_hourly_sales_pattern(
        self,
        store_id: int,
        days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Analyze hourly sales patterns to identify peak hours
        
        Returns:
            Hourly breakdown with transaction counts and revenue
        """
        query = """
        SELECT 
            EXTRACT(HOUR FROM sale_time) AS hour_of_day,
            COUNT(*) AS transaction_count,
            SUM(total_amount) AS total_revenue,
            AVG(total_amount) AS average_ticket,
            ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 2) AS percent_of_sales
        FROM sales
        WHERE store_id = :store_id
          AND status = 'completed'
          AND deleted_at IS NULL
          AND sale_date >= CURRENT_DATE - INTERVAL ':days days'
        GROUP BY EXTRACT(HOUR FROM sale_time)
        ORDER BY hour_of_day
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'days': days_back
        })
        
        return [dict(row) for row in result.fetchall()]
    
    # =========================================================================
    # PRODUCT ANALYTICS
    # =========================================================================
    
    def get_product_performance(
        self,
        store_id: int,
        category_id: Optional[int] = None,
        limit: int = 50
    ) -> List[ProductMetrics]:
        """
        Get product performance metrics
        
        Returns:
            List of products with sales, profit, and margin data
        """
        query = """
        SELECT * FROM v_product_performance
        WHERE store_id = :store_id
        """
        
        params = {'store_id': store_id, 'limit': limit}
        
        if category_id:
            query += " AND category_id = :category_id"
            params['category_id'] = category_id
        
        query += " ORDER BY gross_profit DESC LIMIT :limit"
        
        result = self.db.execute(query, params)
        
        return [
            ProductMetrics(
                product_id=row.product_id,
                product_name=row.product_name,
                sku=row.sku,
                total_quantity_sold=row.total_quantity_sold or 0,
                gross_revenue=row.gross_revenue or Decimal('0'),
                total_cogs=row.total_cogs or Decimal('0'),
                gross_profit=row.gross_profit or Decimal('0'),
                profit_margin_percent=row.profit_margin_percent or Decimal('0'),
                number_of_sales=row.number_of_sales or 0,
                stock_status=self._get_stock_status(row.current_stock, row.reorder_level)
            )
            for row in result.fetchall()
        ]
    
    def get_abc_analysis(self, store_id: int) -> List[Dict[str, Any]]:
        """
        Perform ABC analysis on products (Pareto 80/20 rule)
        
        Classifies products into:
        - A: Top 70% of revenue
        - B: Next 20% of revenue
        - C: Bottom 10% of revenue
        
        Returns:
            Products classified by ABC category
        """
        query = """
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
            END AS abc_class,
            revenue_rank
        FROM cumulative
        ORDER BY revenue_rank
        """
        
        result = self.db.execute(query, {'store_id': store_id})
        
        return [dict(row) for row in result.fetchall()]
    
    def get_top_products(
        self,
        store_id: int,
        metric: MetricType = MetricType.REVENUE,
        limit: int = 10,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get top N products by specified metric
        
        Args:
            metric: revenue, profit, or quantity
            limit: Number of top products to return
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
        if end_date is None:
            end_date = date.today()
        
        query = """
        SELECT * FROM fn_get_top_products(
            :store_id, :metric, :limit, :start_date, :end_date
        )
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'metric': metric.value,
            'limit': limit,
            'start_date': start_date,
            'end_date': end_date
        })
        
        return [dict(row) for row in result.fetchall()]
    
    # =========================================================================
    # CUSTOMER ANALYTICS
    # =========================================================================
    
    def get_customer_analytics(
        self,
        store_id: int,
        customer_status: Optional[str] = None
    ) -> List[CustomerMetrics]:
        """
        Get comprehensive customer analytics
        
        Returns:
            Customer metrics including CLV, purchase frequency, status
        """
        query = """
        SELECT * FROM v_customer_analytics
        WHERE store_id = :store_id
        """
        
        params = {'store_id': store_id}
        
        if customer_status:
            query += """
            AND CASE 
                WHEN CURRENT_DATE - MAX(s.sale_date) <= 30 THEN 'Active'
                WHEN CURRENT_DATE - MAX(s.sale_date) <= 90 THEN 'At Risk'
                ELSE 'Churned'
            END = :status
            """
            params['status'] = customer_status
        
        result = self.db.execute(query, params)
        
        return [
            CustomerMetrics(
                client_id=row.client_id,
                client_name=row.client_name,
                lifetime_value=row.lifetime_value or Decimal('0'),
                total_purchases=row.total_purchases or 0,
                average_purchase_value=row.average_purchase_value or Decimal('0'),
                days_since_last_purchase=row.days_since_last_purchase or 0,
                customer_status=row.customer_status,
                loyalty_tier=row.tier_name or 'None',
                current_points=row.current_points or 0
            )
            for row in result.fetchall()
        ]
    
    def get_customer_cohort_analysis(
        self,
        store_id: int,
        months_back: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Perform cohort analysis to track customer retention
        
        Returns:
            Retention rates by cohort month
        """
        query = """
        WITH customer_cohorts AS (
            SELECT 
                s.client_id,
                DATE_TRUNC('month', MIN(s.sale_date)) AS cohort_month
            FROM sales s
            JOIN clients cl ON s.client_id = cl.id
            WHERE cl.store_id = :store_id
              AND s.status = 'completed'
              AND s.deleted_at IS NULL
              AND cl.deleted_at IS NULL
              AND s.sale_date >= CURRENT_DATE - INTERVAL ':months months'
            GROUP BY s.client_id
        ),
        customer_activity AS (
            SELECT 
                s.client_id,
                cc.cohort_month,
                DATE_TRUNC('month', s.sale_date) AS activity_month,
                EXTRACT(MONTH FROM AGE(DATE_TRUNC('month', s.sale_date), cc.cohort_month)) AS months_since_first
            FROM sales s
            JOIN customer_cohorts cc ON s.client_id = cc.client_id
            WHERE s.status = 'completed' AND s.deleted_at IS NULL
        )
        SELECT 
            cohort_month,
            months_since_first,
            COUNT(DISTINCT client_id) AS active_customers
        FROM customer_activity
        GROUP BY cohort_month, months_since_first
        ORDER BY cohort_month, months_since_first
        """
        
        result = self.db.execute(query, {'store_id': store_id, 'months': months_back})
        
        # Process into cohort matrix
        cohorts = {}
        for row in result.fetchall():
            cohort_month = row.cohort_month
            months_since = int(row.months_since_first)
            
            if cohort_month not in cohorts:
                cohorts[cohort_month] = {'initial': 0, 'retention': {}}
            
            if months_since == 0:
                cohorts[cohort_month]['initial'] = row.active_customers
            
            if cohorts[cohort_month]['initial'] > 0:
                retention_rate = (row.active_customers / cohorts[cohort_month]['initial']) * 100
                cohorts[cohort_month]['retention'][months_since] = round(retention_rate, 2)
        
        return [
            {
                'cohort_month': month,
                'initial_customers': data['initial'],
                'retention_rates': data['retention']
            }
            for month, data in cohorts.items()
        ]
    
    def get_top_customers(
        self,
        store_id: int,
        limit: int = 10,
        days_back: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Get top customers by revenue in specified period
        
        Returns:
            Top customers with spending metrics
        """
        query = """
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
        WHERE cl.store_id = :store_id
          AND s.sale_date >= CURRENT_DATE - INTERVAL ':days days'
          AND s.status = 'completed'
          AND s.deleted_at IS NULL
          AND cl.deleted_at IS NULL
        GROUP BY cl.id, cl.name, cl.phone
        ORDER BY total_spent DESC
        LIMIT :limit
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'days': days_back,
            'limit': limit
        })
        
        return [dict(row) for row in result.fetchall()]
    
    # =========================================================================
    # INVENTORY ANALYTICS
    # =========================================================================
    
    def get_inventory_health(
        self,
        store_id: int,
        include_expired: bool = True
    ) -> List[InventoryHealth]:
        """
        Get inventory health status for all products
        
        Returns:
            Products with stock levels, status, and expiry information
        """
        query = """
        SELECT * FROM v_inventory_health
        WHERE store_id = :store_id
        """
        
        if not include_expired:
            query += " AND expiry_status != 'Expired'"
        
        result = self.db.execute(query, {'store_id': store_id})
        
        return [
            InventoryHealth(
                product_id=row.product_id,
                product_name=row.product_name,
                current_stock=row.current_stock or 0,
                reorder_level=row.reorder_level or 0,
                stock_status=row.stock_status,
                expiry_status=row.expiry_status,
                total_sold=row.total_sold or 0,
                total_purchased=row.total_purchased or 0
            )
            for row in result.fetchall()
        ]
    
    def get_low_stock_products(
        self,
        store_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get products below reorder level
        
        Returns:
            Products needing restock with suggested quantities
        """
        query = """
        SELECT * FROM v_inventory_health
        WHERE store_id = :store_id
          AND stock_status IN ('Low Stock', 'Out of Stock')
        ORDER BY 
            CASE stock_status 
                WHEN 'Out of Stock' THEN 1 
                WHEN 'Low Stock' THEN 2 
            END
        """
        
        result = self.db.execute(query, {'store_id': store_id})
        
        return [dict(row) for row in result.fetchall()]
    
    def get_slow_moving_inventory(
        self,
        store_id: int,
        days_threshold: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Identify slow-moving or dead stock
        
        Returns:
            Products with no recent sales
        """
        query = """
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
        WHERE p.store_id = :store_id
          AND p.deleted_at IS NULL
        GROUP BY p.id, p.name, p.sku, p.store_id, il.quantity_on_hand, 
                 p.initial_stock, p.reorder_level
        HAVING MAX(s.sale_date) < CURRENT_DATE - INTERVAL ':days days' 
           OR MAX(s.sale_date) IS NULL
        ORDER BY days_since_last_sale DESC NULLS FIRST
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'days': days_threshold
        })
        
        return [dict(row) for row in result.fetchall()]
    
    # =========================================================================
    # PROFIT & LOSS ANALYTICS
    # =========================================================================
    
    def get_profit_loss_summary(
        self,
        store_id: int,
        start_date: date,
        end_date: date,
        period: PeriodType = PeriodType.DAILY
    ) -> List[ProfitLossMetrics]:
        """
        Get profit & loss summary for a period
        
        Returns:
            P&L metrics with revenue, COGS, expenses, and net profit
        """
        query = """
        SELECT * FROM v_profit_loss_summary
        WHERE store_id = :store_id
          AND period_date BETWEEN :start_date AND :end_date
        ORDER BY period_date
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'start_date': start_date,
            'end_date': end_date
        })
        
        return [
            ProfitLossMetrics(
                period_date=row.period_date,
                revenue=row.revenue or Decimal('0'),
                cost_of_goods_sold=row.cost_of_goods_sold or Decimal('0'),
                gross_profit=row.gross_profit or Decimal('0'),
                gross_margin_percent=row.gross_margin_percent or Decimal('0'),
                operating_expenses=row.operating_expenses or Decimal('0'),
                net_profit=row.net_profit or Decimal('0'),
                net_margin_percent=row.net_margin_percent or Decimal('0')
            )
            for row in result.fetchall()
        ]
    
    def calculate_days_sales_inventory(
        self,
        store_id: int,
        product_id: int,
        period_days: int = 30
    ) -> Optional[Decimal]:
        """
        Calculate Days Sales of Inventory (DSI) for a product
        
        DSI measures how many days it takes to sell current inventory
        
        Returns:
            DSI value (lower is better)
        """
        query = """
        SELECT fn_calculate_dsi(:store_id, :product_id, :period_days)
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'product_id': product_id,
            'period_days': period_days
        })
        
        dsi = result.scalar()
        return Decimal(str(dsi)) if dsi else None
    
    # =========================================================================
    # CASH FLOW ANALYTICS
    # =========================================================================
    
    def get_cash_flow_analysis(
        self,
        store_id: int,
        start_date: date,
        end_date: date
    ) -> List[CashFlowEntry]:
        """
        Get detailed cash flow analysis
        
        Returns:
            Cash inflows and outflows by day and type
        """
        query = """
        SELECT * FROM v_cash_flow_analysis
        WHERE store_id = :store_id
          AND flow_date BETWEEN :start_date AND :end_date
        ORDER BY flow_date, transaction_type
        """
        
        result = self.db.execute(query, {
            'store_id': store_id,
            'start_date': start_date,
            'end_date': end_date
        })
        
        return [
            CashFlowEntry(
                flow_date=row.flow_date,
                transaction_type=row.transaction_type,
                amount_in=row.amount_in or Decimal('0'),
                amount_out=row.amount_out or Decimal('0'),
                net_flow=row.net_flow or Decimal('0'),
                payment_method=row.payment_method,
                description=row.description
            )
            for row in result.fetchall()
        ]
    
    def get_cash_flow_summary(
        self,
        store_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Get summarized cash flow metrics
        
        Returns:
            Total inflows, outflows, net flow, and breakdown by type
        """
        cash_flows = self.get_cash_flow_analysis(store_id, start_date, end_date)
        
        total_in = sum(cf.amount_in for cf in cash_flows)
        total_out = sum(cf.amount_out for cf in cash_flows)
        net_flow = total_in - total_out
        
        # Breakdown by transaction type
        by_type = {}
        for cf in cash_flows:
            if cf.transaction_type not in by_type:
                by_type[cf.transaction_type] = {'in': Decimal('0'), 'out': Decimal('0')}
            by_type[cf.transaction_type]['in'] += cf.amount_in
            by_type[cf.transaction_type]['out'] += cf.amount_out
        
        # Breakdown by payment method
        by_method = {}
        for cf in cash_flows:
            if cf.payment_method not in by_method:
                by_method[cf.payment_method] = Decimal('0')
            by_method[cf.payment_method] += cf.net_flow
        
        return {
            'period': {
                'start': start_date,
                'end': end_date
            },
            'summary': {
                'total_inflow': float(total_in),
                'total_outflow': float(total_out),
                'net_cash_flow': float(net_flow)
            },
            'by_transaction_type': {
                k: {'in': float(v['in']), 'out': float(v['out']), 'net': float(v['in'] - v['out'])}
                for k, v in by_type.items()
            },
            'by_payment_method': {
                k: float(v) for k, v in by_method.items()
            }
        }
    
    # =========================================================================
    # EXECUTIVE DASHBOARD
    # =========================================================================
    
    def get_executive_dashboard(
        self,
        store_id: int,
        as_of_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive executive dashboard metrics
        
        Returns:
            Key metrics for quick business overview
        """
        if as_of_date is None:
            as_of_date = date.today()
        
        # Today's metrics
        today_start = as_of_date
        today_end = as_of_date + timedelta(days=1)
        
        # Month-to-date
        month_start = as_of_date.replace(day=1)
        
        # Query today's summary
        query_today = """
        SELECT 
            COUNT(*) AS transactions,
            COALESCE(SUM(total_amount - discount_amount), 0) AS revenue,
            COALESCE(SUM(si.quantity * (si.selling_price - si.cost_price)), 0) AS gross_profit
        FROM sales s
        JOIN sale_items si ON s.id = si.sale_id
        WHERE s.store_id = :store_id
          AND DATE(s.sale_date) = :today
          AND s.status = 'completed'
          AND s.deleted_at IS NULL
        """
        
        result_today = self.db.execute(query_today, {
            'store_id': store_id,
            'today': today_start
        }).fetchone()
        
        # Query MTD summary
        query_mtd = """
        SELECT 
            COUNT(*) AS transactions,
            COALESCE(SUM(total_amount - discount_amount), 0) AS revenue
        FROM sales
        WHERE store_id = :store_id
          AND sale_date >= :month_start
          AND sale_date < :month_end
          AND status = 'completed'
          AND deleted_at IS NULL
        """
        
        result_mtd = self.db.execute(query_mtd, {
            'store_id': store_id,
            'month_start': month_start,
            'month_end': as_of_date + timedelta(days=1)
        }).fetchone()
        
        # Low stock count
        low_stock_query = """
        SELECT COUNT(*) 
        FROM v_inventory_health
        WHERE store_id = :store_id
          AND stock_status IN ('Low Stock', 'Out of Stock')
        """
        
        low_stock_count = self.db.execute(low_stock_query, {
            'store_id': store_id
        }).scalar()
        
        # New customers today
        new_customers_query = """
        SELECT COUNT(*) 
        FROM clients
        WHERE store_id = :store_id
          AND DATE(created_at) = :today
          AND deleted_at IS NULL
        """
        
        new_customers = self.db.execute(new_customers_query, {
            'store_id': store_id,
            'today': today_start
        }).scalar()
        
        return {
            'as_of_date': as_of_date.isoformat(),
            'today': {
                'transactions': result_today.transactions or 0,
                'revenue': float(result_today.revenue or 0),
                'gross_profit': float(result_today.gross_profit or 0),
                'new_customers': new_customers or 0
            },
            'month_to_date': {
                'transactions': result_mtd.transactions or 0,
                'revenue': float(result_mtd.revenue or 0)
            },
            'alerts': {
                'low_stock_products': low_stock_count or 0
            },
            'quick_ratios': {
                'avg_ticket_today': float((result_today.revenue / result_today.transactions) if result_today.transactions > 0 else 0),
                'profit_margin_today': float(((result_today.gross_profit / result_today.revenue) * 100) if result_today.revenue > 0 else 0)
            }
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_stock_status(self, current_stock: int, reorder_level: int) -> str:
        """Determine stock status based on quantity and reorder level"""
        if current_stock <= 0:
            return "Out of Stock"
        elif current_stock <= reorder_level:
            return "Low Stock"
        elif current_stock > reorder_level * 2:
            return "Overstocked"
        else:
            return "Healthy"
    
    def refresh_materialized_views(self):
        """Refresh all materialized views for updated analytics"""
        views = [
            'mv_monthly_store_performance',
            'mv_category_performance'
        ]
        
        for view in views:
            try:
                self.db.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                logger.info(f"Refreshed materialized view: {view}")
            except Exception as e:
                logger.error(f"Failed to refresh {view}: {e}")


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    # Example usage (would integrate with your actual DB session)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # engine = create_engine("postgresql://user:pass@localhost/african_pos")
    # Session = sessionmaker(bind=engine)
    # db_session = Session()
    
    # analytics = AnalyticsService(db_session)
    
    # # Get executive dashboard
    # dashboard = analytics.get_executive_dashboard(store_id=1)
    # print(f"Today's Revenue: ${dashboard['today']['revenue']}")
    
    # # Get product performance
    # products = analytics.get_product_performance(store_id=1, limit=20)
    # for p in products[:5]:
    #     print(f"{p.product_name}: Profit Margin {p.profit_margin_percent}%")
    
    # # Get cash flow summary
    # from datetime import date, timedelta
    # cash_flow = analytics.get_cash_flow_summary(
    #     store_id=1,
    #     start_date=date.today() - timedelta(days=30),
    #     end_date=date.today()
    # )
    # print(f"Net Cash Flow: ${cash_flow['summary']['net_cash_flow']}")
    
    pass
