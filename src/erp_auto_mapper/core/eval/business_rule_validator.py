"""Business-rule validator — auto-infers accounting invariants from CDM entities."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Result models
# ------------------------------------------------------------------

class RuleDetail(BaseModel):
    """Outcome of a single business-rule check."""

    rule_name: str
    passed: bool
    message: str = ""
    expected: Any = None
    actual: Any = None


class BusinessRuleResult(BaseModel):
    """Aggregate result from business-rule validation."""

    rules_checked: int = 0
    rules_passed: int = 0
    rules_failed: int = 0
    details: list[RuleDetail] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.rules_passed / self.rules_checked if self.rules_checked else 0.0


# ------------------------------------------------------------------
# Rule definitions
# ------------------------------------------------------------------

class _RuleRegistry:
    """Internal registry mapping CDM entity names to applicable rules."""

    ENTITY_RULES: dict[str, list[str]] = {
        "journal_entry": ["debits_equal_credits"],
        "journal_entry_line": ["debits_equal_credits"],
        "general_ledger": ["gl_rollup_consistency"],
        "trial_balance": ["trial_balance_tieout"],
        "invoice": ["invoice_po_matching"],
        "accounts_payable": ["invoice_po_matching"],
    }

    @classmethod
    def rules_for(cls, cdm_entity: str) -> list[str]:
        normalised = cdm_entity.lower().replace(" ", "_")
        return cls.ENTITY_RULES.get(normalised, [])


class BusinessRuleValidator:
    """Auto-infers and validates accounting invariants for mapped CDM data.

    Supported rules:
    * **debits_equal_credits** — per journal entry, sum(debit) == sum(credit)
    * **gl_rollup_consistency** — child account totals == parent total
    * **trial_balance_tieout** — total debits == total credits per period/company
    * **invoice_po_matching** — every invoice references a valid PO
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, mapped_data: dict[str, Any], cdm_entity: str) -> BusinessRuleResult:
        """Run all applicable business rules for *cdm_entity* against *mapped_data*.

        Args:
            mapped_data: Dict whose keys are CDM field names and values are
                lists of column values (columnar format) or a list of row
                dicts under the key ``"rows"``.
            cdm_entity: Name of the CDM entity (e.g. ``"journal_entry"``).

        Returns:
            A :class:`BusinessRuleResult` summarising which rules passed/failed.
        """
        rule_names = _RuleRegistry.rules_for(cdm_entity)
        if not rule_names:
            logger.info("No business rules defined for CDM entity '%s'", cdm_entity)
            return BusinessRuleResult()

        details: list[RuleDetail] = []
        for name in rule_names:
            handler = self._rule_handlers.get(name)
            if handler is None:
                logger.warning("Rule '%s' has no handler implementation", name)
                continue
            detail = handler(self, mapped_data)
            details.append(detail)

        passed = sum(1 for d in details if d.passed)
        return BusinessRuleResult(
            rules_checked=len(details),
            rules_passed=passed,
            rules_failed=len(details) - passed,
            details=details,
        )

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    def _check_debits_equal_credits(self, data: dict[str, Any]) -> RuleDetail:
        """Sum(debit) must equal Sum(credit) across all rows."""
        rows = self._extract_rows(data)
        total_debit = 0.0
        total_credit = 0.0
        for row in rows:
            total_debit += float(row.get("debit_amount", 0) or 0)
            total_credit += float(row.get("credit_amount", 0) or 0)

        passed = abs(total_debit - total_credit) < 0.01
        return RuleDetail(
            rule_name="debits_equal_credits",
            passed=passed,
            message=(
                "Debits equal credits."
                if passed
                else f"Imbalance detected: debits={total_debit:.2f}, credits={total_credit:.2f}"
            ),
            expected="debit_total == credit_total",
            actual={"total_debit": total_debit, "total_credit": total_credit},
        )

    def _check_gl_rollup_consistency(self, data: dict[str, Any]) -> RuleDetail:
        """Child account totals must equal parent account totals."""
        rows = self._extract_rows(data)
        parent_totals: dict[str, float] = {}
        child_sums: dict[str, float] = {}

        for row in rows:
            account_id = str(row.get("account_id", ""))
            parent_id = str(row.get("parent_account_id", ""))
            amount = float(row.get("amount", 0) or 0)

            if parent_id:
                child_sums.setdefault(parent_id, 0.0)
                child_sums[parent_id] += amount

            parent_totals[account_id] = float(row.get("balance", amount) or 0)

        mismatches: list[str] = []
        for parent, child_total in child_sums.items():
            if parent in parent_totals:
                if abs(parent_totals[parent] - child_total) >= 0.01:
                    mismatches.append(
                        f"Account {parent}: parent={parent_totals[parent]:.2f}, children={child_total:.2f}"
                    )

        passed = len(mismatches) == 0
        return RuleDetail(
            rule_name="gl_rollup_consistency",
            passed=passed,
            message="GL rollup consistent." if passed else f"{len(mismatches)} rollup mismatches found.",
            expected="parent_balance == sum(child_balances)",
            actual=mismatches[:10] if mismatches else "all consistent",
        )

    def _check_trial_balance_tieout(self, data: dict[str, Any]) -> RuleDetail:
        """Total debits must equal total credits per period/company."""
        rows = self._extract_rows(data)
        period_totals: dict[str, dict[str, float]] = {}

        for row in rows:
            period = str(row.get("period", row.get("fiscal_period", "unknown")))
            company = str(row.get("company_code", ""))
            key = f"{company}|{period}"

            bucket = period_totals.setdefault(key, {"debit": 0.0, "credit": 0.0})
            bucket["debit"] += float(row.get("debit_amount", row.get("debit", 0)) or 0)
            bucket["credit"] += float(row.get("credit_amount", row.get("credit", 0)) or 0)

        imbalanced: list[str] = []
        for key, totals in period_totals.items():
            if abs(totals["debit"] - totals["credit"]) >= 0.01:
                imbalanced.append(f"{key}: D={totals['debit']:.2f} C={totals['credit']:.2f}")

        passed = len(imbalanced) == 0
        return RuleDetail(
            rule_name="trial_balance_tieout",
            passed=passed,
            message="Trial balance ties out." if passed else f"{len(imbalanced)} period(s) imbalanced.",
            expected="total_debits == total_credits per period/company",
            actual=imbalanced[:10] if imbalanced else "all balanced",
        )

    def _check_invoice_po_matching(self, data: dict[str, Any]) -> RuleDetail:
        """Every invoice must reference a valid purchase order."""
        rows = self._extract_rows(data)
        total = 0
        unmatched = 0
        unmatched_ids: list[str] = []

        for row in rows:
            po_ref = row.get("purchase_order_id") or row.get("po_number")
            total += 1
            if not po_ref or str(po_ref).strip() == "":
                unmatched += 1
                inv_id = str(row.get("invoice_id", row.get("document_number", "?")))
                if len(unmatched_ids) < 10:
                    unmatched_ids.append(inv_id)

        passed = unmatched == 0
        return RuleDetail(
            rule_name="invoice_po_matching",
            passed=passed,
            message=(
                "All invoices reference a PO."
                if passed
                else f"{unmatched}/{total} invoices missing PO reference."
            ),
            expected="every invoice has a valid PO reference",
            actual={"unmatched_count": unmatched, "sample_ids": unmatched_ids},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalise *data* into a list of row dicts.

        Accepts either ``{"rows": [...]}`` or columnar format
        ``{"col": [v1, v2, ...]}``.
        """
        if "rows" in data and isinstance(data["rows"], list):
            return data["rows"]

        # Columnar -> row-wise pivot.
        columns = {k: v for k, v in data.items() if isinstance(v, list)}
        if not columns:
            return []
        length = max(len(v) for v in columns.values())
        return [
            {k: (v[i] if i < len(v) else None) for k, v in columns.items()}
            for i in range(length)
        ]

    # Handler dispatch table.
    _rule_handlers: dict[str, Any] = {
        "debits_equal_credits": _check_debits_equal_credits,
        "gl_rollup_consistency": _check_gl_rollup_consistency,
        "trial_balance_tieout": _check_trial_balance_tieout,
        "invoice_po_matching": _check_invoice_po_matching,
    }

    # ------------------------------------------------------------------
    # Convenience methods — direct rule execution
    # ------------------------------------------------------------------

    def validate_debits_equal_credits(
        self, entries: list[dict[str, Any]]
    ) -> BusinessRuleResult:
        """Validate debits == credits for a list of journal entries.

        Each entry is ``{"entry_id": str, "lines": [{"debit": float, "credit": float}, ...]}``.
        """
        details: list[RuleDetail] = []
        for entry in entries:
            entry_id = entry.get("entry_id", "unknown")
            lines = entry.get("lines", [])
            total_debit = sum(float(ln.get("debit", ln.get("debit_amount", 0)) or 0) for ln in lines)
            total_credit = sum(float(ln.get("credit", ln.get("credit_amount", 0)) or 0) for ln in lines)
            passed = abs(total_debit - total_credit) < 0.01
            details.append(RuleDetail(
                rule_name=f"debits_equal_credits:{entry_id}",
                passed=passed,
                message=f"Entry {entry_id}: debit={total_debit:.2f}, credit={total_credit:.2f}",
                expected="debit_total == credit_total",
                actual={"total_debit": total_debit, "total_credit": total_credit},
            ))
        p = sum(1 for d in details if d.passed)
        return BusinessRuleResult(
            rules_checked=len(details),
            rules_passed=p,
            rules_failed=len(details) - p,
            details=details,
        )

    def validate_gl_rollup(
        self, accounts: list[dict[str, Any]]
    ) -> BusinessRuleResult:
        """Validate parent balance == sum(child balances).

        Each account: ``{"id": str, "parent_id": str|None, "balance": float}``.
        """
        by_id: dict[str, float] = {}
        children: dict[str, list[str]] = {}
        for acc in accounts:
            aid = str(acc["id"])
            by_id[aid] = float(acc.get("balance", 0))
            pid = acc.get("parent_id")
            if pid is not None:
                children.setdefault(str(pid), []).append(aid)

        details: list[RuleDetail] = []
        for pid, child_ids in children.items():
            child_sum = sum(by_id.get(c, 0) for c in child_ids)
            parent_bal = by_id.get(pid, 0)
            passed = abs(parent_bal - child_sum) < 0.01
            details.append(RuleDetail(
                rule_name=f"gl_rollup:{pid}",
                passed=passed,
                message=f"Account {pid}: parent={parent_bal:.2f}, children={child_sum:.2f}",
            ))
        p = sum(1 for d in details if d.passed)
        return BusinessRuleResult(
            rules_checked=len(details),
            rules_passed=p,
            rules_failed=len(details) - p,
            details=details,
        )

    def validate_trial_balance(
        self, tb_rows: list[dict[str, Any]]
    ) -> BusinessRuleResult:
        """Validate total debits == total credits across all TB rows.

        Each row: ``{"account_id": str, "debit_total": float, "credit_total": float}``.
        """
        if not tb_rows:
            return BusinessRuleResult(rules_checked=0, rules_passed=0, rules_failed=0)
        total_debit = sum(float(r.get("debit_total", 0) or 0) for r in tb_rows)
        total_credit = sum(float(r.get("credit_total", 0) or 0) for r in tb_rows)
        passed = abs(total_debit - total_credit) < 0.01
        detail = RuleDetail(
            rule_name="trial_balance_tieout",
            passed=passed,
            message=f"TB: debit={total_debit:.2f}, credit={total_credit:.2f}",
        )
        return BusinessRuleResult(
            rules_checked=1,
            rules_passed=1 if passed else 0,
            rules_failed=0 if passed else 1,
            details=[detail],
        )
