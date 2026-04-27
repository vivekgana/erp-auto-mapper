"""Delta client wrapping Databricks Statement Execution API."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DeltaClient:
    """Thin wrapper around Databricks SQL Statement Execution API."""

    def __init__(
        self,
        host: str = "",
        token: str = "",
        warehouse_id: str = "",
        catalog: str = "erp_auto_mapper_dev",
        schema: str = "mapper",
    ) -> None:
        self._host = host
        self._token = token
        self._warehouse_id = warehouse_id
        self._catalog = catalog
        self._schema = schema
        self._ws: Any = None

    def _get_workspace(self) -> Any:
        if self._ws is None:
            from databricks.sdk import WorkspaceClient
            self._ws = WorkspaceClient(host=self._host, token=self._token)
        return self._ws

    def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        ws = self._get_workspace()
        result = ws.statement_execution.execute_statement(
            warehouse_id=self._warehouse_id,
            statement=sql,
            catalog=self._catalog,
            schema=self._schema,
        )
        columns = [c.name for c in (result.manifest.schema.columns or [])]
        rows = []
        if result.result and result.result.data_array:
            for row_data in result.result.data_array:
                rows.append(dict(zip(columns, row_data)))
        return rows

    def write_rows(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        columns = list(rows[0].keys())
        col_list = ", ".join(columns)
        values_list = []
        for row in rows:
            vals = ", ".join(f"'{row.get(c, '')}'" for c in columns)
            values_list.append(f"({vals})")
        values_sql = ", ".join(values_list)
        sql = f"INSERT INTO {table} ({col_list}) VALUES {values_sql}"
        self.execute_sql(sql)
        return len(rows)

    def read_table(self, table: str, limit: int = 1000) -> list[dict[str, Any]]:
        return self.execute_sql(f"SELECT * FROM {table} LIMIT {limit}")
