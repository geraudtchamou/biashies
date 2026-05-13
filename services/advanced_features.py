"""
=============================================================================
MODULE: Advanced Feature Services (Python/FastAPI)
PURPOSE: Implements logic for Health Scoring, Anomaly Detection, USSD, Group Buying
STACK: Python 3.10+, FastAPI, SQLAlchemy/SQLModel
=============================================================================
"""

import math
import hashlib
import json
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass, asdict
from decimal import Decimal

# Mock DB imports (replace with actual SQLAlchemy models)
# from models import Store, Sale, User, CashTransaction, Purchase

class AnomalyType(str, Enum):
    VELOCITY_SPIKE = "velocity_spike"
    VOID_ABUSE = "void_abuse"
    OFF_HOURS_LOGIN = "off_hours_login"
    NEGATIVE_MARGIN = "negative_margin"
    DUPLICATE_REFUND = "duplicate_refund"

class HealthCategory(str, Enum):
    LIQUIDITY = "liquidity"
    INVENTORY_TURNOVER = "inventory_turnover"
    DEBT_RATIO = "debt_ratio"
    GROWTH_CONSISTENCY = "growth_consistency"
    COMPLIANCE = "compliance"

@dataclass
class HealthScoreResult:
    overall_score: int
    liquidity_score: int
    inventory_score: int
    growth_score: int
    compliance_score: int
    metrics: Dict[str, float]
    recommendations: List[str]

@dataclass
class AnomalyAlert:
    store_id: str
    user_id: Optional[str]
    anomaly_type: AnomalyType
    severity: int
    evidence: Dict[str, Any]
    message: str

class BusinessHealthService:
    """
    Calculates the 0-100 Business Health Score based on weighted metrics.
    Weights: Liquidity (30%), Inventory (25%), Growth (25%), Compliance (20%)
    """
    
    def __init__(self, db_session):
        self.db = db_session

    def calculate_daily_health(self, store_id: str, snapshot_date: date = None) -> HealthScoreResult:
        if snapshot_date is None:
            snapshot_date = date.today()
        
        # 1. Calculate Component Scores
        liq_score = self._calc_liquidity_score(store_id)
        inv_score = self._calc_inventory_score(store_id)
        grow_score = self._calc_growth_score(store_id)
        comp_score = self._calc_compliance_score(store_id)
        
        # 2. Weighted Average
        overall = int(
            (liq_score * 0.30) +
            (inv_score * 0.25) +
            (grow_score * 0.25) +
            (comp_score * 0.20)
        )
        
        # 3. Generate Recommendations
        recommendations = self._generate_recommendations(liq_score, inv_score, grow_score, comp_score)
        
        metrics = {
            "cash_ratio": self._get_cash_ratio(store_id),
            "stock_turn_days": self._get_stock_turn_days(store_id),
            "revenue_growth_pct": self._get_revenue_growth(store_id),
            "tax_compliance_rate": self._get_tax_compliance(store_id)
        }
        
        return HealthScoreResult(
            overall_score=overall,
            liquidity_score=liq_score,
            inventory_score=inv_score,
            growth_score=grow_score,
            compliance_score=comp_score,
            metrics=metrics,
            recommendations=recommendations
        )

    def _calc_liquidity_score(self, store_id: str) -> int:
        """
        Logic: Cash on Hand / Current Payables
        Target Ratio: 1.5 (Score 100)
        Minimum Ratio: 0.5 (Score 20)
        """
        # Pseudo-SQLAlchemy queries
        # cash = db.query(func.sum(CashTransaction.amount)).filter(...).scalar()
        # payables = db.query(func.sum(Purchase.balance)).filter(...).scalar()
        
        # Mock data for illustration
        cash = 5000.0
        payables = 4000.0
        
        if payables == 0:
            return 100
            
        ratio = cash / payables
        
        if ratio >= 1.5:
            return 100
        elif ratio <= 0.5:
            return 20
        else:
            return int((ratio / 1.5) * 100)

    def _calc_inventory_score(self, store_id: str) -> int:
        """
        Logic: Based on Stock Turnover Days
        Ideal: 15-30 days (Score 100)
        Too fast (<7): Risk of stockouts (Score 60)
        Too slow (>60): Dead stock (Score 40)
        """
        turn_days = self._get_stock_turn_days(store_id)
        
        if 15 <= turn_days <= 30:
            return 100
        elif turn_days < 15:
            # Linear drop to 60
            return max(60, 100 - ((15 - turn_days) * 5))
        else:
            # Linear drop to 40
            return max(40, 100 - ((turn_days - 30) * 2))

    def _calc_growth_score(self, store_id: str) -> int:
        """
        Logic: Month-over-Month Revenue Growth
        >10% growth: 100
        0-10%: Linear 50-100
        Negative: <50
        """
        growth_pct = self._get_revenue_growth(store_id)
        
        if growth_pct >= 10:
            return 100
        elif growth_pct >= 0:
            return int(50 + (growth_pct / 10) * 50)
        else:
            return max(0, int(50 + (growth_pct * 5))) # Penalty for negative

    def _calc_compliance_score(self, store_id: str) -> int:
        """
        Logic: Tax filing consistency + Anomaly resolution rate
        """
        tax_rate = self._get_tax_compliance(store_id)
        anomaly_resolution_rate = self._get_anomaly_resolution_rate(store_id)
        
        return int((tax_rate * 0.7) + (anomaly_resolution_rate * 0.3))

    def _generate_recommendations(self, liq: int, inv: int, grow: int, comp: int) -> List[str]:
        recs = []
        if liq < 50:
            recs.append("⚠️ Low liquidity: Consider delaying non-essential purchases or collecting overdue debts.")
        if inv < 60:
            recs.append("📦 Inventory issues: Review slow-moving stock and adjust reorder points.")
        if grow < 40:
            recs.append("📉 Revenue decline: Consider running a promotion or reviewing pricing strategy.")
        if comp < 70:
            recs.append("📝 Compliance risk: Ensure all tax filings are up to date.")
        
        if not recs:
            recs.append("✅ Business health is excellent! Keep maintaining current practices.")
            
        return recs

    # Helper stubs for DB queries
    def _get_cash_ratio(self, store_id: str) -> float: return 1.25
    def _get_stock_turn_days(self, store_id: str) -> float: return 22.0
    def _get_revenue_growth(self, store_id: str) -> float: return 5.5
    def _get_tax_compliance(self, store_id: str) -> float: return 90.0
    def _get_anomaly_resolution_rate(self, store_id: str) -> float: return 85.0


class AnomalyDetectionService:
    """
    Real-time anomaly detection using statistical methods (Z-Score, Benford's Law).
    """
    
    def __init__(self, db_session):
        self.db = db_session

    def check_sale_velocity(self, store_id: str, user_id: str) -> Optional[AnomalyAlert]:
        """
        Detects if a cashier is processing sales unusually fast (potential fake sales).
        Uses Z-Score over last 7 days.
        """
        # 1. Get sales count in last 30 mins
        current_sales_count = self._get_recent_sales_count(store_id, user_id, minutes=30)
        
        # 2. Get historical stats for same time window over last 7 days
        hist_avg, hist_std = self._get_historical_velocity_stats(store_id, user_id, days=7)
        
        if hist_std == 0 or hist_std is None:
            return None  # Not enough data
            
        z_score = (current_sales_count - hist_avg) / hist_std
        
        if z_score > 3.0:  # 3 Sigma event
            return AnomalyAlert(
                store_id=store_id,
                user_id=user_id,
                anomaly_type=AnomalyType.VELOCITY_SPIKE,
                severity=4,
                evidence={
                    "current_count": current_sales_count,
                    "historical_avg": round(hist_avg, 2),
                    "z_score": round(z_score, 2)
                },
                message=f"Unusual sales velocity detected: {current_sales_count} sales in 30m vs avg {hist_avg}"
            )
        return None

    def check_negative_margin(self, store_id: str, sale_id: str) -> Optional[AnomalyAlert]:
        """
        Flags sales where COGS > Selling Price (unless intentional promo).
        """
        # Query sale details
        # sale = db.query(Sale).get(sale_id)
        
        # Mock data
        total_amount = 100.0
        cogs = 120.0
        
        if cogs > total_amount:
            margin_pct = ((total_amount - cogs) / total_amount) * 100
            return AnomalyAlert(
                store_id=store_id,
                user_id=None,
                anomaly_type=AnomalyType.NEGATIVE_MARGIN,
                severity=3,
                evidence={"sale_id": sale_id, "margin_pct": margin_pct},
                message=f"Sale {sale_id} has negative margin ({margin_pct:.1f}%)"
            )
        return None

    def check_duplicate_refund(self, store_id: str, original_sale_id: str, refund_amount: Decimal) -> Optional[AnomalyAlert]:
        """
        Detects if a refund ID or amount pattern matches recent refunds (potential double dipping).
        """
        # Check DB for similar refunds in last 24h
        count = self._count_similar_refunds(store_id, original_sale_id, refund_amount)
        
        if count > 1:
            return AnomalyAlert(
                store_id=store_id,
                user_id=None,
                anomaly_type=AnomalyType.DUPLICATE_REFUND,
                severity=5,
                evidence={"original_sale_id": original_sale_id, "count": count},
                message=f"Potential duplicate refund detected for sale {original_sale_id}"
            )
        return None

    # Stub helpers
    def _get_recent_sales_count(self, store_id, user_id, minutes) -> int: return 15
    def _get_historical_velocity_stats(self, store_id, user_id, days) -> Tuple[float, float]: return (5.0, 2.0)
    def _count_similar_refunds(self, store_id, sale_id, amount) -> int: return 2


class USSDSessionManager:
    """
    Manages stateful USSD sessions for feature phones.
    Handles menu navigation and context persistence.
    """
    
    MENU_STRUCTURE = {
        "MAIN_MENU": "1. Make Sale\n2. Check Stock\n3. My Balance\n4. Exit",
        "MAKE_SALE": "Enter Product Code:",
        "CONFIRM_SALE": "Confirm Sale of {item} for {amount}? 1. Yes 2. No"
    }

    def __init__(self, db_session):
        self.db = db_session

    def start_session(self, phone_number: str, store_id: str) -> str:
        """Initiate new USSD session"""
        # Create DB record in ussd_sessions
        return self.MENU_STRUCTURE["MAIN_MENU"]

    def process_input(self, session_id: str, user_input: str) -> str:
        """Process user input based on current state"""
        # Fetch session from DB
        # current_step = session.current_menu_step
        
        # Simple state machine logic
        # if current_step == "MAIN_MENU":
        #    if user_input == "1": return self.MENU_STRUCTURE["MAKE_SALE"]
        
        return "Processing..." # Placeholder

    def expire_sessions(self):
        """Cleanup expired sessions (run via cron)"""
        # DELETE FROM ussd_sessions WHERE expires_at < NOW()
        pass


class GroupBuyingService:
    """
    Manages cooperative procurement pools.
    """
    
    def create_pool(self, organizer_id: str, product_id: str, target_qty: float, deadline: datetime) -> str:
        """Create a new buying pool"""
        # Insert into group_buying_pools
        # Return pool_id
        return "pool_uuid_mock"

    def join_pool(self, pool_id: str, store_id: str, quantity: float) -> bool:
        """Add contribution to a pool"""
        # Check if pool is full
        # Check if deadline passed
        # Insert into group_buying_contributions
        # Update pool current_quantity
        return True

    def check_pool_status(self, pool_id: str) -> Dict[str, Any]:
        """Get current status of a pool"""
        # Query pool and contributions
        return {
            "status": "open",
            "current_qty": 50,
            "target_qty": 100,
            "participants": 5
        }


class WhatsAppCatalogService:
    """
    Generates cached catalog messages for WhatsApp sharing.
    """
    
    def generate_catalog_text(self, store_id: str) -> str:
        """
        Creates a formatted text list of top products.
        Optimized for WhatsApp character limits.
        """
        # Fetch top 20 products
        lines = ["*🏪 Daily Specials @ Store Name* 🏪\n"]
        lines.append("_Valid for today only_\n")
        
        # Mock products
        products = [
            ("Rice 5kg", "₦2,500"),
            ("Oil 1L", "₦1,200"),
            ("Sugar 1kg", "₦800")
        ]
        
        for name, price in products:
            lines.append(f"• {name}: *{price}*")
            
        lines.append("\n📞 Reply to order via WhatsApp!")
        
        content = "\n".join(lines)
        
        # Cache this payload in whatsapp_catalog_cache table
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        return content

    def generate_low_stock_alert(self, product_name: str, qty_left: int) -> str:
        """Generate urgent restock message"""
        return f"⚠️ *Low Stock Alert*: {product_name} is running low ({qty_left} left). Restock now!"
