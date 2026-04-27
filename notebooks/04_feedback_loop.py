# Databricks notebook source
# MAGIC %md
# MAGIC # Feedback + Reward Engine Demo
# MAGIC Shows how human corrections improve future mapping runs via Thompson Sampling.

# COMMAND ----------

from erp_auto_mapper import FeedbackStore, RewardEngine
from erp_auto_mapper.core.feedback.store import FeedbackEntry
from erp_auto_mapper.core.feedback.reward_engine import RewardSignal

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Initialize Stores

# COMMAND ----------

feedback = FeedbackStore()
reward = RewardEngine()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Record Human Corrections

# COMMAND ----------

feedback.record_feedback(FeedbackEntry(
    source_field="BUKRS",
    original_cdm_field="entity_id",
    corrected_cdm_field="company_code",
    feedback_type="correction",
    erp_type="sap",
    engagement_id="demo-001",
))

feedback.record_feedback(FeedbackEntry(
    source_field="BELNR",
    original_cdm_field="reference_number",
    corrected_cdm_field="entry_id",
    feedback_type="correction",
    erp_type="sap",
    engagement_id="demo-001",
))

print(f"Corrections stored: {feedback.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Compute Boosts

# COMMAND ----------

boost_bukrs = feedback.compute_boost("sap", "BUKRS", "company_code")
boost_belnr = feedback.compute_boost("sap", "BELNR", "entry_id")
print(f"BUKRS -> company_code boost: {boost_bukrs:+.2f}")
print(f"BELNR -> entry_id boost: {boost_belnr:+.2f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Reward Engine (Thompson Sampling)

# COMMAND ----------

for _ in range(5):
    reward.record_reward(RewardSignal(
        source_field="BUKRS", cdm_field="company_code", reward=1.0, erp_type="sap",
    ))

reward.record_reward(RewardSignal(
    source_field="BUKRS", cdm_field="company_code", reward=0.0, erp_type="sap",
))

boosts = reward.suggest_deterministic("sap", "BUKRS", ["company_code", "entity_id"])
print(f"Deterministic boosts: {boosts}")
print(f"Total observations: {reward.total_observations()}")

stochastic = reward.suggest_boost("sap", "BUKRS", ["company_code", "entity_id"])
print(f"Stochastic (sampled) boosts: {stochastic}")
