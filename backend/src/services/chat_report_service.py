"""
Chat Report Service - Parse chat commands and generate reports
for the African POS system.

This service handles:
- Natural language command parsing for report requests
- Context extraction (dates, stores, metrics)
- Report generation and formatting
- Scheduled report management
- In-app chat message handling
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Pattern
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from models.chat import ChatConversation, ChatMessage
from models.report import ReportSchedule, GeneratedReport
from models.store import Store


class CommandType(str, Enum):
    """Types of chat commands."""
    REPORT_DAILY = "report_daily"
    REPORT_WEEKLY = "report_weekly"
    REPORT_MONTHLY = "report_monthly"
    REPORT_PROFIT = "report_profit"
    REPORT_SALES = "report_sales"
    REPORT_INVENTORY = "report_inventory"
    REPORT_STORE = "report_store"
    REPORT_PRODUCT = "report_product"
    REPORT_CLIENT = "report_client"
    SCHEDULE_REPORT = "schedule_report"
    CANCEL_SCHEDULE = "cancel_schedule"
    LIST_SCHEDULES = "list_schedules"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    """Result of parsing a chat command."""
    command_type: CommandType
    entities: Dict[str, Any]
    confidence: float
    original_text: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "command_type": self.command_type.value,
            "entities": self.entities,
            "confidence": self.confidence,
            "original_text": self.original_text
        }


@dataclass
class ChatResponse:
    """Response to a chat command."""
    success: bool
    message: str
    report_data: Optional[Dict[str, Any]] = None
    report_file_url: Optional[str] = None
    suggested_actions: List[str] = None
    
    def __post_init__(self):
        if self.suggested_actions is None:
            self.suggested_actions = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "report_data": self.report_data,
            "report_file_url": self.report_file_url,
            "suggested_actions": self.suggested_actions
        }


class ChatReportService:
    """
    Service for parsing chat commands and generating reports.
    
    Handles natural language queries like:
    - "Show today's profit"
    - "Yesterday's sales by store"
    - "Top 5 products by profit this month"
    - "Report daily"
    - "Report week"
    - "Report profit"
    - "Report store TX"
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize the chat report service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        
        # Command patterns with regex
        self.patterns: List[Tuple[Pattern, CommandType]] = [
            # Profit reports
            (re.compile(r'(?:show|get|give me|what(?:\'s| is))?[\s]*(?:today(?:\'s| )?|this day)?[\s]*profit', re.I), 
             CommandType.REPORT_PROFIT),
            (re.compile(r'profit\s+(?:for\s+)?(?:today|this day)', re.I), 
             CommandType.REPORT_PROFIT),
            (re.compile(r'profit\s+(?:for\s+)?(?:yesterday|last day)', re.I), 
             CommandType.REPORT_PROFIT),
            (re.compile(r'profit\s+(?:for\s+)?(?:this week|week)', re.I), 
             CommandType.REPORT_PROFIT),
            (re.compile(r'profit\s+(?:for\s+)?(?:this month|month)', re.I), 
             CommandType.REPORT_PROFIT),
            
            # Daily reports
            (re.compile(r'(?:show|get|give me)?[\s]*daily\s*report', re.I), 
             CommandType.REPORT_DAILY),
            (re.compile(r'report\s+daily', re.I), 
             CommandType.REPORT_DAILY),
            (re.compile(r'today(?:\'s| )?(?:sales)?\s*(?:report)?', re.I), 
             CommandType.REPORT_DAILY),
            (re.compile(r'yesterday(?:\'s| )?(?:sales)?\s*(?:report)?', re.I), 
             CommandType.REPORT_DAILY),
            
            # Weekly reports
            (re.compile(r'(?:show|get|give me)?[\s]*weekly\s*report', re.I), 
             CommandType.REPORT_WEEKLY),
            (re.compile(r'report\s+week(?:ly)?', re.I), 
             CommandType.REPORT_WEEKLY),
            (re.compile(r'this\s*week(?:\'s| )?(?:sales)?\s*(?:report)?', re.I), 
             CommandType.REPORT_WEEKLY),
            (re.compile(r'last\s*week(?:\'s| )?(?:sales)?\s*(?:report)?', re.I), 
             CommandType.REPORT_WEEKLY),
            
            # Monthly reports
            (re.compile(r'(?:show|get|give me)?[\s]*monthly\s*report', re.I), 
             CommandType.REPORT_MONTHLY),
            (re.compile(r'report\s+month(?:ly)?', re.I), 
             CommandType.REPORT_MONTHLY),
            (re.compile(r'this\s*month(?:\'s| )?(?:sales)?\s*(?:report)?', re.I), 
             CommandType.REPORT_MONTHLY),
            (re.compile(r'last\s*month(?:\'s| )?(?:sales)?\s*(?:report)?', re.I), 
             CommandType.REPORT_MONTHLY),
            
            # Sales reports
            (re.compile(r'(?:show|get|give me)?[\s]*sales\s*(?:report)?', re.I), 
             CommandType.REPORT_SALES),
            (re.compile(r'report\s+sales', re.I), 
             CommandType.REPORT_SALES),
            
            # Store-specific reports
            (re.compile(r'report\s+store\s+(\w+)', re.I), 
             CommandType.REPORT_STORE),
            (re.compile(r'(?:store|location)\s+[\'"]?(\w+)[\'"]?\s+(?:sales|profit|report)', re.I), 
             CommandType.REPORT_STORE),
            
            # Product reports
            (re.compile(r'(?:top|best)\s*(\d+)?\s*(?:products|items)\s+(?:by\s+)?(?:profit|sales)', re.I), 
             CommandType.REPORT_PRODUCT),
            (re.compile(r'report\s+product', re.I), 
             CommandType.REPORT_PRODUCT),
            
            # Client reports
            (re.compile(r'(?:client|customer)\s*(?:report|stats)', re.I), 
             CommandType.REPORT_CLIENT),
            
            # Inventory reports
            (re.compile(r'inventory\s*(?:report|status|level)', re.I), 
             CommandType.REPORT_INVENTORY),
            (re.compile(r'(?:low\s*stock|out\s*of\s*stock)', re.I), 
             CommandType.REPORT_INVENTORY),
            
            # Schedule commands
            (re.compile(r'schedule\s+(?:daily|weekly|monthly)\s+report', re.I), 
             CommandType.SCHEDULE_REPORT),
            (re.compile(r'(?:cancel|stop|remove)\s+schedule', re.I), 
             CommandType.CANCEL_SCHEDULE),
            (re.compile(r'(?:my\s+)?schedules?(?:\s+list)?', re.I), 
             CommandType.LIST_SCHEDULES),
            
            # Help
            (re.compile(r'(?:help|\?)', re.I), 
             CommandType.HELP),
        ]
        
        # Date entity patterns
        self.date_patterns = {
            'today': re.compile(r'today|this day|current day', re.I),
            'yesterday': re.compile(r'yesterday|last day|previous day', re.I),
            'this_week': re.compile(r'this week|current week', re.I),
            'last_week': re.compile(r'last week|previous week', re.I),
            'this_month': re.compile(r'this month|current month', re.I),
            'last_month': re.compile(r'last month|previous month', re.I),
        }
        
        # Number pattern for extracting quantities
        self.number_pattern = re.compile(r'\b(\d+)\b')
    
    def parse_command(self, message_text: str) -> ParsedCommand:
        """
        Parse a chat message into a structured command.
        
        Args:
            message_text: The user's message text
            
        Returns:
            ParsedCommand with command type and extracted entities
        """
        message_text = message_text.strip()
        
        # Try each pattern
        for pattern, command_type in self.patterns:
            match = pattern.search(message_text)
            if match:
                entities = self._extract_entities(message_text, match)
                
                # Calculate confidence based on match quality
                confidence = self._calculate_confidence(match, message_text)
                
                return ParsedCommand(
                    command_type=command_type,
                    entities=entities,
                    confidence=confidence,
                    original_text=message_text
                )
        
        # No pattern matched
        return ParsedCommand(
            command_type=CommandType.UNKNOWN,
            entities={"raw_text": message_text},
            confidence=0.0,
            original_text=message_text
        )
    
    def _extract_entities(
        self, 
        text: str, 
        match: re.Match
    ) -> Dict[str, Any]:
        """
        Extract entities from the matched text.
        
        Args:
            text: Full message text
            match: Regex match object
            
        Returns:
            Dictionary of extracted entities
        """
        entities = {}
        
        # Extract date/time references
        for date_name, pattern in self.date_patterns.items():
            if pattern.search(text):
                entities['date_ref'] = date_name
                break
        
        # Extract store name/code from capture groups
        if match.lastindex and match.lastindex >= 1:
            try:
                # First capture group might be a number (e.g., top 5 products)
                num_match = self.number_pattern.match(match.group(1))
                if num_match:
                    entities['limit'] = int(num_match.group(1))
                else:
                    # Otherwise it's likely a store code
                    entities['store_code'] = match.group(1)
            except IndexError:
                pass
        
        # Extract explicit numbers (e.g., "top 5 products")
        numbers = self.number_pattern.findall(text)
        if numbers:
            # Take the first number as limit if not already set
            if 'limit' not in entities:
                entities['limit'] = int(numbers[0])
        
        # Check for specific keywords
        text_lower = text.lower()
        if 'profit' in text_lower:
            entities['metric'] = 'profit'
        if 'sales' in text_lower or 'revenue' in text_lower:
            entities['metric'] = 'sales'
        if 'product' in text_lower or 'item' in text_lower:
            entities['entity_type'] = 'product'
        if 'store' in text_lower or 'location' in text_lower:
            entities['entity_type'] = 'store'
        
        return entities
    
    def _calculate_confidence(
        self, 
        match: re.Match, 
        text: str
    ) -> float:
        """
        Calculate confidence score for the match.
        
        Args:
            match: Regex match object
            text: Full message text
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence
        confidence = 0.7
        
        # Higher confidence if match covers more of the text
        match_ratio = len(match.group(0)) / len(text)
        confidence += min(0.3, match_ratio * 0.3)
        
        # Bonus for exact keyword matches
        if match.group(0).lower().strip() == text.lower().strip():
            confidence = min(1.0, confidence + 0.2)
        
        return min(1.0, confidence)
    
    def execute_command(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        user_id: str,
        store_id: Optional[str] = None
    ) -> ChatResponse:
        """
        Execute a parsed command and return the response.
        
        Args:
            parsed: Parsed command
            tenant_id: Tenant identifier
            user_id: User who sent the command
            store_id: Optional default store ID
            
        Returns:
            ChatResponse with results
        """
        if parsed.command_type == CommandType.UNKNOWN:
            return ChatResponse(
                success=False,
                message="I didn't understand that command. Try:\n"
                        "• \"Show today's profit\"\n"
                        "• \"Daily report\"\n"
                        "• \"Weekly sales\"\n"
                        "• \"Top 5 products\"\n"
                        "• \"Report store TX\"",
                suggested_actions=["help"]
            )
        
        elif parsed.command_type == CommandType.HELP:
            return self._handle_help()
        
        elif parsed.command_type == CommandType.REPORT_PROFIT:
            return self._handle_profit_report(
                parsed, tenant_id, store_id
            )
        
        elif parsed.command_type == CommandType.REPORT_DAILY:
            return self._handle_daily_report(
                parsed, tenant_id, store_id
            )
        
        elif parsed.command_type == CommandType.REPORT_WEEKLY:
            return self._handle_weekly_report(
                parsed, tenant_id, store_id
            )
        
        elif parsed.command_type == CommandType.REPORT_MONTHLY:
            return self._handle_monthly_report(
                parsed, tenant_id, store_id
            )
        
        elif parsed.command_type == CommandType.REPORT_STORE:
            return self._handle_store_report(
                parsed, tenant_id, store_id
            )
        
        elif parsed.command_type == CommandType.REPORT_PRODUCT:
            return self._handle_product_report(
                parsed, tenant_id, store_id
            )
        
        elif parsed.command_type == CommandType.SCHEDULE_REPORT:
            return self._handle_schedule_report(
                parsed, tenant_id, user_id, store_id
            )
        
        elif parsed.command_type == CommandType.LIST_SCHEDULES:
            return self._handle_list_schedules(
                tenant_id, user_id
            )
        
        else:
            return ChatResponse(
                success=False,
                message=f"Command '{parsed.command_type.value}' is not yet implemented.",
                suggested_actions=["help"]
            )
    
    def _handle_profit_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle profit report request."""
        from services.profit_service import ProfitService, ReportPeriod
        
        # Determine period from entities
        date_ref = parsed.entities.get('date_ref', 'today')
        
        if date_ref == 'yesterday':
            reference_date = datetime.utcnow() - timedelta(days=1)
            period = ReportPeriod.DAILY
        elif date_ref in ('this_week', 'last_week'):
            reference_date = datetime.utcnow()
            period = ReportPeriod.WEEKLY
            if date_ref == 'last_week':
                reference_date -= timedelta(weeks=1)
        elif date_ref in ('this_month', 'last_month'):
            reference_date = datetime.utcnow()
            period = ReportPeriod.MONTHLY
            if date_ref == 'last_month':
                reference_date = reference_date.replace(month=reference_date.month - 1)
        else:  # today
            reference_date = datetime.utcnow()
            period = ReportPeriod.DAILY
        
        profit_service = ProfitService(self.db)
        metrics = profit_service.compute_period_profit(
            tenant_id=tenant_id,
            period=period,
            reference_date=reference_date,
            store_id=store_id
        )
        
        # Format summary
        period_label = date_ref.replace('_', ' ')
        summary = (
            f"📊 *Profit Report - {period_label.title()}*\n\n"
            f"💰 Revenue: {metrics.total_revenue:,.2f}\n"
            f"📦 COGS: {metrics.total_cogs:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Gross Profit: {metrics.gross_profit:,.2f}\n"
            f"📈 Margin: {metrics.gross_margin_percent:.1f}%\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 Expenses: {metrics.total_expenses:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Net Profit: {metrics.net_profit:,.2f}\n"
            f"📊 Net Margin: {metrics.net_margin_percent:.1f}%"
        )
        
        return ChatResponse(
            success=True,
            message=summary,
            report_data=metrics.to_dict(),
            suggested_actions=[
                "View detailed breakdown",
                "Compare with last period",
                "Export to PDF"
            ]
        )
    
    def _handle_daily_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle daily report request."""
        from services.profit_service import ProfitService, ReportPeriod
        
        profit_service = ProfitService(self.db)
        metrics = profit_service.compute_period_profit(
            tenant_id=tenant_id,
            period=ReportPeriod.DAILY,
            reference_date=datetime.utcnow(),
            store_id=store_id
        )
        
        summary = (
            f"📅 *Daily Sales Report*\n\n"
            f"🛒 Transactions: {metrics.total_sales_count}\n"
            f"💵 Total Revenue: {metrics.total_revenue:,.2f}\n"
            f"🏷️ Tax Collected: {metrics.tax_collected:,.2f}\n"
            f"🎁 Discounts: {metrics.discounts_given:,.2f}\n"
            f"📦 COGS: {metrics.total_cogs:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Gross Profit: {metrics.gross_profit:,.2f}\n"
            f"📈 Margin: {metrics.gross_margin_percent:.1f}%"
        )
        
        return ChatResponse(
            success=True,
            message=summary,
            report_data=metrics.to_dict()
        )
    
    def _handle_weekly_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle weekly report request."""
        from services.profit_service import ProfitService, ReportPeriod
        
        profit_service = ProfitService(self.db)
        metrics = profit_service.compute_period_profit(
            tenant_id=tenant_id,
            period=ReportPeriod.WEEKLY,
            reference_date=datetime.utcnow(),
            store_id=store_id
        )
        
        summary = (
            f"📅 *Weekly Report*\n\n"
            f"🛒 Total Transactions: {metrics.total_sales_count}\n"
            f"💵 Revenue: {metrics.total_revenue:,.2f}\n"
            f"💰 Gross Profit: {metrics.gross_profit:,.2f}\n"
            f"💸 Expenses: {metrics.total_expenses:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Net Profit: {metrics.net_profit:,.2f}\n"
            f"📊 Net Margin: {metrics.net_margin_percent:.1f}%"
        )
        
        return ChatResponse(
            success=True,
            message=summary,
            report_data=metrics.to_dict()
        )
    
    def _handle_monthly_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle monthly report request."""
        from services.profit_service import ProfitService, ReportPeriod
        
        profit_service = ProfitService(self.db)
        metrics = profit_service.compute_period_profit(
            tenant_id=tenant_id,
            period=ReportPeriod.MONTHLY,
            reference_date=datetime.utcnow(),
            store_id=store_id
        )
        
        summary = (
            f"📅 *Monthly Report*\n\n"
            f"🛒 Total Transactions: {metrics.total_sales_count}\n"
            f"💵 Revenue: {metrics.total_revenue:,.2f}\n"
            f"💰 Gross Profit: {metrics.gross_profit:,.2f}\n"
            f"💸 Expenses: {metrics.total_expenses:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Net Profit: {metrics.net_profit:,.2f}\n"
            f"📊 Net Margin: {metrics.net_margin_percent:.1f}%"
        )
        
        return ChatResponse(
            success=True,
            message=summary,
            report_data=metrics.to_dict()
        )
    
    def _handle_store_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle store-specific report request."""
        store_code = parsed.entities.get('store_code')
        
        if not store_code:
            return ChatResponse(
                success=False,
                message="Please specify a store code. Example: \"Report store TX\""
            )
        
        # Find store by code
        store = self.db.query(Store).filter(
            Store.tenant_id == tenant_id,
            Store.code.ilike(f"%{store_code}%")
        ).first()
        
        if not store:
            return ChatResponse(
                success=False,
                message=f"Store '{store_code}' not found."
            )
        
        from services.profit_service import ProfitService, ReportPeriod
        
        profit_service = ProfitService(self.db)
        metrics = profit_service.compute_period_profit(
            tenant_id=tenant_id,
            period=ReportPeriod.DAILY,
            reference_date=datetime.utcnow(),
            store_id=store.id
        )
        
        summary = (
            f"🏪 *Store Report: {store.name}*\n\n"
            f"📅 Today's Performance:\n"
            f"🛒 Transactions: {metrics.total_sales_count}\n"
            f"💵 Revenue: {metrics.total_revenue:,.2f}\n"
            f"💰 Profit: {metrics.net_profit:,.2f}\n"
            f"📈 Margin: {metrics.net_margin_percent:.1f}%"
        )
        
        return ChatResponse(
            success=True,
            message=summary,
            report_data={**metrics.to_dict(), "store_name": store.name}
        )
    
    def _handle_product_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle top products report request."""
        from services.profit_service import ProfitService, ReportPeriod
        
        limit = parsed.entities.get('limit', 5)
        
        profit_service = ProfitService(self.db)
        top_products = profit_service.get_product_profit_breakdown(
            tenant_id=tenant_id,
            period=ReportPeriod.DAILY,
            reference_date=datetime.utcnow(),
            store_id=store_id,
            limit=limit,
            sort_by='gross_profit'
        )
        
        if not top_products:
            return ChatResponse(
                success=False,
                message="No product data available for today."
            )
        
        lines = [f"🏆 *Top {len(top_products)} Products by Profit*\n"]
        for i, product in enumerate(top_products, 1):
            lines.append(
                f"{i}. {product.product_name}\n"
                f"   💰 Profit: {product.gross_profit:,.2f}\n"
                f"   📈 Margin: {product.profit_margin_percent:.1f}%"
            )
        
        summary = "\n\n".join(lines)
        
        return ChatResponse(
            success=True,
            message=summary,
            report_data={
                "products": [p.to_dict() for p in top_products]
            }
        )
    
    def _handle_schedule_report(
        self,
        parsed: ParsedCommand,
        tenant_id: str,
        user_id: str,
        store_id: Optional[str]
    ) -> ChatResponse:
        """Handle schedule report request."""
        # Extract frequency from command
        text_lower = parsed.original_text.lower()
        if 'daily' in text_lower:
            frequency = 'daily'
        elif 'weekly' in text_lower:
            frequency = 'weekly'
        elif 'monthly' in text_lower:
            frequency = 'monthly'
        else:
            frequency = 'daily'  # Default
        
        # Create schedule
        schedule = ReportSchedule(
            tenant_id=tenant_id,
            user_id=user_id,
            store_id=store_id,
            report_type='daily_profit',
            frequency=frequency,
            delivery_method='in_app',
            is_active=True
        )
        
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        
        return ChatResponse(
            success=True,
            message=f"✅ Report scheduled successfully!\n\n"
                    f"📅 Frequency: {frequency.title()}\n"
                    f"📬 Delivery: In-app notification\n\n"
                    f"You'll receive your reports automatically.",
            suggested_actions=[
                "View my schedules",
                "Change delivery method",
                "Cancel schedule"
            ]
        )
    
    def _handle_list_schedules(
        self,
        tenant_id: str,
        user_id: str
    ) -> ChatResponse:
        """Handle list schedules request."""
        schedules = self.db.query(ReportSchedule).filter(
            ReportSchedule.tenant_id == tenant_id,
            ReportSchedule.user_id == user_id,
            ReportSchedule.is_active == True
        ).all()
        
        if not schedules:
            return ChatResponse(
                success=True,
                message="You have no active report schedules.\n\n"
                        "To schedule a report, say:\n"
                        "• \"Schedule daily report\"\n"
                        "• \"Schedule weekly report\"\n"
                        "• \"Schedule monthly report\""
            )
        
        lines = ["📅 *Your Scheduled Reports*\n"]
        for schedule in schedules:
            lines.append(
                f"• {schedule.report_type.replace('_', ' ').title()}\n"
                f"  🔄 {schedule.frequency.title()}\n"
                f"  📬 {schedule.delivery_method.replace('_', ' ').title()}"
            )
        
        summary = "\n\n".join(lines)
        
        return ChatResponse(
            success=True,
            message=summary,
            suggested_actions=[
                "Cancel a schedule",
                "Create new schedule"
            ]
        )
    
    def _handle_help(self) -> ChatResponse:
        """Handle help request."""
        help_text = (
            "👋 *POS Assistant - Available Commands*\n\n"
            "*Quick Reports:*\n"
            "• \"Show today's profit\" - Today's profit summary\n"
            "• \"Daily report\" - Today's sales report\n"
            "• \"Weekly report\" - This week's performance\n"
            "• \"Monthly report\" - This month's summary\n"
            "• \"Report store TX\" - Report for specific store\n"
            "• \"Top 5 products\" - Best selling products\n\n"
            "*Scheduling:*\n"
            "• \"Schedule daily report\" - Get daily reports\n"
            "• \"Schedule weekly report\" - Get weekly reports\n"
            "• \"My schedules\" - View scheduled reports\n\n"
            "*Examples:*\n"
            "• \"What's the profit today?\"\n"
            "• \"Yesterday's sales by store\"\n"
            "• \"Top 10 products by profit this month\""
        )
        
        return ChatResponse(
            success=True,
            message=help_text,
            suggested_actions=[
                "Show today's profit",
                "Daily report",
                "Schedule daily report"
            ]
        )
    
    def process_chat_message(
        self,
        message_text: str,
        tenant_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        store_id: Optional[str] = None
    ) -> ChatResponse:
        """
        Process a complete chat message and return response.
        
        This is the main entry point for chat-based reporting.
        
        Args:
            message_text: User's message
            tenant_id: Tenant identifier
            user_id: User identifier
            conversation_id: Optional conversation ID
            store_id: Optional default store ID
            
        Returns:
            ChatResponse with the assistant's reply
        """
        # Parse the command
        parsed = self.parse_command(message_text)
        
        # Save user message if conversation exists
        if conversation_id:
            user_message = ChatMessage(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                message_type='user',
                content=message_text,
                command_type=parsed.command_type.value if parsed.command_type != CommandType.UNKNOWN else None,
                entities=parsed.entities
            )
            self.db.add(user_message)
            self.db.commit()
        
        # Execute the command
        response = self.execute_command(
            parsed, tenant_id, user_id, store_id
        )
        
        # Save assistant response if conversation exists
        if conversation_id and response.success:
            assistant_message = ChatMessage(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                message_type='assistant',
                content=response.message,
                report_data=response.report_data,
                report_file_url=response.report_file_url
            )
            self.db.add(assistant_message)
            self.db.commit()
        
        return response
