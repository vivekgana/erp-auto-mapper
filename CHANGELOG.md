# Changelog

## [0.1.0] - 2026-04-26

### Added
- 3-pass AI ensemble mapping engine (Alias+Similarity, LLM Refinement, Graph Structural Boost)
- 10-entity Canonical Data Model (JournalEntry, Account, CostCenter, Party, Invoice, Payment, PurchaseOrder, TrialBalance, LedgerEntry, Organization)
- 8 ERP extractors (SAP, Oracle, Dynamics 365, NetSuite, Workday, Infor, Epicor, Sage)
- 6-dimension eval scoring (semantic similarity, type compatibility, value distribution, LLM judge, business rule compliance, golden set match)
- Confidence band classification (AUTO >= 0.85, REVIEW >= 0.50, MANUAL < 0.50)
- FeedbackStore for human corrections with boost computation
- RewardEngine with Thompson Sampling for contextual bandit mapping arm selection
- RegressionDetector for baseline comparison across releases
- GoldenSetEvaluator with precision/recall/F1 metrics
- BusinessRuleValidator with 4 accounting invariants (debits=credits, GL rollup, trial balance tie-out, invoice-PO match)
- REST API (FastAPI) with pluggable OAuth2 auth, in-memory rate limiter (50 fields/req, 100 req/day), TTL session cache
- FileFormatReader supporting CSV, JSON, Parquet, Excel, Avro, and more
- SchemaInferrer for automatic type detection from sample data
- TransformationGenerator for 3-layer SQL codegen (staging, transform, mart)
- Databricks native integration: Delta tables, Unity Catalog Python UDFs, DAB deployment
- 6 demo notebooks for Databricks Marketplace
- Docker support with docker-compose
