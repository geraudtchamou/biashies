"""
Loyalty Service - Manages points earning, redemption, and tier upgrades
for the African POS system.

This service handles:
- Points calculation based on sales
- Points redemption for discounts
- Tier qualification and upgrades
- Loyalty transaction logging
- Expiration handling
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.loyalty import (
    LoyaltyProgram,
    LoyaltyTier,
    ClientLoyaltyAccount,
    LoyaltyTransaction,
)
from models.client import Client
from models.sale import Sale


class TransactionType(str, Enum):
    """Types of loyalty transactions."""
    EARN = "earn"
    REDEEM = "redeem"
    ADJUSTMENT = "adjustment"
    EXPIRE = "expire"
    BONUS = "bonus"
    REFUND = "refund"


@dataclass
class LoyaltyResult:
    """Result of a loyalty operation."""
    success: bool
    points_earned: int = 0
    points_redeemed: int = 0
    new_balance: int = 0
    tier_upgraded: bool = False
    new_tier_id: Optional[str] = None
    message: str = ""
    error: Optional[str] = None


class LoyaltyService:
    """
    Service for managing customer loyalty programs.
    
    Handles points earning/redemption and automatic tier management
    based on customer spending and engagement.
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize the loyalty service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
    
    def get_active_program(self, tenant_id: str, store_id: Optional[str] = None) -> Optional[LoyaltyProgram]:
        """
        Get the active loyalty program for a tenant/store.
        
        Args:
            tenant_id: Tenant identifier
            store_id: Optional store identifier for store-specific programs
            
        Returns:
            Active loyalty program or None
        """
        query = self.db.query(LoyaltyProgram).filter(
            LoyaltyProgram.tenant_id == tenant_id,
            LoyaltyProgram.is_active == True
        )
        
        if store_id:
            query = query.filter(LoyaltyProgram.store_id == store_id)
        else:
            query = query.filter(LoyaltyProgram.store_id == None)
        
        return query.first()
    
    def get_or_create_account(
        self, 
        client_id: str, 
        program_id: str,
        tenant_id: str
    ) -> ClientLoyaltyAccount:
        """
        Get existing loyalty account or create a new one.
        
        Args:
            client_id: Client identifier
            program_id: Loyalty program identifier
            tenant_id: Tenant identifier
            
        Returns:
            Client loyalty account
        """
        account = self.db.query(ClientLoyaltyAccount).filter(
            ClientLoyaltyAccount.client_id == client_id,
            ClientLoyaltyAccount.program_id == program_id
        ).first()
        
        if not account:
            account = ClientLoyaltyAccount(
                tenant_id=tenant_id,
                client_id=client_id,
                program_id=program_id,
                current_points=0,
                lifetime_points_earned=0,
                lifetime_points_spent=0,
                lifetime_spend=Decimal('0'),
                transaction_count=0
            )
            self.db.add(account)
            self.db.commit()
            self.db.refresh(account)
        
        return account
    
    def calculate_points_to_earn(
        self, 
        amount: Decimal, 
        program: LoyaltyProgram,
        account: Optional[ClientLoyaltyAccount] = None
    ) -> int:
        """
        Calculate points to earn for a purchase amount.
        
        Args:
            amount: Purchase amount in currency units
            program: Loyalty program configuration
            account: Optional client account for tier multiplier
            
        Returns:
            Number of points to earn
        """
        # Base points calculation
        currency_unit = Decimal(str(program.currency_unit))
        points_per_unit = Decimal(str(program.points_per_currency_unit))
        
        base_points = int((amount / currency_unit) * points_per_unit)
        
        # Apply tier multiplier if account exists
        if account and account.tier_id:
            tier = self.db.query(LoyaltyTier).filter(
                LoyaltyTier.id == account.tier_id
            ).first()
            
            if tier:
                multiplier = Decimal(str(tier.points_multiplier))
                base_points = int(base_points * multiplier)
        
        return base_points
    
    def earn_points(
        self,
        client_id: str,
        sale_amount: Decimal,
        sale_id: str,
        tenant_id: str,
        program_id: Optional[str] = None,
        store_id: Optional[str] = None,
        bonus_points: int = 0,
        description: Optional[str] = None
    ) -> LoyaltyResult:
        """
        Award points for a purchase.
        
        Args:
            client_id: Client making the purchase
            sale_amount: Total sale amount
            sale_id: Reference to the sale
            tenant_id: Tenant identifier
            program_id: Optional program ID (auto-detected if not provided)
            store_id: Store identifier
            bonus_points: Optional bonus points to add
            description: Custom description for the transaction
            
        Returns:
            LoyaltyResult with points earned and new balance
        """
        try:
            # Get or detect program
            if not program_id:
                program = self.get_active_program(tenant_id, store_id)
                if not program:
                    return LoyaltyResult(
                        success=False,
                        error="No active loyalty program found"
                    )
                program_id = program.id
            else:
                program = self.db.query(LoyaltyProgram).filter(
                    LoyaltyProgram.id == program_id
                ).first()
            
            if not program or not program.is_active:
                return LoyaltyResult(
                    success=False,
                    error="Loyalty program not active"
                )
            
            # Get or create account
            account = self.get_or_create_account(client_id, program_id, tenant_id)
            
            # Calculate points
            base_points = self.calculate_points_to_earn(sale_amount, program, account)
            total_points = base_points + bonus_points
            
            if total_points <= 0:
                return LoyaltyResult(
                    success=True,
                    points_earned=0,
                    new_balance=account.current_points,
                    message="No points earned (amount too low)"
                )
            
            # Update account
            old_balance = account.current_points
            account.current_points += total_points
            account.lifetime_points_earned += total_points
            account.lifetime_spend += sale_amount
            account.transaction_count += 1
            account.last_activity_at = datetime.utcnow()
            
            # Determine expiration
            expires_at = None
            if program.points_expiry_months:
                expires_at = datetime.utcnow() + timedelta(
                    days=program.points_expiry_months * 30
                )
            
            # Create transaction record
            transaction = LoyaltyTransaction(
                tenant_id=tenant_id,
                account_id=account.id,
                transaction_type=TransactionType.EARN.value,
                points=total_points,
                balance_after=account.current_points,
                reference_type="sale",
                reference_id=sale_id,
                description=description or f"Earned {total_points} points from purchase",
                expires_at=expires_at,
                performed_by=None  # System-generated
            )
            
            self.db.add(transaction)
            
            # Check for tier upgrade
            tier_upgraded, new_tier = self.check_and_upgrade_tier(account, program)
            
            self.db.commit()
            self.db.refresh(account)
            
            message = f"Earned {total_points} points"
            if bonus_points > 0:
                message += f" (including {bonus_points} bonus)"
            if tier_upgraded:
                message += f" ✓ Upgraded to {new_tier.name}!"
            
            return LoyaltyResult(
                success=True,
                points_earned=total_points,
                new_balance=account.current_points,
                tier_upgraded=tier_upgraded,
                new_tier_id=new_tier.id if tier_upgraded else None,
                message=message
            )
            
        except Exception as e:
            self.db.rollback()
            return LoyaltyResult(
                success=False,
                error=str(e)
            )
    
    def redeem_points(
        self,
        client_id: str,
        points_to_redeem: int,
        tenant_id: str,
        program_id: Optional[str] = None,
        store_id: Optional[str] = None,
        sale_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> LoyaltyResult:
        """
        Redeem points for discount or reward.
        
        Args:
            client_id: Client redeeming points
            points_to_redeem: Number of points to redeem
            tenant_id: Tenant identifier
            program_id: Optional program ID
            store_id: Store identifier
            sale_id: Optional associated sale
            description: Description for the transaction
            
        Returns:
            LoyaltyResult with redemption details
        """
        try:
            # Get program
            if not program_id:
                program = self.get_active_program(tenant_id, store_id)
                if not program:
                    return LoyaltyResult(
                        success=False,
                        error="No active loyalty program found"
                    )
                program_id = program.id
            else:
                program = self.db.query(LoyaltyProgram).filter(
                    LoyaltyProgram.id == program_id
                ).first()
            
            if not program or not program.is_active:
                return LoyaltyResult(
                    success=False,
                    error="Loyalty program not active"
                )
            
            # Get account
            account = self.db.query(ClientLoyaltyAccount).filter(
                ClientLoyaltyAccount.client_id == client_id,
                ClientLoyaltyAccount.program_id == program_id
            ).first()
            
            if not account:
                return LoyaltyResult(
                    success=False,
                    error="No loyalty account found for this client"
                )
            
            # Validate redemption
            if points_to_redeem <= 0:
                return LoyaltyResult(
                    success=False,
                    error="Invalid points amount"
                )
            
            if account.current_points < points_to_redeem:
                return LoyaltyResult(
                    success=False,
                    error=f"Insufficient points. Available: {account.current_points}"
                )
            
            if points_to_redeem < program.min_points_redemption:
                return LoyaltyResult(
                    success=False,
                    error=f"Minimum redemption is {program.min_points_redemption} points"
                )
            
            # Calculate discount value
            points_value = Decimal(str(program.points_value))
            discount_value = Decimal(str(points_to_redeem)) * points_value
            
            # Check max discount limit
            if sale_id:
                sale = self.db.query(Sale).filter(Sale.id == sale_id).first()
                if sale:
                    max_discount = sale.total_amount * (
                        Decimal(str(program.max_discount_percent)) / 100
                    )
                    if discount_value > max_discount:
                        return LoyaltyResult(
                            success=False,
                            error=f"Discount cannot exceed {program.max_discount_percent}% of sale"
                        )
            
            # Update account
            old_balance = account.current_points
            account.current_points -= points_to_redeem
            account.lifetime_points_spent += points_to_redeem
            account.last_activity_at = datetime.utcnow()
            
            # Create transaction record
            transaction = LoyaltyTransaction(
                tenant_id=tenant_id,
                account_id=account.id,
                transaction_type=TransactionType.REDEEM.value,
                points=-points_to_redeem,  # Negative for redemption
                balance_after=account.current_points,
                reference_type="sale" if sale_id else "manual",
                reference_id=sale_id,
                description=description or f"Redeemed {points_to_redeem} points for {discount_value}",
                performed_by=None
            )
            
            self.db.add(transaction)
            self.db.commit()
            self.db.refresh(account)
            
            return LoyaltyResult(
                success=True,
                points_redeemed=points_to_redeem,
                new_balance=account.current_points,
                message=f"Redeemed {points_to_redeem} points (Value: {discount_value})"
            )
            
        except Exception as e:
            self.db.rollback()
            return LoyaltyResult(
                success=False,
                error=str(e)
            )
    
    def check_and_upgrade_tier(
        self, 
        account: ClientLoyaltyAccount,
        program: LoyaltyProgram
    ) -> Tuple[bool, Optional[LoyaltyTier]]:
        """
        Check if account qualifies for tier upgrade and perform upgrade.
        
        Args:
            account: Client loyalty account
            program: Loyalty program
            
        Returns:
            Tuple of (upgraded: bool, new_tier: Optional[LoyaltyTier])
        """
        current_tier = None
        if account.tier_id:
            current_tier = self.db.query(LoyaltyTier).filter(
                LoyaltyTier.id == account.tier_id
            ).first()
        
        # Get all tiers for this program, ordered by requirements
        tiers = self.db.query(LoyaltyTier).filter(
            LoyaltyTier.program_id == program.id,
            LoyaltyTier.is_active == True
        ).order_by(
            LoyaltyTier.min_lifetime_spend.desc(),
            LoyaltyTier.min_lifetime_points.desc(),
            LoyaltyTier.sort_order.asc()
        ).all()
        
        # Find highest qualifying tier
        new_tier = None
        for tier in tiers:
            qualifies = True
            
            if tier.min_lifetime_spend > 0:
                if account.lifetime_spend < tier.min_lifetime_spend:
                    qualifies = False
            
            if tier.min_lifetime_points > 0:
                if account.lifetime_points_earned < tier.min_lifetime_points:
                    qualifies = False
            
            if tier.min_transactions > 0:
                if account.transaction_count < tier.min_transactions:
                    qualifies = False
            
            if qualifies:
                new_tier = tier
                break
        
        # Upgrade if qualified for higher tier
        if new_tier and (not current_tier or new_tier.sort_order > current_tier.sort_order):
            account.tier_id = new_tier.id
            account.tier_upgraded_at = datetime.utcnow()
            return True, new_tier
        
        return False, None
    
    def get_client_status(
        self, 
        client_id: str, 
        tenant_id: str,
        program_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive loyalty status for a client.
        
        Args:
            client_id: Client identifier
            tenant_id: Tenant identifier
            program_id: Optional program ID
            
        Returns:
            Dictionary with complete loyalty status
        """
        # Get program
        if not program_id:
            program = self.get_active_program(tenant_id)
            if not program:
                return {"error": "No active program"}
            program_id = program.id
        else:
            program = self.db.query(LoyaltyProgram).filter(
                LoyaltyProgram.id == program_id
            ).first()
        
        # Get account
        account = self.db.query(ClientLoyaltyAccount).filter(
            ClientLoyaltyAccount.client_id == client_id,
            ClientLoyaltyAccount.program_id == program_id
        ).first()
        
        if not account:
            return {
                "has_account": False,
                "current_points": 0,
                "message": "Not enrolled in loyalty program"
            }
        
        # Get tier info
        tier_info = None
        if account.tier_id:
            tier = self.db.query(LoyaltyTier).filter(
                LoyaltyTier.id == account.tier_id
            ).first()
            if tier:
                tier_info = {
                    "name": tier.name,
                    "discount_percent": float(tier.discount_percent),
                    "points_multiplier": float(tier.points_multiplier),
                    "benefits": {
                        "birthday_bonus": tier.birthday_bonus_points,
                        "exclusive_access": tier.exclusive_access,
                        "free_delivery": tier.free_delivery
                    }
                }
        
        # Get recent transactions
        recent_transactions = self.db.query(LoyaltyTransaction).filter(
            LoyaltyTransaction.account_id == account.id
        ).order_by(
            LoyaltyTransaction.created_at.desc()
        ).limit(10).all()
        
        transactions_summary = [
            {
                "type": t.transaction_type,
                "points": t.points,
                "balance_after": t.balance_after,
                "description": t.description,
                "date": t.created_at.isoformat()
            }
            for t in recent_transactions
        ]
        
        return {
            "has_account": True,
            "current_points": account.current_points,
            "lifetime_points_earned": account.lifetime_points_earned,
            "lifetime_points_spent": account.lifetime_points_spent,
            "lifetime_spend": float(account.lifetime_spend),
            "transaction_count": account.transaction_count,
            "tier": tier_info,
            "next_review_date": account.next_review_date.isoformat() if account.next_review_date else None,
            "recent_transactions": transactions_summary,
            "points_expire_in_days": self._days_until_expiration(account, program)
        }
    
    def _days_until_expiration(
        self, 
        account: ClientLoyaltyAccount, 
        program: LoyaltyProgram
    ) -> Optional[int]:
        """Calculate days until points expire."""
        if not program.points_expiry_months:
            return None
        
        # Find earliest expiring points
        earliest_expiry = self.db.query(LoyaltyTransaction).filter(
            LoyaltyTransaction.account_id == account.id,
            LoyaltyTransaction.expires_at != None,
            LoyaltyTransaction.points > 0
        ).order_by(
            LoyaltyTransaction.expires_at.asc()
        ).first()
        
        if earliest_expiry:
            delta = earliest_expiry.expires_at - datetime.utcnow()
            return max(0, delta.days)
        
        return None
    
    def process_expired_points(self, program_id: str) -> int:
        """
        Process expired points for a program.
        
        Args:
            program_id: Program to process
            
        Returns:
            Number of accounts processed
        """
        now = datetime.utcnow()
        
        # Find expired transactions
        expired = self.db.query(LoyaltyTransaction).join(
            ClientLoyaltyAccount,
            LoyaltyTransaction.account_id == ClientLoyaltyAccount.id
        ).filter(
            LoyaltyTransaction.program_id == program_id,
            LoyaltyTransaction.expires_at <= now,
            LoyaltyTransaction.transaction_type != TransactionType.EXPIRE.value
        ).all()
        
        processed_accounts = set()
        
        for transaction in expired:
            account = transaction.account
            
            # Only process if still has points
            if account.current_points > 0:
                # Deduct expired points
                expired_amount = min(
                    transaction.points,
                    account.current_points
                )
                
                account.current_points -= expired_amount
                
                # Create expiration record
                expiry_record = LoyaltyTransaction(
                    tenant_id=account.tenant_id,
                    account_id=account.id,
                    transaction_type=TransactionType.EXPIRE.value,
                    points=-expired_amount,
                    balance_after=account.current_points,
                    description=f"Expired {expired_amount} points",
                    reference_type="expiration",
                    reference_id=transaction.id
                )
                
                self.db.add(expiry_record)
                processed_accounts.add(account.id)
        
        self.db.commit()
        return len(processed_accounts)
    
    def apply_promotion_bonus(
        self,
        client_id: str,
        bonus_points: int,
        tenant_id: str,
        program_id: Optional[str] = None,
        description: str = "Promotional bonus",
        performed_by: Optional[str] = None
    ) -> LoyaltyResult:
        """
        Award bonus points from a promotion.
        
        Args:
            client_id: Client to award bonus
            bonus_points: Number of bonus points
            tenant_id: Tenant identifier
            program_id: Optional program ID
            description: Description of the bonus
            performed_by: User who applied the bonus
            
        Returns:
            LoyaltyResult with bonus details
        """
        try:
            # Get program
            if not program_id:
                program = self.get_active_program(tenant_id)
                if not program:
                    return LoyaltyResult(
                        success=False,
                        error="No active loyalty program found"
                    )
                program_id = program.id
            else:
                program = self.db.query(LoyaltyProgram).filter(
                    LoyaltyProgram.id == program_id
                ).first()
            
            # Get or create account
            account = self.get_or_create_account(client_id, program_id, tenant_id)
            
            # Update account
            account.current_points += bonus_points
            account.lifetime_points_earned += bonus_points
            account.last_activity_at = datetime.utcnow()
            
            # Create transaction
            transaction = LoyaltyTransaction(
                tenant_id=tenant_id,
                account_id=account.id,
                transaction_type=TransactionType.BONUS.value,
                points=bonus_points,
                balance_after=account.current_points,
                description=description,
                reference_type="promotion",
                performed_by=performed_by
            )
            
            self.db.add(transaction)
            self.db.commit()
            self.db.refresh(account)
            
            return LoyaltyResult(
                success=True,
                points_earned=bonus_points,
                new_balance=account.current_points,
                message=f"Awarded {bonus_points} bonus points"
            )
            
        except Exception as e:
            self.db.rollback()
            return LoyaltyResult(
                success=False,
                error=str(e)
            )
