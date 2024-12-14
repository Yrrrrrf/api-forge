from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from sqlalchemy import MetaData


class ColumnMetadata(BaseModel):
    name: str  # Column name
    type: str
    is_primary_key: bool
    is_foreign_key: bool = False

class TableMetadata(BaseModel):
    name: str  # Table name
    columns: List[ColumnMetadata] = []

class SchemaMetadata(BaseModel):
    name: str  # Schema name
    tables: Dict[str, TableMetadata] = {}


def get_metadata_router(metadata: MetaData, prefix: str = "/dt") -> APIRouter:
    dt_router: APIRouter = APIRouter(prefix=prefix, tags=["METADATA"])

    @dt_router.get("/schemas", response_model=List[SchemaMetadata])
    def get_schemas():
        schemas = {}
        for table in metadata.tables.values():
            if table.schema not in schemas:
                schemas[table.schema] = SchemaMetadata(name=table.schema)

            table_metadata = TableMetadata(name=table.name)
            for column in table.columns:
                column_metadata = ColumnMetadata(
                    name=column.name,
                    type=str(column.type),
                    is_primary_key=column.primary_key,
                    is_foreign_key=bool(column.foreign_keys)
                )
                table_metadata.columns.append(column_metadata)
            
            schemas[table.schema].tables[table.name] = table_metadata
        
        return list(schemas.values())

    @dt_router.get("/{schema}/tables", response_model=List[TableMetadata])
    def get_tables(schema: str):
        tables = []
        for table in metadata.tables.values():
            if table.schema == schema:
                table_metadata = TableMetadata(name=table.name)
                for column in table.columns:
                    column_metadata = ColumnMetadata(
                        name=column.name,
                        type=str(column.type),
                        is_primary_key=column.primary_key,
                        is_foreign_key=bool(column.foreign_keys)
                    )
                    table_metadata.columns.append(column_metadata)
                tables.append(table_metadata)
        
        if not tables:
            raise HTTPException(status_code=404, detail=f"Schema '{schema}' not found")
        return tables

    @dt_router.get("/{schema}/{table}/columns", response_model=List[ColumnMetadata])
    def get_columns(schema: str, table: str):
        full_table_name = f"{schema}.{table}"
        if full_table_name not in metadata.tables:
            raise HTTPException(status_code=404, detail=f"Table '{full_table_name}' not found")
        
        table_obj = metadata.tables[full_table_name]
        columns = []
        for column in table_obj.columns:
            column_metadata = ColumnMetadata(
                name=column.name,
                type=str(column.type),
                is_primary_key=column.primary_key,
                is_foreign_key=bool(column.foreign_keys)
            )
            columns.append(column_metadata)
        return columns

    return dt_router
