
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from forge.gen.enum import EnumInfo
from forge.gen.fn import FunctionType, ObjectType
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


class FunctionParameterMetadata(BaseModel):
    """Parameter information for functions/procedures"""
    name: str
    type: str
    mode: str = "IN"  # IN, OUT, INOUT, VARIADIC
    has_default: bool = False
    default_value: Optional[str] = None

class ReturnColumnMetadata(BaseModel):
    """For TABLE and complex return types"""
    name: str
    type: str

class FunctionMetadataResponse(BaseModel):
    """Common metadata for all function types"""
    name: str
    schema: str
    object_type: ObjectType
    type: FunctionType
    description: Optional[str] = None
    parameters: List[FunctionParameterMetadata] = []
    return_type: Optional[str] = None
    return_columns: Optional[List[ReturnColumnMetadata]] = None
    is_strict: bool = False

def get_functions(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/functions", response_model=List[FunctionMetadataResponse])
    def get_schema_functions(schema: str):
        """Get all functions for a schema"""
        functions = []
        
        # Regular functions
        for fn_key, fn in model_forge.fn_cache.items():
            if fn.schema == schema:
                # Convert parameters
                params = [
                    FunctionParameterMetadata(
                        name=p.name,
                        type=p.type,
                        mode=p.mode,
                        has_default=p.has_default,
                        default_value=str(p.default_value) if p.default_value else None
                    ) for p in fn.parameters
                ]
                
                # Handle return columns for TABLE types
                return_cols = None
                if fn.type in (FunctionType.TABLE, FunctionType.SET_RETURNING) and fn.return_type:
                    # Parse TABLE definition
                    if "TABLE" in fn.return_type:
                        cols_str = fn.return_type.replace("TABLE", "").strip("()").strip()
                        cols = [col.strip() for col in cols_str.split(",")]
                        return_cols = []
                        for col in cols:
                            name, type_str = col.split(" ", 1)
                            return_cols.append(ReturnColumnMetadata(
                                name=name,
                                type=type_str
                            ))
                
                functions.append(FunctionMetadataResponse(
                    name=fn.name,
                    schema=fn.schema,
                    object_type=ObjectType(fn.object_type),
                    type=fn.type,
                    description=fn.description,
                    parameters=params,
                    return_type=fn.return_type,
                    return_columns=return_cols,
                    is_strict=fn.is_strict
                ))
        
        if not functions:
            raise HTTPException(status_code=404, detail=f"No functions found in schema '{schema}'")
        return functions

def get_procedures(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/procedures", response_model=List[FunctionMetadataResponse])
    def get_schema_procedures(schema: str):
        """Get all procedures for a schema"""
        procedures = []
        
        for proc_key, proc in model_forge.proc_cache.items():
            if proc.schema == schema:
                params = [
                    FunctionParameterMetadata(
                        name=p.name,
                        type=p.type,
                        mode=p.mode,
                        has_default=p.has_default,
                        default_value=str(p.default_value) if p.default_value else None
                    ) for p in proc.parameters
                ]
                
                procedures.append(FunctionMetadataResponse(
                    name=proc.name,
                    schema=proc.schema,
                    object_type=ObjectType(proc.object_type),
                    type=proc.type,
                    description=proc.description,
                    parameters=params,
                    is_strict=proc.is_strict
                ))
        
        if not procedures:
            raise HTTPException(status_code=404, detail=f"No procedures found in schema '{schema}'")
        return procedures

    
class TriggerEventMetadata(BaseModel):
    """Additional metadata specific to triggers"""
    timing: str  # BEFORE, AFTER, INSTEAD OF
    events: List[str]  # INSERT, UPDATE, DELETE, TRUNCATE
    table_schema: str
    table_name: str

class TriggerMetadataResponse(FunctionMetadataResponse):
    """Extended metadata for triggers"""
    trigger_data: TriggerEventMetadata

def get_triggers(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/triggers", response_model=List[TriggerMetadataResponse])
    def get_schema_triggers(schema: str):
        """Get all triggers for a schema"""
        triggers = []
        
        for trig_key, trig in model_forge.trig_cache.items():
            if trig.schema == schema:
                # Parse trigger event information from description or metadata
                timing, events = "AFTER", ["UPDATE"]  # Default values
                table_schema = schema
                table_name = ""
                
                # You might need to adjust this based on your actual trigger metadata
                if trig.description:
                    # Parse timing and events from description if available
                    # This is just an example - adjust based on your actual format
                    desc_parts = trig.description.split(" ")
                    if len(desc_parts) >= 4:
                        timing = desc_parts[0]
                        events = [desc_parts[1]]
                        table_ref = desc_parts[3]
                        if "." in table_ref:
                            table_schema, table_name = table_ref.split(".")
                        else:
                            table_name = table_ref
                
                trigger_data = TriggerEventMetadata(
                    timing=timing,
                    events=events,
                    table_schema=table_schema,
                    table_name=table_name
                )
                
                params = [
                    FunctionParameterMetadata(
                        name=p.name,
                        type=p.type,
                        mode=p.mode,
                        has_default=p.has_default,
                        default_value=str(p.default_value) if p.default_value else None
                    ) for p in trig.parameters
                ]
                
                triggers.append(TriggerMetadataResponse(
                    name=trig.name,
                    schema=trig.schema,
                    object_type=ObjectType(trig.object_type),
                    type=trig.type,
                    description=trig.description,
                    parameters=params,
                    is_strict=trig.is_strict,
                    trigger_data=trigger_data
                ))
        
        if not triggers:
            raise HTTPException(status_code=404, detail=f"No triggers found in schema '{schema}'")
        return triggers
