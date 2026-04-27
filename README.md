# ERP Auto Mapper

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Databricks](https://img.shields.io/badge/Databricks-Marketplace-orange.svg)](https://databricks.com/marketplace)

**AI-powered ERP-to-CDM field mapping engine for financial audit.**

ERP Auto Mapper automatically maps any ERP schema (SAP, Oracle, Dynamics, NetSuite, Workday, Infor, Epicor, Sage) to a 10-entity Canonical Data Model with 6-dimension quality scoring, human feedback loop, and regression detection.

## Features

- **3-Pass Ensemble Mapping** — Alias + Levenshtein similarity, LLM refinement, graph structural boost
- **6-Dimension Eval Scoring** — Semantic similarity, type compatibility, value distribution, LLM judge, business rules, golden set match
- **10 CDM Entities** — JournalEntry, Account, CostCenter, Party, Invoice, Payment, PurchaseOrder, TrialBalance, LedgerEntry, Organization
- **8 ERP Extractors** — SAP, Oracle, Dynamics 365, NetSuite, Workday, Infor, Epicor, Sage
- **Confidence Bands** — AUTO (>=0.85), REVIEW (>=0.50), MANUAL (<0.50)
- **Human Feedback Loop** — FeedbackStore + Thompson Sampling RewardEngine improve accuracy over time
- **Regression Detection** — Baseline comparison prevents quality degradation across releases
- **REST API** — FastAPI with OAuth2, rate limiting, session cache
- **Databricks Native** — Delta tables, Unity Catalog UDFs, DAB deployment, Marketplace listing

## Architecture

```
ERP Schema               Canonical Data Model
    |                          |
    v                          v
[Pass 1: Alias + Similarity]  CDMRegistry (10 entities, extensible)
    |
    +-- FeedbackStore boost
    +-- RewardEngine boost (Thompson Sampling)
    |
    v
[Pass 2: LLM Refinement] --- async LLM callable (10 parallel)
    |
    v
[Pass 3: Graph Structural Boost]
    |
    v
[Confidence Band Classification] --> AUTO / REVIEW / MANUAL
    |
    v
[6-Dimension Eval Scoring] --> MappingEvalResult (aggregate, per_dimension)
    |
    v
MappingOutput --> Delta tables / API response
```

## Install

```bash
pip install erp-auto-mapper          # core only (pydantic + httpx)
pip install erp-auto-mapper[api]     # REST API (FastAPI + uvicorn)
pip install erp-auto-mapper[databricks]  # Databricks SDK + pyarrow
pip install erp-auto-mapper[formats] # Excel, Avro, Parquet support
pip install erp-auto-mapper[all]     # everything
```

## Quick Start

```python
import asyncio
from erp_auto_mapper import CDMRegistry, ERPMappingOrchestrator, OrchestratorConfig
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata

# Define SAP schema
fields = [
    FieldMetadata(name="BUKRS", type="string", description="Company Code"),
    FieldMetadata(name="BELNR", type="string", description="Document Number"),
    FieldMetadata(name="BLDAT", type="date", description="Document Date"),
]
metadata = ERPMetadata(
    source=ERPType.SAP,
    entities=[EntityMetadata(name="BKPF", fields=fields)],
)

# Run mapping
config = OrchestratorConfig(engagement_id="quickstart")
orch = ERPMappingOrchestrator(config=config)
result = asyncio.run(orch.run(metadata))

# Inspect results
for em in result.entity_mappings:
    print(f"{em.source_entity} -> {em.cdm_entity}")
    for fm in em.field_mappings:
        print(f"  {fm['source_field']:20s} -> {fm['cdm_field']:20s}  ({fm['confidence']:.2f} {fm['band']})")
```

## CDM Entities

| Entity | Key Fields | Description |
|--------|-----------|-------------|
| JournalEntry | entry_id, company_code, posting_date, amount | General ledger journal entries |
| Account | account_number, account_name, account_type | Chart of accounts |
| CostCenter | code, name, parent_id | Cost center hierarchy |
| Party | party_id, name, party_type | Vendors, customers, employees |
| Invoice | invoice_number, vendor_id, amount, issue_date | AP/AR invoices |
| Payment | payment_id, amount, payment_date, method | Payment transactions |
| PurchaseOrder | po_number, vendor_id, total_amount | Purchase orders |
| TrialBalance | account_id, period, debit_balance, credit_balance | Period trial balances |
| LedgerEntry | ledger_id, entry_id, amount | Subsidiary ledger entries |
| Organization | org_id, name, parent_id | Company/org hierarchy |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/map` | Map ERP schema to CDM |
| POST | `/v1/validate` | Run 6-dimension eval scoring |
| POST | `/v1/extract` | Upload file, infer schema |
| POST | `/v1/cdm/register` | Register custom CDM entity |
| GET | `/v1/cdm/entities` | List all CDM entities |
| GET | `/health` | Health check |

### Run the API

```bash
# Via CLI
pip install erp-auto-mapper[api]
erp-auto-mapper-serve

# Via Docker
docker build -t erp-auto-mapper .
docker run -p 8000:8000 -e MAPPER_AUTH_DISABLED=true erp-auto-mapper
```

## Databricks Deployment

```bash
# Install Databricks CLI and configure
databricks configure --token

# Deploy to dev
databricks bundle validate --target dev
databricks bundle deploy --target dev

# Run setup (creates Delta tables + registers UDFs)
databricks bundle run erp-auto-mapper-setup --target dev
```

### Unity Catalog UDFs

```sql
-- Map fields
SELECT erp_auto_mapper_dev.mapper.map_fields(
    '[{"name":"BUKRS","type":"string"}]',
    'sap',
    'JournalEntry'
);

-- Validate quality
SELECT erp_auto_mapper_dev.mapper.validate_quality(
    '[{"source_field":"BUKRS","cdm_field":"company_code","confidence":0.95}]'
);
```

## Notebooks

| Notebook | Description |
|----------|-------------|
| `00_quickstart.py` | Map a SAP schema in 15 lines |
| `01_sap_to_cdm.py` | Full SAP walkthrough with eval scoring |
| `02_oracle_to_cdm.py` | Oracle ERP Cloud mapping |
| `03_validate_quality.py` | 6-dimension eval + golden set + business rules |
| `04_feedback_loop.py` | Human corrections + Thompson Sampling |
| `05_batch_job.py` | Scheduled batch mapping from staging volume |

## Development

```bash
git clone https://github.com/erp-auto-mapper/erp-auto-mapper.git
cd erp-auto-mapper
pip install -e ".[all,dev]"
pytest tests/ -v
ruff check src/ tests/
mypy src/
```

## License

Apache-2.0. See [LICENSE](LICENSE).
