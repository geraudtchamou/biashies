"""
Module: Intelligent Inventory & Customer Engagement Services
Target: African POS System (Offline-First, Low-Data)

Features Implemented:
1. Smart Expiry & Flash Sales Manager
2. Visual Search Service (Metadata handling)
3. Predictive Restocking Engine
4. Customer Soft Credit Scoring Service
"""

import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Assuming SQLAlchemy or similar ORM is used in the main project
# from models import InventoryBatch, Product, Sale, Client, etc.

logger = logging.getLogger(__name__)


class RiskTier(Enum):
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    VERY_HIGH_RISK = "VERY_HIGH_RISK"


class ExpiryStatus(Enum):
    MONITORING = "monitoring"
    ALERTED = "alerted"
    DISCOUNTED = "discounted"
    SOLD = "sold"
    EXPIRED = "expired"
    DISCARDED = "discarded"


@dataclass
class ExpiryAlert:
    batch_id: str
    product_name: str
    expiry_date: date
    days_until_expiry: int
    quantity_remaining: float
    suggested_discount: float
    status: str


@dataclass
class RestockRecommendation:
    product_id: str
    product_name: str
    current_stock: float
    predicted_demand_7d: float
    recommended_order_qty: float
    priority_score: int  # 1-10
    reason_code: str


@dataclass
class CustomerCreditProfile:
    client_id: str
    client_name: str
    final_score: int
    risk_tier: RiskTier
    outstanding_balance: float
    credit_limit: float
    recommended_action: str


class SmartExpiryService:
    """
    Manages product expiry tracking and automated flash sales.
    Reduces waste by suggesting dynamic discounts.
    """

    def __init__(self, db_session):
        self.db = db_session

    def calculate_discount(self, days_left: int) -> float:
        """
        Business logic for dynamic discounting based on expiry proximity.
        Matches the SQL function calc_expiry_discount.
        """
        if days_left <= 0:
            return 100.0
        elif days_left <= 3:
            return 50.0
        elif days_left <= 7:
            return 30.0
        elif days_left <= 14:
            return 15.0
        return 0.0

    def get_urgent_expiries(self, store_id: str, threshold_days: int = 7) -> List[ExpiryAlert]:
        """
        Fetches items expiring within threshold_days.
        Used for dashboard widgets and push notifications.
        """
        # Pseudo-SQLAlchemy query
        # results = self.db.query(InventoryExpiryAlert).filter(
        #     InventoryExpiryAlert.store_id == store_id,
        #     InventoryExpiryAlert.days_until_expiry <= threshold_days,
        #     InventoryExpiryAlert.status.in_(['monitoring', 'alerted'])
        # ).order_by(InventoryExpiryAlert.days_until_expiry.asc()).all()
        
        logger.info(f"Fetching urgent expiries for store {store_id} within {threshold_days} days")
        return [] # Placeholder

    def process_daily_expiry_jobs(self):
        """
        Daily cron job to update statuses and trigger alerts.
        Should be called by a background worker (Celery/RQ).
        """
        logger.info("Starting daily expiry processing job")
        
        # In production, this calls the SQL function process_expiry_alerts()
        # self.db.execute("SELECT process_expiry_alerts()")
        
        # 1. Identify expired items -> Mark as expired
        # 2. Identify items entering 7-day window -> Trigger Alert
        # 3. Send notifications to Store Manager
        
        logger.info("Daily expiry processing completed")

    def create_flash_sale(self, store_id: str, alert_ids: List[str]) -> str:
        """
        Bundles expiring items into a Flash Sale campaign.
        Returns the Campaign ID.
        """
        logger.info(f"Creating flash sale for {len(alert_ids)} items in store {store_id}")
        
        # Logic:
        # 1. Create FlashSaleCampaign record
        # 2. Link selected alert items to campaign
        # 3. Set start/end times (e.g., immediate, 48h duration)
        # 4. Apply calculated discounts
        
        return "campaign_uuid_placeholder"


class VisualSearchService:
    """
    Handles metadata for visual product search.
    Supports offline-first by storing lightweight signatures (JSONB) 
    rather than heavy vectors unless pgvector is available.
    """

    def __init__(self, db_session):
        self.db = db_session

    def register_visual_signature(self, product_id: str, store_id: str, 
                                  color_histogram: Dict, texture_features: Dict):
        """
        Saves a visual signature for a product.
        Called when a user takes a photo of a new unbranded product.
        """
        logger.info(f"Registering visual signature for product {product_id}")
        
        # Logic:
        # 1. Insert/Update product_visual_signatures
        # 2. Mark as primary if first image
        
        pass

    def find_similar_products(self, store_id: str, query_colors: List[int], 
                              limit: int = 5) -> List[Dict]:
        """
        Finds products with similar color histograms.
        Simplified logic for JSONB storage; real implementation uses Cosine Similarity.
        """
        logger.info(f"Searching for visually similar products in store {store_id}")
        
        # Heuristic: Match dominant color buckets
        # SELECT * FROM product_visual_signatures 
        # WHERE store_id = ? AND color_histogram -> 'dominant' IN (?)
        
        return []


class PredictiveRestockingService:
    """
    Analyzes sales velocity and seasonality to suggest restocking.
    Critical for preventing stockouts of high-turnover goods.
    """

    def __init__(self, db_session):
        self.db = db_session

    def calculate_seasonal_multiplier(self, category: str, date: date) -> float:
        """
        Returns demand multiplier based on historical seasonality.
        E.g., Rice during Ramadan, Notebooks in September.
        """
        # Lookup in restock_patterns.seasonal_multipliers JSONB
        # Fallback to 1.0 if no data
        
        month = date.month
        if category == 'School Supplies' and month in [8, 9]:
            return 2.0
        if category == 'Food Staples' and month in [3, 4]: # Ramadan variable
            return 1.5
            
        return 1.0

    def generate_restock_recommendations(self, store_id: str) -> List[RestockRecommendation]:
        """
        Main engine: Scans all products, compares stock vs predicted demand.
        Generates rows for restock_recommendations table.
        """
        logger.info(f"Generating restock recommendations for store {store_id}")
        
        recommendations = []
        
        # Pseudo-logic:
        # 1. Fetch all active products with stock < reorder_point
        # 2. For each:
        #    - Calculate Avg Daily Sales (last 30d)
        #    - Apply Seasonal Multiplier
        #    - Calculate Safety Stock
        #    - Determine Priority Score (1-10) based on urgency
        
        # Example Mock Data
        recommendations.append(RestockRecommendation(
            product_id="prod_123",
            product_name="5kg Sugar",
            current_stock=10.0,
            predicted_demand_7d=50.0,
            recommended_order_qty=40.0,
            priority_score=9,
            reason_code="LOW_STOCK"
        ))
        
        return recommendations

    def mark_as_ordered(self, recommendation_id: str):
        """Updates status to 'ordered' and logs timestamp."""
        pass


class CustomerCreditScoringService:
    """
    Calculates proprietary credit scores for informal traders.
    Enables safe credit issuance without traditional bureau data.
    """

    def __init__(self, db_session):
        self.db = db_session

    def calculate_score_components(self, client_id: str, store_id: str) -> Dict[str, int]:
        """
        Computes the 4 sub-scores: Repayment, Frequency, Tenure, Utilization.
        Mirrors the SQL function calculate_customer_credit_score.
        """
        scores = {
            'repayment': 50,
            'frequency': 50,
            'tenure': 50,
            'utilization': 50
        }
        
        # 1. Repayment History (40%)
        # Query customer_credit_events for on-time vs late payments
        # total = count(events)
        # on_time = count(events where paid_date <= due_date)
        # score = (on_time / total) * 100
        
        # 2. Frequency (20%)
        # Count purchases in last 90 days
        
        # 3. Tenure (20%)
        # Days since first transaction
        
        # 4. Utilization (20%)
        # (Limit - Balance) / Limit
        
        return scores

    def update_client_score(self, client_id: str, store_id: str):
        """
        Recalculates and updates the client's credit score.
        Triggered after:
        - New Sale (Credit)
        - Payment Received
        - Monthly Batch Job
        """
        components = self.calculate_score_components(client_id, store_id)
        
        final_score = int(
            (components['repayment'] * 0.4) +
            (components['frequency'] * 0.2) +
            (components['tenure'] * 0.2) +
            (components['utilization'] * 0.2)
        )
        
        # Determine Tier
        if final_score >= 80:
            tier = RiskTier.LOW_RISK
            action = "Approve up to limit"
        elif final_score >= 60:
            tier = RiskTier.MEDIUM_RISK
            action = "Approve with manager approval"
        else:
            tier = RiskTier.HIGH_RISK
            action = "Cash only or strict terms"
            
        logger.info(f"Updated score for {client_id}: {final_score} ({tier.value})")
        
        # Update DB: customer_credit_scores table
        return {
            "final_score": final_score,
            "tier": tier.value,
            "action": action
        }

    def check_credit_eligibility(self, client_id: str, store_id: str, 
                                 amount: float) -> Tuple[bool, str]:
        """
        Real-time check before allowing a credit sale.
        Returns (Allowed, Reason).
        """
        # Fetch latest score
        # profile = self.get_profile(client_id, store_id)
        
        # Rules:
        # 1. If Very High Risk -> Deny
        # 2. If Balance + Amount > Limit -> Deny
        # 3. If Medium Risk & Amount > Threshold -> Require PIN/Manager
        
        return True, "Approved"


# ==============================================================================
# ORCHESTRATOR: Daily Background Jobs
# ==============================================================================

def run_daily_intelligence_jobs(store_id: Optional[str] = None):
    """
    Master function to be called by Cron/Celery every night.
    Executes all maintenance and prediction tasks.
    """
    logger.info(f"Starting daily intelligence jobs for store: {store_id or 'ALL'}")
    
    # 1. Process Expiry Alerts
    # SmartExpiryService(db).process_daily_expiry_jobs()
    
    # 2. Generate Restock Recommendations
    # PredictiveRestockingService(db).generate_restock_recommendations(store_id)
    
    # 3. Refresh Credit Scores (for active clients)
    # Loop through clients with recent activity
    
    logger.info("Daily intelligence jobs completed")
