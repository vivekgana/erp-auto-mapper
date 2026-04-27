"""Embedding-based field mapping pass (Pass 1 of the AI Mapping Engine)."""

from __future__ import annotations

import logging
import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import FieldMetadata

logger = logging.getLogger(__name__)


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase/PascalCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().replace("-", "_")


class MappingCandidate(BaseModel):
    """A single candidate mapping between a source field and a CDM field."""

    source_field: str
    cdm_field: str
    score: float = Field(..., ge=0.0, le=1.0)
    method: str = "embedding"


@runtime_checkable
class EmbeddingProvider(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(curr_row[j] + 1, prev_row[j + 1] + 1, prev_row[j] + cost))
        prev_row = curr_row
    return prev_row[-1]


def _levenshtein_similarity(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - (_levenshtein_distance(s1, s2) / max_len)


def _token_similarity(a: str, b: str) -> float:
    """Jaccard similarity on CamelCase-aware underscore-split tokens."""
    ta = set(_camel_to_snake(a).split("_"))
    tb = set(_camel_to_snake(b).split("_"))
    ta.discard("")
    tb.discard("")
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_CDM_FIELDS: dict[str, list[str]] = {
    "JournalEntry": [
        "id", "entry_id", "ledger_id", "posting_date", "period", "company_code",
        "description", "line_items", "is_posted", "created_by",
        "source_key_map", "valid_from", "valid_to", "is_current",
        "amount", "debit_amount", "credit_amount", "currency",
        "account_id", "cost_center_id", "line_number",
        "document_date", "fiscal_year", "document_number",
        "gl_account", "debit_credit",
    ],
    "Account": [
        "id", "account_number", "account_name", "account_type",
        "parent_id", "level", "currency", "is_active",
        "source_key_map", "valid_from", "valid_to", "is_current",
        "parent_account",
    ],
    "LedgerEntry": [
        "id", "ledger_id", "account_id", "posting_date", "period",
        "company_code", "amount", "currency", "description",
        "source_key_map", "valid_from", "valid_to", "is_current",
    ],
    "Party": [
        "id", "name", "party_type", "tax_id", "address", "contact_info",
        "source_key_map", "valid_from", "valid_to", "is_current",
        "email", "phone", "country", "party_id",
    ],
    "TrialBalance": [
        "id", "period", "company_code", "account_id",
        "opening_balance", "debit_total", "credit_total", "closing_balance",
        "currency", "source_key_map", "valid_from", "valid_to", "is_current",
    ],
    "Invoice": [
        "id", "invoice_number", "vendor_id", "customer_id", "amount",
        "currency", "issue_date", "due_date", "status", "line_items",
        "source_key_map", "valid_from", "valid_to", "is_current",
        "description",
    ],
    "Payment": [
        "id", "payment_id", "invoice_id", "amount", "currency",
        "payment_date", "method", "reference",
        "source_key_map", "valid_from", "valid_to", "is_current",
    ],
    "PurchaseOrder": [
        "id", "po_number", "vendor_id", "order_date", "status",
        "total_amount", "currency", "line_items",
        "source_key_map", "valid_from", "valid_to", "is_current",
        "description", "delivery_date",
    ],
    "CostCenter": [
        "id", "code", "name", "parent_id", "level",
        "responsible_person", "is_active",
        "source_key_map", "valid_from", "valid_to", "is_current",
        "parent_code",
    ],
    "Organization": [
        "id", "org_id", "name", "org_type", "parent_id",
        "country_code", "currency_code",
        "source_key_map", "valid_from", "valid_to", "is_current",
    ],
}

_ERP_FIELD_ALIASES: dict[str, str] = {
    "fiscal_year": "period",
    "fiscal_period": "period",
    "document_number": "entry_id",
    "journal_num": "entry_id",
    "journal_header_id": "entry_id",
    "journal_entry_id": "entry_id",
    "journal_id": "entry_id",
    "journal_number": "entry_id",
    "internal_id": "entry_id",
    "gl_account": "account_id",
    "account_number": "account_number",
    "code_combination_id": "account_id",
    "ledger_account": "account_id",
    "ledger_account_id": "account_id",
    "main_account_id": "account_id",
    "nominal_code": "account_number",
    "debit_credit_indicator": "debit_credit",
    "debit_credit": "debit_credit",
    "entered_dr_cr": "debit_credit",
    "is_debit": "debit_credit",
    "debit_credit_flag": "debit_credit",
    "transaction_type": "debit_credit",
    "cost_center": "cost_center_id",
    "cost_center_code": "code",
    "cost_centre": "code",
    "cost_centre_code": "code",
    "cost_center_id": "code",
    "cost_center_reference_id": "code",
    "company_code": "company_code",
    "data_area_id": "company_code",
    "subsidiary": "company_code",
    "company_reference_id": "company_code",
    "company": "company_code",
    "ledger_id": "ledger_id",
    "posting_date": "posting_date",
    "accounting_date": "posting_date",
    "trans_date": "posting_date",
    "tran_date": "posting_date",
    "apply_date": "posting_date",
    "document_date": "document_date",
    "default_effective_date": "document_date",
    "created_date": "document_date",
    "created_moment": "document_date",
    "transaction_date": "document_date",
    "journal_date": "document_date",
    "amount": "amount",
    "entered_amount": "amount",
    "gross_amount": "amount",
    "invoice_amount": "amount",
    "payment_amount": "amount",
    "total_amount": "total_amount",
    "net_amount": "total_amount",
    "amount_lc": "amount",
    "acctd_amount": "amount",
    "book_debit_amount": "amount",
    "ledger_debit_amount": "amount",
    "amount_cur_debit": "amount",
    "book_amount": "amount",
    "transaction_amount": "amount",
    "nominal_amount": "amount",
    "accounting_currency_amount": "amount",
    "currency": "currency",
    "currency_code": "currency",
    "currency_key": "currency",
    "currency_id": "currency",
    "currency_name": "currency",
    "invoice_currency_code": "currency",
    "payment_currency_code": "currency",
    "accounting_currency": "currency",
    "base_currency": "currency_code",
    "functional_currency": "currency_code",
    "company_currency": "currency_code",
    "default_currency": "currency_code",
    "period_name": "period",
    "posting_period": "period",
    "fiscal_calendar_period": "period",
    "accounting_period": "period",
    "financial_period": "period",
    "period_year": "period",
    "year": "period",
    "segment3": "cost_center_id",
    "department": "cost_center_id",
    "invoice_number": "invoice_number",
    "invoice_num": "invoice_number",
    "tran_id": "invoice_number",
    "invoice_id": "invoice_number",
    "vendor_number": "vendor_id",
    "vendor_id": "vendor_id",
    "vendor_num": "vendor_id",
    "supplier_id": "vendor_id",
    "supplier_code": "vendor_id",
    "entity": "vendor_id",
    "invoice_account": "vendor_id",
    "customer_number": "customer_id",
    "customer_id": "customer_id",
    "customer_trx_id": "customer_id",
    "cust_num": "customer_id",
    "customer_code": "customer_id",
    "order_account": "vendor_id",
    "invoice_date": "issue_date",
    "due_date": "due_date",
    "payment_status": "status",
    "approval_status": "status",
    "invoice_status": "status",
    "status": "status",
    "payment_document": "payment_id",
    "payment_id": "payment_id",
    "head_num": "payment_id",
    "payment_number": "payment_id",
    "invoice_reference": "invoice_id",
    "apply_to": "invoice_id",
    "clearing_date": "payment_date",
    "payment_date": "payment_date",
    "check_date": "payment_date",
    "payment_method": "method",
    "payment_method_code": "method",
    "method_of_payment": "method",
    "payment_type": "method",
    "pay_method": "method",
    "reference": "reference",
    "payment_reference": "reference",
    "check_num": "reference",
    "check_number": "reference",
    "reference_number": "reference",
    "purchase_order_number": "po_number",
    "po_header_id": "po_number",
    "purch_id": "po_number",
    "po_num": "po_number",
    "order_number": "po_number",
    "purchase_order_id": "po_number",
    "order_date": "order_date",
    "creation_date": "order_date",
    "created_date_time": "order_date",
    "po_status": "status",
    "purch_status": "status",
    "order_status": "status",
    "authorization_status": "status",
    "delivery_date": "delivery_date",
    "need_by_date": "delivery_date",
    "ship_date": "delivery_date",
    "requested_date": "delivery_date",
    "required_delivery_date": "delivery_date",
    "business_partner": "party_id",
    "party_id": "party_id",
    "account_num": "party_id",
    "worker_id": "party_id",
    "party_number": "party_id",
    "account_code": "party_id",
    "partner_name": "name",
    "party_name": "name",
    "company_name": "name",
    "legal_name": "name",
    "account_name": "name",
    "partner_type": "party_type",
    "party_type": "party_type",
    "cust_vend_type": "party_type",
    "worker_type": "party_type",
    "party_category": "party_category",
    "vendor_type": "party_type",
    "account_type": "account_type",
    "tax_number": "tax_id",
    "tax_registration_number": "tax_id",
    "tax_registration_id": "tax_id",
    "national_id": "tax_id",
    "tax_id": "tax_id",
    "tax_payer_id": "tax_id",
    "vat_number": "tax_id",
    "tax_id_num": "tax_id",
    "email_address": "email",
    "email": "email",
    "primary_email": "email",
    "contact_email": "email",
    "e_mail_address": "email",
    "phone_number": "phone",
    "phone": "phone",
    "primary_phone": "phone",
    "contact_phone": "phone",
    "telephone": "phone",
    "phone_num": "phone",
    "country": "country",
    "country_code": "country_code",
    "country_iso": "country_code",
    "country_region_id": "country",
    "country_num": "country_code",
    "primary_address_country": "country_code",
    "cost_center_name": "name",
    "cost_centre_name": "name",
    "cost_center_description": "name",
    "parent_cost_center": "parent_code",
    "parent_cost_center_id": "parent_code",
    "superior_cost_center": "parent_code",
    "hierarchy_level": "level",
    "responsible_person": "responsible_person",
    "responsible_worker": "responsible_person",
    "manager_name": "responsible_person",
    "manager_id": "responsible_person",
    "manager": "responsible_person",
    "supervisor": "responsible_person",
    "organization_id": "org_id",
    "organization_reference_id": "org_id",
    "company_number": "org_id",
    "organization_name": "name",
    "org_type": "org_type",
    "organization_type": "org_type",
    "entity_type": "org_type",
    "company_type": "org_type",
    "parent_organization_id": "parent_id",
    "parent_organization": "parent_id",
    "parent_company": "parent_id",
    "superior_organization": "parent_id",
    "header_text": "description",
    "document_header_text": "description",
    "text": "description",
    "memo": "description",
    "narrative_text": "description",
    "description": "description",
    "po_description": "description",
    "purch_name": "description",
    "total_goods": "total_amount",
    "total_order": "total_amount",
    "order_total": "total_amount",
    "invoice_total": "amount",
    "invoice_amt": "amount",
    "check_amt": "amount",
    "begin_balance": "opening_balance",
    "beginning_balance": "opening_balance",
    "brought_forward": "opening_balance",
    "open_balance": "opening_balance",
    "end_balance": "closing_balance",
    "ending_balance": "closing_balance",
    "carried_forward": "closing_balance",
    "close_balance": "closing_balance",
    "period_net_dr": "debit_total",
    "period_debits": "debit_total",
    "debit_activity": "debit_total",
    "debit_amount": "debit_total",
    "debit_amt": "debit_total",
    "period_debit": "debit_total",
    "debit": "debit_total",
    "entered_dr": "debit_amount",
    "entered_cr": "credit_amount",
    "period_net_cr": "credit_total",
    "period_credits": "credit_total",
    "credit_activity": "credit_total",
    "credit_amount": "credit_total",
    "credit_amt": "credit_total",
    "period_credit": "credit_total",
    "credit": "credit_total",
    "account_id": "account_id",
    "account_desc": "account_name",
    "account_description": "account_name",
    "nominal_name": "account_name",
    "acct_number": "account_number",
    "acct_name": "account_name",
    "acct_type": "account_type",
    "account_category": "account_type",
    "nominal_type": "account_type",
    "parent_account": "parent_id",
    "parent_account_id": "parent_id",
    "parent_main_account_id": "parent_id",
    "parent_gl_account": "parent_id",
    "parent_ledger_account": "parent_id",
    "parent_code": "parent_id",
    "parent": "parent_id",
    "level": "level",
    "depth": "level",
    "account_level": "level",
    "is_active": "is_active",
    "active": "is_active",
    "active_flag": "is_active",
    "active_status": "is_active",
    "enabled_flag": "is_active",
    "is_inactive": "is_active",
    "is_suspended": "is_active",
    "ledger_book": "ledger_id",
    "ledger": "ledger_id",
    "accounting_book_id": "ledger_id",
    "book_id": "ledger_id",
    "ledger_code": "ledger_id",
    "company_segment": "company_code",
}


class EmbeddingMappingPass:
    """First pass: semantic similarity via embeddings or Levenshtein fallback."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        top_k: int = 10,
        min_threshold: float = 0.0,
    ) -> None:
        self._provider = embedding_provider
        self._top_k = top_k
        self._min_threshold = min_threshold

    def map_fields(
        self, source_fields: list[FieldMetadata], cdm_entity: str
    ) -> list[MappingCandidate]:
        cdm_fields = _CDM_FIELDS.get(cdm_entity, [])
        if not cdm_fields:
            return []

        candidates: list[MappingCandidate] = []
        for src_field in source_fields:
            src_norm = _camel_to_snake(src_field.name)
            scored: list[tuple[str, float]] = []

            alias_target = _ERP_FIELD_ALIASES.get(src_norm)
            if alias_target and alias_target in cdm_fields:
                scored.append((alias_target, 0.95))

            for cdm_name in cdm_fields:
                sim = max(
                    _levenshtein_similarity(src_norm, cdm_name.lower()),
                    _token_similarity(src_field.name, cdm_name),
                )
                if src_field.description:
                    desc_norm = _camel_to_snake(src_field.description)
                    desc_sim = _token_similarity(desc_norm, cdm_name.replace("_", " "))
                    sim = max(sim, desc_sim)
                scored.append((cdm_name, sim))

            scored.sort(key=lambda t: t[1], reverse=True)
            seen: set[str] = set()
            for cdm_name, score in scored[:self._top_k]:
                if cdm_name in seen:
                    continue
                seen.add(cdm_name)
                if self._min_threshold > 0.0 and score < self._min_threshold:
                    continue
                candidates.append(MappingCandidate(
                    source_field=src_field.name,
                    cdm_field=cdm_name,
                    score=round(min(score, 1.0), 4),
                    method="alias" if cdm_name == alias_target else "levenshtein",
                ))

        return candidates
