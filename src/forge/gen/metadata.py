
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from forge.gen.enum import EnumInfo
from forge.tools.model import ModelForge


class ColumnRef(BaseModel):
    """Reference to another column"""
    schema: str
    table: str
    column: str

class ColumnMetadata(BaseModel):
    """Column metadata matching TypeScript expectations"""
    name: str  # column name
    type: str  # column type (SQL type)
    nullable: bool
    isPrimaryKey: bool = False
    isEnum: bool = False
    references: Optional[ColumnRef] = None

class TableMetadata(BaseModel):
    """Table metadata matching TypeScript expectations"""
    name: str
    schema: str
    columns: List[ColumnMetadata] = []

class SchemaMetadata(BaseModel):
    """Schema metadata matching TypeScript expectations"""
    name: str
    tables: Dict[str, TableMetadata] = {}

def get_schemas(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/schemas", response_model=List[SchemaMetadata])
    def get_schemas():
        schemas = {}
        for schema_name in model_forge.include_schemas:
            schema_tables = {}
            
            # Collect all tables for this schema
            for table_key, (table, _) in model_forge.table_cache.items():
                if table.schema == schema_name:
                    columns = []
                    for col in table.columns:
                        # Get reference if it's a foreign key
                        ref = None
                        if col.foreign_keys:
                            fk = next(iter(col.foreign_keys))
                            ref = ColumnRef(
                                schema=fk.column.table.schema,
                                table=fk.column.table.name,
                                column=fk.column.name
                            )
                        
                        # Create column metadata
                        columns.append(ColumnMetadata(
                            name=col.name,
                            type=str(col.type),
                            nullable=col.nullable,
                            isPrimaryKey=col.primary_key,
                            isEnum=col.type.__class__.__name__ == 'Enum',
                            references=ref
                        ))

                    schema_tables[table.name] = TableMetadata(
                        name=table.name,
                        schema=schema_name,
                        columns=columns
                    )
            
            schemas[schema_name] = SchemaMetadata(
                name=schema_name,
                tables=schema_tables
            )
        
        return list(schemas.values())


# * TABLES SECTION

def get_tables(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/tables", response_model=List[TableMetadata])
    def get_tables(schema: str):
        tables = []
        for table_key, (table, _) in model_forge.table_cache.items():
            if table.schema == schema:
                columns = []
                for col in table.columns:
                    # Get reference if it's a foreign key
                    ref = None
                    if col.foreign_keys:
                        fk = next(iter(col.foreign_keys))
                        ref = ColumnRef(
                            schema=fk.column.table.schema,
                            table=fk.column.table.name,
                            column=fk.column.name
                        )
                    
                    # Create column metadata
                    columns.append(ColumnMetadata(
                        name=col.name,
                        type=str(col.type),
                        nullable=col.nullable,
                        isPrimaryKey=col.primary_key,
                        isEnum=col.type.__class__.__name__ == 'Enum',
                        references=ref
                    ))

                tables.append(TableMetadata(
                    name=table.name,
                    schema=schema,
                    columns=columns
                ))
        
        if not tables:
            raise HTTPException(status_code=404, detail=f"Schema '{schema}' not found")
        return tables


# * VIEWS SECTION

class ViewColumnMetadata(BaseModel):
    """View column metadata matching TypeScript expectations"""
    name: str
    type: str
    nullable: bool

class ViewMetadata(BaseModel):
    """View metadata matching TypeScript expectations"""
    name: str
    schema: str
    view_columns: List[ViewColumnMetadata] = []

def get_views(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/views", response_model=List[ViewMetadata])
    def get_views(schema: str):
        views = []
        for view_key, view_data in model_forge.view_cache.items():
            # view_cache: Dict[str, Tuple[Table, Tuple[type[BaseModel], type[BaseModel]]]]
            view_schema, view_name = view_key.split('.')
            if view_schema == schema:
                view_columns = []
                for col in view_data[0].columns:
                    view_columns.append(ViewColumnMetadata(
                        name=col.name,
                        type=str(col.type),
                        nullable=col.nullable
                    ))
                
                views.append(ViewMetadata(
                    name=view_name,
                    schema=view_schema,
                    view_columns=view_columns
                ))

        if not views:
            raise HTTPException(status_code=404, detail=f"Schema '{schema}' not found")
        return views
    

# * ENUMS SECTION

class SimpleEnumInfo(BaseModel):
    """Store simplified enum information for metadata endpoints"""
    name: str
    values: List[str]

def get_enums(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/enums", response_model=List[SimpleEnumInfo])
    def get_schema_enums(schema: str):
        """Get all enums for a specific schema"""
        enums = []
        for enum_info in model_forge.enum_cache.values():
            if enum_info.schema == schema:
                enums.append(SimpleEnumInfo(
                    name=enum_info.name,
                    schema=schema,
                    values=enum_info.values
                ))
        
        if not enums:
            raise HTTPException(status_code=404, detail=f"No enums found in schema '{schema}'")
        return enums


# * FUNCTIONS SECTION
