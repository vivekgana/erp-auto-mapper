"""Canonical Data Model entities for audit-critical financial data.

Defines 10 CDM entities that unify ERP-specific schemas into a single
representation suitable for automated audit analysis.  All entities carry
SCD Type 2 temporal fields (valid_from / valid_to / is_current) and a
source_key_map that traces every CDM record back to its ERP-native key(s).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------

class PartyType(str, Enum):
    CUSTOMER = "customer"
    VENDOR = "vendor"
    EMPLOYEE = "employee"


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class PurchaseOrderStatus(str, Enum):
    OPEN = "open"
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class PaymentMethod(str, Enum):
    WIRE = "wire"
    CHECK = "check"
    ACH = "ach"
    CREDIT_CARD = "credit_card"
    CASH = "cash"
    OTHER = "other"


class OrganizationType(str, Enum):
    COMPANY = "company"
    DIVISION = "division"
    DEPARTMENT = "department"
    BRANCH = "branch"
    LEGAL_ENTITY = "legal_entity"


# ---------------------------------------------------------------------------
# Base CDM mixin
# ---------------------------------------------------------------------------

class CDMBase(BaseModel):
    """Common fields shared by every CDM entity (SCD Type 2)."""

    id: str = Field(..., description="CDM-generated surrogate key (UUID).")
    source_key_map: dict[str, str] = Field(
        default_factory=dict,
        description="Maps ERP source name to the original primary key value.",
    )
    valid_from: str | None = Field(
        default=None,
        description="Start of the validity window (SCD2).",
    )
    valid_to: str | None = Field(
        default=None,
        description="End of the validity window; None means currently active.",
    )
    is_current: bool = Field(
        default=True,
        description="Convenience flag: True when this is the active version.",
    )
    created_at: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# 1. Party (unifies Customer / Vendor / Employee)
# ---------------------------------------------------------------------------

class ContactInfo(BaseModel):
    email: str | None = None
    phone: str | None = None
    fax: str | None = None


class Address(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class Party(CDMBase):
    """Unified party entity — customers, vendors, and employees."""

    name: str
    party_type: PartyType
    tax_id: str | None = None
    address: Address | None = None
    contact_info: ContactInfo | None = None


# ---------------------------------------------------------------------------
# 2. Account (Chart of Accounts)
# ---------------------------------------------------------------------------

class Account(CDMBase):
    """General-ledger account with hierarchy support."""

    account_number: str
    account_name: str
    account_type: AccountType
    parent_id: str | None = Field(
        default=None, description="Parent account ID for hierarchy."
    )
    level: int = Field(default=0, description="Depth in the account hierarchy.")
    currency: str = "USD"
    is_active: bool = True


# ---------------------------------------------------------------------------
# 3. LedgerEntry
# ---------------------------------------------------------------------------

class LedgerEntry(CDMBase):
    """Single posted ledger entry (after journals are posted)."""

    ledger_id: str
    account_id: str
    posting_date: datetime.date
    period: str = Field(..., description="Fiscal period, e.g. '2026-Q1'.")
    company_code: str
    amount: Decimal
    currency: str = "USD"
    description: str = ""


# ---------------------------------------------------------------------------
# 4. JournalEntry + Line Items
# ---------------------------------------------------------------------------

class JournalEntryLine(BaseModel):
    """Single debit/credit line within a journal entry."""

    line_number: int
    account_id: str
    debit_amount: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    currency: str = "USD"
    description: str = ""
    cost_center_id: str | None = None


class JournalEntry(CDMBase):
    """Multi-line journal entry (pre- or post-posting)."""

    entry_id: str
    ledger_id: str
    posting_date: datetime.date
    period: str
    company_code: str
    description: str = ""
    line_items: list[JournalEntryLine] = Field(default_factory=list)
    is_posted: bool = False
    created_by: str = ""


# ---------------------------------------------------------------------------
# 5. TrialBalance
# ---------------------------------------------------------------------------

class TrialBalance(CDMBase):
    """Period-level trial balance row per account."""

    period: str
    company_code: str
    account_id: str
    opening_balance: Decimal = Decimal("0")
    debit_total: Decimal = Decimal("0")
    credit_total: Decimal = Decimal("0")
    closing_balance: Decimal = Decimal("0")
    currency: str = "USD"


# ---------------------------------------------------------------------------
# 6. Invoice + Line Items
# ---------------------------------------------------------------------------

class InvoiceLineItem(BaseModel):
    """Single line on an invoice."""

    line_number: int
    description: str = ""
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    account_id: str | None = None
    tax_amount: Decimal = Decimal("0")


class Invoice(CDMBase):
    """Accounts-payable or accounts-receivable invoice."""

    invoice_number: str
    vendor_id: str | None = None
    customer_id: str | None = None
    amount: Decimal
    currency: str = "USD"
    issue_date: datetime.date | None = None
    due_date: datetime.date | None = None
    status: InvoiceStatus = InvoiceStatus.OPEN
    line_items: list[InvoiceLineItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 7. Payment
# ---------------------------------------------------------------------------

class Payment(CDMBase):
    """Payment against an invoice."""

    payment_id: str
    invoice_id: str | None = None
    amount: Decimal
    currency: str = "USD"
    payment_date: datetime.date
    method: PaymentMethod = PaymentMethod.WIRE
    reference: str = ""


# ---------------------------------------------------------------------------
# 8. PurchaseOrder + Line Items
# ---------------------------------------------------------------------------

class PurchaseOrderLine(BaseModel):
    """Single line on a purchase order."""

    line_number: int
    description: str = ""
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    account_id: str | None = None


class PurchaseOrder(CDMBase):
    """Purchase order header with line items."""

    po_number: str
    vendor_id: str
    order_date: datetime.date
    status: PurchaseOrderStatus = PurchaseOrderStatus.OPEN
    total_amount: Decimal = Decimal("0")
    currency: str = "USD"
    line_items: list[PurchaseOrderLine] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 9. CostCenter
# ---------------------------------------------------------------------------

class CostCenter(CDMBase):
    """Organisational cost center with hierarchy."""

    code: str
    name: str
    parent_id: str | None = None
    level: int = 0
    responsible_person: str | None = None
    is_active: bool = True


# ---------------------------------------------------------------------------
# 10. Organisation
# ---------------------------------------------------------------------------

class Organization(CDMBase):
    """Legal entity / organisational unit."""

    org_id: str
    name: str
    org_type: OrganizationType = OrganizationType.COMPANY
    parent_id: str | None = None
    country_code: str = ""
    currency_code: str = "USD"


# ---------------------------------------------------------------------------
# Convenience collection of all entity classes
# ---------------------------------------------------------------------------

ALL_CDM_ENTITIES: dict[str, type[CDMBase]] = {
    "Party": Party,
    "Account": Account,
    "LedgerEntry": LedgerEntry,
    "JournalEntry": JournalEntry,
    "TrialBalance": TrialBalance,
    "Invoice": Invoice,
    "Payment": Payment,
    "PurchaseOrder": PurchaseOrder,
    "CostCenter": CostCenter,
    "Organization": Organization,
}
