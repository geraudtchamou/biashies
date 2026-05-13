# African POS & Business Management System - Architecture Overview

## 1. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD INFRASTRUCTURE                                │
│                                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │   Load Balancer │───▶│   API Gateway   │───▶│   Modular Monolith Backend  │  │
│  │   (nginx/ALB)   │    │  (Auth/Ratelimit)│    │   (Rust + Django + FastAPI) │  │
│  └─────────────────┘    └─────────────────┘    └──────────────┬──────────────┘  │
│                                                               │                   │
│                    ┌──────────────────────────────────────────┼──────────────┐  │
│                    │                                          │              │  │
│                    ▼                                          ▼              │  │
│  ┌─────────────────────────┐                 ┌──────────────────────────────┐ │  │
│  │   Sync Service          │                 │   PostgreSQL Database        │ │  │
│  │   - Delta ingestion     │◀───────────────▶│   - Core data                │ │  │
│  │   - Conflict resolution │                 │   - Tenant isolation         │ │  │
│  │   - Queue management    │                 │   - Read replica (optional)  │ │  │
│  └─────────────────────────┘                 └──────────────────────────────┘ │  │
│                    │                                                           │
│                    ▼                                                           │
│  ┌─────────────────────────┐                 ┌──────────────────────────────┐ │  │
│  │   Background Workers    │                 │   Message Queue (Redis/SQS)  │ │  │
│  │   - Profit computation  │◀───────────────▶│   - Async tasks              │ │  │
│  │   - Report generation   │                 │   - Event streaming          │ │  │
│  │   - Loyalty processing  │                 └──────────────────────────────┘ │  │
│  │   - WhatsApp/SMS sender │                                                   │  │
│  └─────────────────────────┘                                                   │  │
│                    │                                                           │
│                    ▼                                                           │
│  ┌─────────────────────────┐                                                   │  │
│  │   WhatsApp/SMS Gateway  │◀───────────▶ External APIs                        │  │
│  │   - Twilio/WhatsApp API │                                                   │  │
│  └─────────────────────────┘                                                   │  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ HTTPS/WebSocket
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
        ┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
        │  Flutter Mobile │ │ Flutter     │ │  Web Dashboard  │
        │  (Android/iOS)  │ │ Tablet POS  │ │  (Admin Panel)  │
        │                 │ │             │ │                 │
        │ ┌─────────────┐ │ │ ┌─────────┐ │ │                 │
        │ │ SQLite DB   │ │ │ │ SQLite  │ │ │                 │
        │ │ - Local cache│ │ │ │ DB      │ │ │                 │
        │ │ - Offline ops│ │ │ │         │ │ │                 │
        │ │ - Sync queue│ │ │ │         │ │ │                 │
        │ └─────────────┘ │ │ └─────────┘ │ │                 │
        │                 │ │             │ │                 │
        │ Offline-first   │ │ Offline-    │ │ Online-only     │
        │ capabilities    │ │ first       │ │ reporting       │
        └─────────────────┘ └─────────────┘ └─────────────────┘
```

## 2. Data Flow Architecture

### 2.1 Offline-First Sync Pattern

```
┌──────────────────────────────────────────────────────────────────┐
│                      MOBILE CLIENT (Flutter)                      │
│                                                                   │
│  User Action (Sale/Inventory/Expense)                             │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                             │
│  │ Local SQLite DB │ ◀─── Write immediately (offline-capable)    │
│  └─────────────────┘                                             │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                             │
│  │ Sync Queue Table│ ◀─── Queue pending changes                  │
│  └─────────────────┘                                             │
│         │                                                         │
│         │ [Network Available]                                     │
│         ▼                                                         │
│  ┌─────────────────┐                                             │
│  │ Sync Engine     │                                             │
│  │ - Batch deltas  │                                             │
│  │ - Retry logic   │                                             │
│  │ - Conflict detect│                                            │
│  └─────────────────┘                                             │
│         │                                                         │
│         │ POST /sync/push                                        │
│         ▼                                                         │
└──────────────────────────────────────────────────────────────────┘
         │
         │ Cloud Processing
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                      CLOUD SYNC SERVICE                           │
│                                                                   │
│  ┌─────────────────┐                                             │
│  │ Delta Validator │                                             │
│  └─────────────────┘                                             │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                             │
│  │ Conflict Resolver│ ◀─── Last-write-wins + audit trail         │
│  └─────────────────┘                                             │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                             │
│  │ Apply to PostgreSQL│                                          │
│  └─────────────────┘                                             │
│         │                                                         │
│         │ GET /sync/pull                                         │
│         ▼                                                         │
└──────────────────────────────────────────────────────────────────┘
         │
         │ Return updated data
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                      MOBILE CLIENT                                │
│                                                                   │
│  ┌─────────────────┐                                             │
│  │ Update Local DB │ ◀─── Merge cloud changes                    │
│  └─────────────────┘                                             │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                             │
│  │ Clear Sync Queue│                                             │
│  └─────────────────┘                                             │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Multi-Tenancy Model

```
PostgreSQL Schema: Single Database with tenant_id isolation

┌─────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Trader A     │  │ Trader B     │  │ Trader C     │          │
│  │ tenant_id=1  │  │ tenant_id=2  │  │ tenant_id=3  │          │
│  │              │  │              │  │              │          │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │          │
│  │ │ Store 1  │ │  │ │ Store 1  │ │  │ │ Store 1  │ │          │
│  │ │ Store 2  │ │  │ │ Store 2  │ │  │ │ Store 2  │ │          │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │          │
│  │              │  │              │  │              │          │
│  │ • Products   │  │ • Products   │  │ • Products   │          │
│  │ • Sales      │  │ • Sales      │  │ • Sales      │          │
│  │ • Clients    │  │ • Clients    │  │ • Clients    │          │
│  │ • Expenses   │  │ • Expenses   │  │ • Expenses   │          │
│  │ • Loyalty    │  │ • Loyalty    │  │ • Loyalty    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  All queries filtered by: WHERE tenant_id = current_tenant_id   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Technology Stack Details

### 3.1 Backend Architecture (Modular Monolith)

```
backend/
├── src/
│   ├── main.rs              # Rust entry point
│   ├── lib.rs               # Library exports
│   │
│   ├── api/                 # API Layer (FastAPI + Django REST)
│   │   ├── routes/
│   │   │   ├── auth.py      # Authentication endpoints
│   │   │   ├── stores.py    # Store management
│   │   │   ├── products.py  # Product catalog
│   │   │   ├── sales.py     # POS transactions
│   │   │   ├── purchases.py # Supplier management
│   │   │   ├── expenses.py  # Expense tracking
│   │   │   ├── clients.py   # CRM endpoints
│   │   │   ├── loyalty.py   # Loyalty program
│   │   │   ├── reports.py   # Analytics & reports
│   │   │   ├── chat.py      # Chat-based reporting
│   │   │   └── sync.py      # Sync endpoints
│   │   ├── middleware/
│   │   │   ├── auth.py      # JWT/OAuth2 middleware
│   │   │   ├── tenant.py    # Tenant isolation
│   │   │   └── rate_limit.py
│   │   └── schemas/         # Pydantic models
│   │
│   ├── services/            # Business Logic
│   │   ├── store_service.py
│   │   ├── product_service.py
│   │   ├── sale_service.py
│   │   ├── purchase_service.py
│   │   ├── expense_service.py
│   │   ├── client_service.py
│   │   ├── loyalty_service.py    # Points, tiers, rewards
│   │   ├── profit_service.py     # Profit computation
│   │   ├── report_service.py     # Report generation
│   │   ├── chat_report_service.py # Chat command parsing
│   │   └── sync_service.py       # Sync logic
│   │
│   ├── models/              # SQLAlchemy/Django ORM Models
│   │   ├── user.py
│   │   ├── store.py
│   │   ├── product.py
│   │   ├── sale.py
│   │   ├── purchase.py
│   │   ├── expense.py
│   │   ├── client.py
│   │   ├── loyalty.py
│   │   └── report.py
│   │
│   ├── workers/             # Background Jobs (Celery)
│   │   ├── profit_worker.py      # Daily profit computation
│   │   ├── report_worker.py      # Scheduled reports
│   │   ├── loyalty_worker.py     # Tier upgrades
│   │   └── notification_worker.py # WhatsApp/SMS sender
│   │
│   ├── sync/                # Sync Engine
│   │   ├── delta_processor.py
│   │   ├── conflict_resolver.py
│   │   └── replication.py
│   │
│   └── utils/
│       ├── currency.py      # Multi-currency handling
│       ├── tax_calculator.py
│       ├── pdf_generator.py
│       └── qr_generator.py
│
├── tests/
├── migrations/
├── config/
│   ├── settings.py
│   └── database.py
└── requirements.txt
```

### 3.2 Flutter Mobile Architecture

```
lib/
├── main.dart
├── core/
│   ├── constants/
│   │   ├── currencies.dart    # XAF, XOF, NGN, GHS, KES, TZS, ZAR
│   │   ├── languages.dart     # EN, FR, PT, SW
│   │   └── permissions.dart
│   ├── database/
│   │   ├── local_db.dart      # SQLite helper
│   │   ├── tables/
│   │   │   ├── products_table.dart
│   │   │   ├── sales_table.dart
│   │   │   └── ...
│   │   └── migrations/
│   ├── network/
│   │   ├── api_client.dart
│   │   ├── sync_engine.dart   # Offline/online sync
│   │   └── interceptors/
│   ├── utils/
│   │   ├── currency_formatter.dart
│   │   ├── date_utils.dart
│   │   └── validators.dart
│   └── widgets/
│       ├── common/
│       └── pos/
│
├── features/
│   ├── auth/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   ├── stores/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   ├── pos/
│   │   ├── screens/
│   │   │   ├── sale_screen.dart
│   │   │   ├── cart_screen.dart
│   │   │   └── payment_screen.dart
│   │   ├── widgets/
│   │   └── bloc/
│   ├── inventory/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   ├── clients/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   ├── loyalty/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   ├── expenses/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   ├── reports/
│   │   ├── screens/
│   │   ├── widgets/
│   │   └── bloc/
│   └── chat/
│       ├── screens/
│       ├── widgets/
│       └── bloc/
│
├── models/
│   ├── user.dart
│   ├── store.dart
│   ├── product.dart
│   ├── sale.dart
│   ├── client.dart
│   └── ...
│
└── services/
    ├── auth_service.dart
    ├── sync_service.dart
    ├── report_service.dart
    └── notification_service.dart
```

## 4. Key Design Decisions

### 4.1 Why Modular Monolith?
- **Simplicity**: Easier to deploy and maintain for SME market
- **Cost-effective**: Single database, no distributed transaction complexity
- **Scalability**: Can split into microservices later when needed
- **Clear boundaries**: Each module (Store, CRM, Inventory, Sales, Loyalty) has well-defined interfaces

### 4.2 Why SQLite on Mobile?
- **True offline**: All operations work without network
- **Performance**: Local queries are instant
- **Maturity**: Well-tested, ACID-compliant
- **Sync-friendly**: Easy to track deltas and conflicts

### 4.3 Conflict Resolution Strategy
```
1. Last-write-wins (based on timestamp)
2. Audit trail preserved for all changes
3. Manual resolution UI for critical conflicts (e.g., inventory adjustments)
4. Server-side validation before applying changes
```

### 4.4 Security Model
- **Authentication**: Email/Phone + OTP (SMS)
- **Authorization**: Role-based (Admin, Cashier, Inventory Manager, Sales Rep)
- **Data isolation**: tenant_id on all tables
- **Encryption**: 
  - TLS in transit
  - AES-256 at rest (database encryption)
  - Local database encrypted on device
- **Audit trail**: All creates/updates/deletes logged

## 5. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      AWS/GCP/Azure                               │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   VPC       │    │   VPC       │    │   VPC       │         │
│  │   (West)    │    │   (East)    │    │   (Central) │         │
│  │             │    │             │    │             │         │
│  │ ┌─────────┐ │    │ ┌─────────┐ │    │ ┌─────────┐ │         │
│  │ │ API     │ │    │ │ API     │ │    │ │ API     │ │         │
│  │ │ Servers │ │    │ │ Servers │ │    │ │ Servers │ │         │
│  │ └─────────┘ │    │ └─────────┘ │    │ └─────────┘ │         │
│  │             │    │             │    │             │         │
│  │ ┌─────────┐ │    │ ┌─────────┐ │    │ ┌─────────┐ │         │
│  │ │ DB      │ │    │ │ DB      │ │    │ │ DB      │ │         │
│  │ │ Primary │ │    │ │ Primary │ │    │ │ Primary │ │         │
│  │ └─────────┘ │    │ └─────────┘ │    │ └─────────┘ │         │
│  │             │    │             │    │             │         │
│  │ ┌─────────┐ │    │ ┌─────────┐ │    │ ┌─────────┐ │         │
│  │ │ Workers │ │    │ │ Workers │ │    │ │ Workers │ │         │
│  │ └─────────┘ │    │ └─────────┘ │    │ └─────────┘ │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Global Services                              │   │
│  │  - CDN for static assets                                 │   │
│  │  - WhatsApp/SMS Gateway                                  │   │
│  │  - Monitoring (Prometheus/Grafana)                       │   │
│  │  - Logging (ELK Stack)                                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 6. API Endpoints Overview

### Authentication
```
POST   /api/v1/auth/register          # Register new trader
POST   /api/v1/auth/login             # Login with email/phone
POST   /api/v1/auth/otp/request       # Request OTP
POST   /api/v1/auth/otp/verify        # Verify OTP
POST   /api/v1/auth/refresh           # Refresh token
POST   /api/v1/auth/logout            # Logout
```

### Stores
```
GET    /api/v1/stores                 # List stores
POST   /api/v1/stores                 # Create store
GET    /api/v1/stores/:id             # Get store details
PUT    /api/v1/stores/:id             # Update store
DELETE /api/v1/stores/:id             # Delete store
GET    /api/v1/stores/:id/stats       # Store statistics
```

### Products & Inventory
```
GET    /api/v1/products               # List products
POST   /api/v1/products               # Create product
GET    /api/v1/products/:id           # Get product
PUT    /api/v1/products/:id           # Update product
DELETE /api/v1/products/:id           # Delete product
POST   /api/v1/products/:id/variants  # Add variant
POST   /api/v1/products/barcode/scan  # Scan barcode
GET    /api/v1/inventory/low-stock    # Low stock alerts
POST   /api/v1/inventory/adjust       # Adjust stock
```

### Sales
```
POST   /api/v1/sales                  # Create sale
GET    /api/v1/sales                  # List sales
GET    /api/v1/sales/:id              # Get sale details
POST   /api/v1/sales/:id/void         # Void sale
POST   /api/v1/sales/:id/refund       # Refund sale
GET    /api/v1/sales/receipt/:id      # Generate receipt (PDF/PNG)
```

### Clients (CRM)
```
GET    /api/v1/clients                # List clients
POST   /api/v1/clients                # Add client
GET    /api/v1/clients/:id            # Get client
PUT    /api/v1/clients/:id            # Update client
GET    /api/v1/clients/:id/history    # Purchase history
GET    /api/v1/clients/:id/credit     # Credit balance
POST   /api/v1/clients/import         # Import CSV
POST   /api/v1/clients/export         # Export CSV
```

### Loyalty
```
GET    /api/v1/loyalty/program        # Get loyalty program
POST   /api/v1/loyalty/program        # Configure program
GET    /api/v1/loyalty/tiers          # List tiers
POST   /api/v1/loyalty/tiers          # Create tier
GET    /api/v1/loyalty/client/:id     # Client points & tier
POST   /api/v1/loyalty/earn           # Record points earned
POST   /api/v1/loyalty/redeem         # Redeem points
```

### Expenses
```
GET    /api/v1/expenses               # List expenses
POST   /api/v1/expenses               # Add expense
GET    /api/v1/expenses/:id           # Get expense
PUT    /api/v1/expenses/:id           # Update expense
DELETE /api/v1/expenses/:id           # Delete expense
GET    /api/v1/expenses/categories    # List categories
```

### Reports
```
GET    /api/v1/reports/sales/daily    # Daily sales report
GET    /api/v1/reports/sales/weekly   # Weekly sales report
GET    /api/v1/reports/sales/monthly  # Monthly sales report
GET    /api/v1/reports/profit/daily   # Daily profit
GET    /api/v1/reports/profit/weekly  # Weekly profit
GET    /api/v1/reports/inventory      # Inventory report
GET    /api/v1/reports/debts          # Overdue debts
POST   /api/v1/reports/export         # Export report (CSV/PDF)
```

### Chat-Based Reporting
```
POST   /api/v1/chat/message           # Send chat command
GET    /api/v1/chat/history           # Chat history
POST   /api/v1/chat/report/schedule   # Schedule report
```

### Sync
```
POST   /api/v1/sync/push              # Push local changes
GET    /api/v1/sync/pull              # Pull cloud updates
GET    /api/v1/sync/status            # Sync status
```

## 7. Supported African Currencies

```dart
enum AfricanCurrency {
  XAF('Central African CFA franc', 'FCFA', ['CM', 'CF', 'TD', 'CG', 'GQ', 'GA']),
  XOF('West African CFA franc', 'CFA', ['BJ', 'BF', 'CI', 'GW', 'ML', 'NE', 'SN', 'TG']),
  NGN('Nigerian Naira', '₦', ['NG']),
  GHS('Ghanaian Cedi', '₵', ['GH']),
  KES('Kenyan Shilling', 'KSh', ['KE']),
  TZS('Tanzanian Shilling', 'TSh', ['TZ']),
  ZAR('South African Rand', 'R', ['ZA']),
  UGX('Ugandan Shilling', 'USh', ['UG']),
  RWF('Rwandan Franc', 'FRw', ['RW']),
  ETB('Ethiopian Birr', 'Br', ['ET']),
  MAD('Moroccan Dirham', 'DH', ['MA']),
  DZD('Algerian Dinar', 'DA', ['DZ']),
  XCD('East Caribbean Dollar', '\$', ['AG', 'DM', 'GD', 'KN', 'LC', 'VC']),
  MZN('Mozambican Metical', 'MT', ['MZ']),
  AOA('Angolan Kwanza', 'Kz', ['AO']),
  ZMW('Zambian Kwacha', 'ZK', ['ZM']),
  BWP('Botswana Pula', 'P', ['BW']),
  MUR('Mauritian Rupee', '₨', ['MU']),
  SCR('Seychellois Rupee', '₨', ['SC']),
  USD('US Dollar', '\$', ['SS', 'SO', 'ER']), // Common alternative
}
```

## 8. Supported Languages

```dart
enum AppLanguage {
  en('English', 'en_US'),
  fr('Français', 'fr_FR'),
  pt('Português', 'pt_PT'),
  sw('Kiswahili', 'sw_KE'),
  ha('Hausa', 'ha_NG'),
  yo('Yorùbá', 'yo_NG'),
  ig('Igbo', 'ig_NG'),
  am('አማርኛ', 'am_ET'),
}
```

This architecture provides a robust, scalable foundation for an African-focused POS system that works offline-first, supports multiple currencies and languages, and includes advanced features like loyalty programs, chat-based reporting, and WhatsApp integration.
