"""Canonical Data Model — unified audit-critical entity definitions."""

from __future__ import annotations

from erp_auto_mapper.core.cdm.entities import (
    ALL_CDM_ENTITIES,
    Account,
    AccountType,
    Address,
    CDMBase,
    ContactInfo,
    CostCenter,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    JournalEntry,
    JournalEntryLine,
    LedgerEntry,
    Organization,
    OrganizationType,
    Party,
    PartyType,
    Payment,
    PaymentMethod,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    TrialBalance,
)
from erp_auto_mapper.core.cdm.registry import CDMRegistry, HierarchyBridge

__all__ = [
    # Base
    "CDMBase",
    # Enums
    "AccountType",
    "InvoiceStatus",
    "OrganizationType",
    "PartyType",
    "PaymentMethod",
    "PurchaseOrderStatus",
    # Entities
    "Account",
    "Address",
    "ContactInfo",
    "CostCenter",
    "Invoice",
    "InvoiceLineItem",
    "JournalEntry",
    "JournalEntryLine",
    "LedgerEntry",
    "Organization",
    "Party",
    "Payment",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "TrialBalance",
    # Registry
    "CDMRegistry",
    "HierarchyBridge",
    # Lookup
    "ALL_CDM_ENTITIES",
]
