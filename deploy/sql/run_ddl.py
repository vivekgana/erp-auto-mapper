"""Execute DDL scripts to create Delta tables in Unity Catalog."""

import sys
from pathlib import Path

sys.path.insert(0, "/Workspace")


def run_ddl(catalog: str = "erp_auto_mapper_dev", schema: str = "mapper") -> None:
    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient()
    ddl_dir = Path(__file__).parent

    for sql_file in sorted(ddl_dir.glob("ddl_*.sql")):
        sql = sql_file.read_text()
        sql = sql.replace("${catalog}", catalog).replace("${schema}", schema)
        print(f"Executing: {sql_file.name}")
        ws.statement_execution.execute_statement(
            statement=sql,
            catalog=catalog,
            schema=schema,
        )
        print(f"  Done: {sql_file.name}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run ERP Auto Mapper DDL scripts")
    parser.add_argument("--catalog", default="erp_auto_mapper_dev")
    parser.add_argument("--schema", default="mapper")
    args = parser.parse_args()
    run_ddl(catalog=args.catalog, schema=args.schema)
