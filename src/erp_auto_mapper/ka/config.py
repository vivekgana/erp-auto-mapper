"""Knowledge Assistant configuration."""

from __future__ import annotations

from pydantic import BaseModel


class KAConfig(BaseModel):
    catalog: str = "erp_auto_mapper_dev"
    schema_name: str = "mapper"
    vs_endpoint_name: str = "erp-auto-mapper-vs"
    vs_index_name: str = "cdm_field_catalog"
    vs_num_results: int = 5
    llm_endpoint: str = "erp-auto-mapper-llm"
    warehouse_id: str = ""

    @property
    def full_index_name(self) -> str:
        return f"{self.catalog}.{self.schema_name}.{self.vs_index_name}"

    @property
    def docs_table_name(self) -> str:
        return f"{self.catalog}.{self.schema_name}.ka_vector_docs"
