"""CLI entry point for registering ERP Auto Mapper UDFs in Unity Catalog."""

import sys
sys.path.insert(0, "/Workspace")

from erp_auto_mapper.databricks.udfs import register_udfs

if __name__ == "__main__":
    register_udfs()
