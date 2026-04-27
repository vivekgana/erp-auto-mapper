"""Unit tests for BusinessRuleValidator — accounting invariants."""

from erp_auto_mapper.core.eval.business_rule_validator import BusinessRuleValidator


def test_validator_returns_result():
    validator = BusinessRuleValidator()
    mapped_data = {
        "rows": [
            {"debit_amount": 100.0, "credit_amount": 100.0},
            {"debit_amount": 50.0, "credit_amount": 50.0},
        ]
    }
    result = validator.validate(mapped_data, "journal_entry")
    assert result.rules_checked > 0
    assert result.rules_passed == result.rules_checked


def test_unknown_entity():
    validator = BusinessRuleValidator()
    result = validator.validate({}, "unknown_entity")
    assert result.rules_checked >= 0


def test_empty_data():
    validator = BusinessRuleValidator()
    result = validator.validate({}, "journal_entry")
    assert result.rules_checked >= 0
