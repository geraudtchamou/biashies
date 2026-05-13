"""
Profit Service - Computes daily, weekly, and monthly profit metrics
for the African POS system.

This service handles:
- Gross profit calculation per sale
- Net profit computation (Revenue - COGS - Expenses)
- Profit margin analysis
- Period-based reporting (daily/weekly/monthly)
- Store-level and product-level profit breakdowns
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_

from models.sale import Sale, SaleItem
from models.expense import Expense
from models.purchase import Purchase, PurchaseItem
from models.store import Store


class ReportPeriod(str, Enum):
    """Report period types."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


@dataclass
class ProfitMetrics:
    """Container for profit metrics."""
    # Revenue
    total_revenue: Decimal = Decimal('0')
    total_sales_count: int = 0
    average_transaction_value: Decimal = Decimal('0')
    
    # Cost of Goods Sold
    total_cogs: Decimal = Decimal('0')
    
    # Gross Profit
    gross_profit: Decimal = Decimal('0')
    gross_margin_percent: Decimal = Decimal('0')
    
    # Expenses
    total_expenses: Decimal = Decimal('0')
    expenses_by_category: Dict[str, Decimal] = field(default_factory=dict)
    
    # Net Profit
    net_profit: Decimal = Decimal('0')
    net_margin_percent: Decimal = Decimal('0')
    
    # Additional metrics
    tax_collected: Decimal = Decimal('0')
    discounts_given: Decimal = Decimal('0')
    returns_amount: Decimal = Decimal('0')
    
    # Period info
    period_start: datetime = None
    period_end: datetime = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "period": {
                "start": self.period_start.isoformat() if self.period_start else None,
                "end": self.period_end.isoformat() if self.period_end else None,
            },
            "revenue": {
                "total_revenue": float(self.total_revenue),
                "total_sales_count": self.total_sales_count,
                "average_transaction_value": float(self.average_transaction_value),
                "tax_collected": float(self.tax_collected),
                "discounts_given": float(self.discounts_given),
                "returns_amount": float(self.returns_amount),
            },
            "cogs": {
                "total_cogs": float(self.total_cogs),
            },
            "gross_profit": {
                "gross_profit": float(self.gross_profit),
                "gross_margin_percent": float(self.gross_margin_percent),
            },
            "expenses": {
                "total_expenses": float(self.total_expenses),
                "by_category": {k: float(v) for k, v in self.expenses_by_category.items()},
            },
            "net_profit": {
                "net_profit": float(self.net_profit),
                "net_margin_percent": float(self.net_margin_percent),
            }
        }


@dataclass
class ProductProfitItem:
    """Profit data for a single product."""
    product_id: str
    product_name: str
    variant_id: Optional[str] = None
    quantity_sold: int = 0
    revenue: Decimal = Decimal('0')
    cogs: Decimal = Decimal('0')
    gross_profit: Decimal = Decimal('0')
    profit_margin_percent: Decimal = Decimal('0')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "variant_id": self.variant_id,
            "quantity_sold": self.quantity_sold,
            "revenue": float(self.revenue),
            "cogs": float(self.cogs),
            "gross_profit": float(self.gross_profit),
            "profit_margin_percent": float(self.profit_margin_percent),
        }


class ProfitService:
    """
    Service for computing profit metrics and generating profit reports.
    
    Handles all profit-related calculations including:
    - Gross profit per sale/product
    - Net profit after expenses
    - Profit margins and trends
    - Period-based comparisons
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize the profit service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
    
    def get_period_bounds(
        self, 
        period: ReportPeriod, 
        reference_date: Optional[datetime] = None,
        custom_start: Optional[datetime] = None,
        custom_end: Optional[datetime] = None
    ) -> Tuple[datetime, datetime]:
        """
        Get start and end datetime for a report period.
        
        Args:
            period: Type of period (daily, weekly, monthly, custom)
            reference_date: Reference date for calculating period bounds
            custom_start: Custom start date (for CUSTOM period)
            custom_end: Custom end date (for CUSTOM period)
            
        Returns:
            Tuple of (start_datetime, end_datetime)
        """
        if reference_date is None:
            reference_date = datetime.utcnow()
        
        if period == ReportPeriod.DAILY:
            start = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        
        elif period == ReportPeriod.WEEKLY:
            # Week starts on Monday
            days_since_monday = reference_date.weekday()
            start = (reference_date - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
        
        elif period == ReportPeriod.MONTHLY:
            start = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # First day of next month
            if reference_date.month == 12:
                end = start.replace(year=reference_date.year + 1, month=1)
            else:
                end = start.replace(month=reference_date.month + 1)
        
        elif period == ReportPeriod.CUSTOM:
            if not custom_start or not custom_end:
                raise ValueError("Custom period requires custom_start and custom_end")
            start = custom_start
            end = custom_end + timedelta(days=1)  # Include the end date
        
        else:
            raise ValueError(f"Invalid period: {period}")
        
        return start, end
    
    def calculate_gross_profit_for_sale(
        self, 
        sale_id: str
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate gross profit for a specific sale.
        
        Formula: Gross Profit = Selling Price - COGS
        
        Args:
            sale_id: Sale identifier
            
        Returns:
            Tuple of (gross_profit, margin_percent)
        """
        sale_items = self.db.query(SaleItem).filter(
            SaleItem.sale_id == sale_id
        ).all()
        
        total_revenue = Decimal('0')
        total_cogs = Decimal('0')
        
        for item in sale_items:
            revenue = item.total  # Already includes tax/discount adjustments
            cogs = item.total_cost or Decimal('0')
            
            total_revenue += revenue
            total_cogs += cogs
        
        gross_profit = total_revenue - total_cogs
        margin_percent = Decimal('0')
        
        if total_revenue > 0:
            margin_percent = (gross_profit / total_revenue) * 100
        
        return gross_profit, margin_percent
    
    def compute_period_profit(
        self,
        tenant_id: str,
        period: ReportPeriod = ReportPeriod.DAILY,
        reference_date: Optional[datetime] = None,
        store_id: Optional[str] = None,
        custom_start: Optional[datetime] = None,
        custom_end: Optional[datetime] = None
    ) -> ProfitMetrics:
        """
        Compute comprehensive profit metrics for a period.
        
        This calculates:
        - Total revenue from sales
        - COGS from sale items
        - Gross profit
        - Operating expenses
        - Net profit
        
        Args:
            tenant_id: Tenant identifier
            period: Report period type
            reference_date: Reference date for period calculation
            store_id: Optional store filter
            custom_start: Custom period start (for CUSTOM period)
            custom_end: Custom period end (for CUSTOM period)
            
        Returns:
            ProfitMetrics with complete profit analysis
        """
        # Get period bounds
        period_start, period_end = self.get_period_bounds(
            period, reference_date, custom_start, custom_end
        )
        
        metrics = ProfitMetrics(
            period_start=period_start,
            period_end=period_end
        )
        
        # Build base query filters
        sale_filters = [
            Sale.tenant_id == tenant_id,
            Sale.sale_date >= period_start,
            Sale.sale_date < period_end,
            Sale.status.notin_(['voided', 'cancelled'])
        ]
        
        expense_filters = [
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= period_start.date(),
            Expense.expense_date <= period_end.date()
        ]
        
        if store_id:
            sale_filters.append(Sale.store_id == store_id)
            expense_filters.append(Expense.store_id == store_id)
        
        # ===== REVENUE CALCULATION =====
        sales_query = self.db.query(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_amount), 0),
            func.coalesce(func.sum(Sale.tax_total), 0),
            func.coalesce(func.sum(Sale.discount_total), 0)
        ).filter(and_(*sale_filters))
        
        sales_result = sales_query.first()
        metrics.total_sales_count = sales_result[0] or 0
        metrics.total_revenue = Decimal(str(sales_result[1] or 0))
        metrics.tax_collected = Decimal(str(sales_result[2] or 0))
        metrics.discounts_given = Decimal(str(sales_result[3] or 0))
        
        if metrics.total_sales_count > 0:
            metrics.average_transaction_value = (
                metrics.total_revenue / metrics.total_sales_count
            )
        
        # ===== COGS CALCULATION =====
        # Join sales with sale items to get COGS
        cogs_query = self.db.query(
            func.coalesce(func.sum(SaleItem.total_cost), 0)
        ).join(
            Sale, SaleItem.sale_id == Sale.id
        ).filter(and_(*sale_filters))
        
        cogs_result = cogs_query.first()
        metrics.total_cogs = Decimal(str(cogs_result[0] or 0))
        
        # ===== GROSS PROFIT =====
        metrics.gross_profit = metrics.total_revenue - metrics.total_cogs
        
        if metrics.total_revenue > 0:
            metrics.gross_margin_percent = (
                metrics.gross_profit / metrics.total_revenue
            ) * 100
        
        # ===== EXPENSES CALCULATION =====
        expenses_query = self.db.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.total_amount), 0)
        ).filter(and_(*expense_filters)).group_by(Expense.category_id)
        
        expenses_result = expenses_query.all()
        
        total_expenses = Decimal('0')
        for category_id, amount in expenses_result:
            expense_amount = Decimal(str(amount))
            total_expenses += expense_amount
            
            # Get category name
            if category_id:
                from models.expense import ExpenseCategory
                category = self.db.query(ExpenseCategory).filter(
                    ExpenseCategory.id == category_id
                ).first()
                if category:
                    metrics.expenses_by_category[category.name] = expense_amount
            else:
                metrics.expenses_by_category['Uncategorized'] = expense_amount
        
        metrics.total_expenses = total_expenses
        
        # ===== NET PROFIT =====
        metrics.net_profit = metrics.gross_profit - metrics.total_expenses
        
        if metrics.total_revenue > 0:
            metrics.net_margin_percent = (
                metrics.net_profit / metrics.total_revenue
            ) * 100
        
        # ===== RETURNS =====
        from models.sale import SaleReturn
        returns_query = self.db.query(
            func.coalesce(func.sum(SaleReturn.total_amount), 0)
        ).filter(
            SaleReturn.tenant_id == tenant_id,
            SaleReturn.created_at >= period_start,
            SaleReturn.created_at < period_end
        )
        
        if store_id:
            returns_query = returns_query.filter(SaleReturn.store_id == store_id)
        
        returns_result = returns_query.first()
        metrics.returns_amount = Decimal(str(returns_result[0] or 0))
        
        return metrics
    
    def get_product_profit_breakdown(
        self,
        tenant_id: str,
        period: ReportPeriod = ReportPeriod.DAILY,
        reference_date: Optional[datetime] = None,
        store_id: Optional[str] = None,
        limit: int = 50,
        sort_by: str = "gross_profit"
    ) -> List[ProductProfitItem]:
        """
        Get profit breakdown by product for a period.
        
        Args:
            tenant_id: Tenant identifier
            period: Report period
            reference_date: Reference date
            store_id: Optional store filter
            limit: Maximum products to return
            sort_by: Sort field ('gross_profit', 'revenue', 'quantity_sold')
            
        Returns:
            List of ProductProfitItem sorted by profitability
        """
        period_start, period_end = self.get_period_bounds(
            period, reference_date
        )
        
        # Build filters
        filters = [
            Sale.tenant_id == tenant_id,
            Sale.sale_date >= period_start,
            Sale.sale_date < period_end,
            Sale.status.notin_(['voided', 'cancelled']),
            SaleItem.variant_id != None  # Only items with variants
        ]
        
        if store_id:
            filters.append(Sale.store_id == store_id)
        
        # Query product-level profit
        from models.product import Product, ProductVariant
        
        query = self.db.query(
            SaleItem.variant_id,
            SaleItem.product_name,
            func.sum(SaleItem.quantity).label('quantity_sold'),
            func.sum(SaleItem.total).label('revenue'),
            func.sum(SaleItem.total_cost).label('cogs'),
        ).join(
            Sale, SaleItem.sale_id == Sale.id
        ).filter(and_(*filters)).group_by(
            SaleItem.variant_id,
            SaleItem.product_name
        )
        
        # Apply sorting
        if sort_by == "gross_profit":
            query = query.order_by(
                (func.sum(SaleItem.total) - func.sum(SaleItem.total_cost)).desc()
            )
        elif sort_by == "revenue":
            query = query.order_by(func.sum(SaleItem.total).desc())
        elif sort_by == "quantity_sold":
            query = query.order_by(func.sum(SaleItem.quantity).desc())
        
        query = query.limit(limit)
        results = query.all()
        
        product_profits = []
        for row in results:
            variant_id = row.variant_id
            revenue = Decimal(str(row.revenue or 0))
            cogs = Decimal(str(row.cogs or 0))
            gross_profit = revenue - cogs
            
            margin_percent = Decimal('0')
            if revenue > 0:
                margin_percent = (gross_profit / revenue) * 100
            
            product_profits.append(ProductProfitItem(
                product_id=None,  # Would need to join with Product table
                product_name=row.product_name,
                variant_id=variant_id,
                quantity_sold=int(row.quantity_sold or 0),
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross_profit,
                profit_margin_percent=margin_percent
            ))
        
        return product_profits
    
    def get_store_profit_comparison(
        self,
        tenant_id: str,
        period: ReportPeriod = ReportPeriod.MONTHLY,
        reference_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Compare profit across all stores for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            period: Report period
            reference_date: Reference date
            
        Returns:
            List of store profit summaries
        """
        stores = self.db.query(Store).filter(
            Store.tenant_id == tenant_id,
            Store.is_active == True
        ).all()
        
        store_profits = []
        
        for store in stores:
            metrics = self.compute_period_profit(
                tenant_id=tenant_id,
                period=period,
                reference_date=reference_date,
                store_id=store.id
            )
            
            store_profits.append({
                "store_id": store.id,
                "store_name": store.name,
                "store_code": store.code,
                "metrics": metrics.to_dict()
            })
        
        # Sort by net profit
        store_profits.sort(
            key=lambda x: x["metrics"]["net_profit"]["net_profit"],
            reverse=True
        )
        
        return store_profits
    
    def compute_profit_trend(
        self,
        tenant_id: str,
        period: ReportPeriod = ReportPeriod.DAILY,
        days: int = 30,
        store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Compute profit trend over multiple periods.
        
        Args:
            tenant_id: Tenant identifier
            period: Period type for each data point
            days: Number of days to look back
            store_id: Optional store filter
            
        Returns:
            List of daily/weekly profit data points
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        trend_data = []
        current_date = start_date
        
        while current_date < end_date:
            metrics = self.compute_period_profit(
                tenant_id=tenant_id,
                period=period,
                reference_date=current_date,
                store_id=store_id
            )
            
            trend_data.append({
                "date": current_date.date().isoformat(),
                "revenue": float(metrics.total_revenue),
                "cogs": float(metrics.total_cogs),
                "gross_profit": float(metrics.gross_profit),
                "expenses": float(metrics.total_expenses),
                "net_profit": float(metrics.net_profit),
                "net_margin_percent": float(metrics.net_margin_percent),
                "sales_count": metrics.total_sales_count
            })
            
            # Move to next period
            if period == ReportPeriod.DAILY:
                current_date += timedelta(days=1)
            elif period == ReportPeriod.WEEKLY:
                current_date += timedelta(weeks=1)
            elif period == ReportPeriod.MONTHLY:
                if current_date.month == 12:
                    current_date = current_date.replace(
                        year=current_date.year + 1, month=1
                    )
                else:
                    current_date = current_date.replace(month=current_date.month + 1)
        
        return trend_data
    
    def get_quick_profit_summary(
        self,
        tenant_id: str,
        store_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get quick profit summary for today, this week, and this month.
        
        Args:
            tenant_id: Tenant identifier
            store_id: Optional store filter
            
        Returns:
            Dictionary with profit summaries for multiple periods
        """
        today = datetime.utcnow()
        
        return {
            "today": self.compute_period_profit(
                tenant_id=tenant_id,
                period=ReportPeriod.DAILY,
                reference_date=today,
                store_id=store_id
            ).to_dict(),
            "this_week": self.compute_period_profit(
                tenant_id=tenant_id,
                period=ReportPeriod.WEEKLY,
                reference_date=today,
                store_id=store_id
            ).to_dict(),
            "this_month": self.compute_period_profit(
                tenant_id=tenant_id,
                period=ReportPeriod.MONTHLY,
                reference_date=today,
                store_id=store_id
            ).to_dict()
        }
    
    def estimate_cogs_weighted_average(
        self,
        variant_id: str,
        quantity_sold: int
    ) -> Decimal:
        """
        Estimate COGS using weighted average cost method.
        
        This is used when exact batch tracking isn't available.
        
        Args:
            variant_id: Product variant identifier
            quantity_sold: Quantity sold
            
        Returns:
            Estimated total COGS
        """
        from models.inventory import InventoryBatch
        
        # Get all batches for this variant
        batches = self.db.query(InventoryBatch).filter(
            InventoryBatch.variant_id == variant_id,
            InventoryBatch.quantity_remaining > 0
        ).order_by(InventoryBatch.received_at.asc()).all()
        
        if not batches:
            # Fallback to product cost price
            from models.product import ProductVariant
            variant = self.db.query(ProductVariant).filter(
                ProductVariant.id == variant_id
            ).first()
            if variant and variant.cost_price_adjustment:
                return Decimal(str(variant.cost_price_adjustment)) * quantity_sold
            return Decimal('0')
        
        total_quantity = sum(b.quantity_remaining for b in batches)
        total_value = sum(
            Decimal(str(b.unit_cost)) * b.quantity_remaining 
            for b in batches
        )
        
        if total_quantity == 0:
            return Decimal('0')
        
        avg_cost = total_value / total_quantity
        return avg_cost * quantity_sold
