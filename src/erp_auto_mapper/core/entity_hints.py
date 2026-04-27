"""Shared entity-name → CDM-entity lookup used by orchestrator and skills."""

from __future__ import annotations

# Keys are normalized: lowercase, no underscores, no spaces.
# The orchestrator looks up entity.name.lower().replace(" ","").replace("_","").
ENTITY_HINTS: dict[str, str] = {
    "journalentry": "JournalEntry",
    "journalentries": "JournalEntry",
    "gljournals": "JournalEntry",
    "gljelines": "JournalEntry",
    "bkpf": "JournalEntry",
    "bseg": "JournalEntry",
    "acdoca": "JournalEntry",
    "generaljournalaccountentry": "JournalEntry",
    "glaccount": "Account",
    "glaccounts": "Account",
    "chartofaccounts": "Account",
    "ska1": "Account",
    "costcenter": "CostCenter",
    "costcenters": "CostCenter",
    "vendor": "Party",
    "customer": "Party",
    "employee": "Party",
    "lfa1": "Party",
    "kna1": "Party",
    "hzparties": "Party",
    "invoice": "Invoice",
    "apinvoicesall": "Invoice",
    "vendinvoicejour": "Invoice",
    "payment": "Payment",
    "purchaseorder": "PurchaseOrder",
    "poheadersall": "PurchaseOrder",
    "trialbalance": "TrialBalance",
    "glbalances": "TrialBalance",
    "faglflext": "TrialBalance",
    "ledgerentry": "LedgerEntry",
    "organization": "Organization",
    "organisation": "Organization",
    "company": "Organization",
}


def token_overlap(a: str, b: str) -> float:
    """Jaccard overlap of underscore/hyphen-delimited tokens."""
    ta = set(a.lower().replace("-", "_").split("_"))
    tb = set(b.lower().replace("-", "_").split("_"))
    ta.discard("")
    tb.discard("")
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
