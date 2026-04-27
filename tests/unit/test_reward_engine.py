"""Unit tests for RewardEngine — Thompson Sampling, deterministic suggest."""

from erp_auto_mapper.core.feedback.reward_engine import RewardEngine, RewardSignal


def test_initial_prior_zero_boost():
    engine = RewardEngine()
    boosts = engine.suggest_deterministic("sap", "BUKRS", ["company_code"])
    assert boosts["company_code"] == 0.0


def test_positive_rewards_increase_boost():
    engine = RewardEngine()
    for _ in range(10):
        engine.record_reward(RewardSignal(
            source_field="BUKRS", cdm_field="company_code", reward=1.0, erp_type="sap",
        ))
    boosts = engine.suggest_deterministic("sap", "BUKRS", ["company_code"])
    assert boosts["company_code"] > 0.0


def test_stochastic_suggest_returns_dict():
    engine = RewardEngine()
    engine.record_reward(RewardSignal(
        source_field="test", cdm_field="target", reward=1.0, erp_type="sap",
    ))
    engine.record_reward(RewardSignal(
        source_field="test", cdm_field="target", reward=0.0, erp_type="sap",
    ))
    boosts = engine.suggest_boost("sap", "test", ["target"])
    assert isinstance(boosts, dict)
    assert "target" in boosts


def test_total_observations():
    engine = RewardEngine()
    assert engine.total_observations() == 0
    engine.record_reward(RewardSignal(
        source_field="X", cdm_field="y", reward=0.5, erp_type="sap",
    ))
    assert engine.total_observations() == 1
