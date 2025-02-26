from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from forge.gen.enum import EnumInfo
from forge.gen.fn import FunctionType, ObjectType
from forge.tools.model import ModelForge

from sqlalchemy.types import Enum as SAEnum

# --- Data Models (unchanged) ---

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
    is_pk: Optional[bool] = None
    is_enum: Optional[bool] = None
    references: Optional[ColumnRef] = None

class TableMetadata(BaseModel):
    """Table metadata matching TypeScript expectations"""
    name: str
    schema: str
    columns: List[ColumnMetadata] = []

class SimpleEnumInfo(BaseModel):
    """Store simplified enum information for metadata endpoints"""
    name: str
    values: List[str]

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

class TriggerEventMetadata(BaseModel):
    """Additional metadata specific to triggers"""
    timing: str  # BEFORE, AFTER, INSTEAD OF
    events: List[str]  # INSERT, UPDATE, DELETE, TRUNCATE
    table_schema: str
    table_name: str

class TriggerMetadataResponse(FunctionMetadataResponse):
    """Extended metadata for triggers"""
    trigger_data: TriggerEventMetadata

class SchemaMetadata(BaseModel):
    """Schema metadata matching TypeScript expectations"""
    name: str
    tables: Dict[str, TableMetadata] = {}
    views: Dict[str, TableMetadata] = {}
    enums: Dict[str, SimpleEnumInfo] = {}
    functions: Dict[str, FunctionMetadataResponse] = {}
    procedures: Dict[str, FunctionMetadataResponse] = {}
    triggers: Dict[str, TriggerMetadataResponse] = {}

# --- Helper Functions ---
# Import Any if you don't have a more specific type for 'col'
from typing import Any

def build_column_metadata(col: Any) -> ColumnMetadata:
    """Convert a column object to ColumnMetadata with proper typing and optional values.
    
    If the column is not a primary key or not an enum, the corresponding fields will be None,
    so that when converting to JSON (with exclude_none=True) they are omitted.
    """
    ref = None
    if col.foreign_keys:
        fk = next(iter(col.foreign_keys))
        ref = ColumnRef(
            schema=fk.column.table.schema,
            table=fk.column.table.name,
            column=fk.column.name
        )
    # Then in your helper:
    # Use None instead of False so that these fields don't appear in the JSON output.
    return ColumnMetadata(
        name=col.name,
        type=str(col.type),
        nullable=col.nullable,
        is_pk=True if col.primary_key else None,  # Only include if True
        is_enum=True if isinstance(col.type, SAEnum) else None,
        references=ref
    )


def build_table_metadata(name: str, table, schema: str) -> TableMetadata:
    """Convert a table (or view) object to TableMetadata using its columns."""
    return TableMetadata(
        name=name,
        schema=schema,
        columns=[build_column_metadata(col) for col in table.columns]
    )

def build_function_param_metadata(p: Any) -> FunctionParameterMetadata:
    """Convert a function parameter to FunctionParameterMetadata."""
    return FunctionParameterMetadata(
        name=p.name,
        type=p.type,
        mode=p.mode,
        has_default=p.has_default,
        default_value=str(p.default_value) if p.default_value else None
    )

def build_function_metadata(fn) -> FunctionMetadataResponse:
    """Convert a function/procedure object to FunctionMetadataResponse."""
    params = [build_function_param_metadata(p) for p in fn.parameters]
    return_cols = None
    if fn.type in (FunctionType.TABLE, FunctionType.SET_RETURNING) and fn.return_type:
        if "TABLE" in fn.return_type:
            cols_str = fn.return_type.replace("TABLE", "").strip("()").strip()
            return_cols = []
            for col in (c.strip() for c in cols_str.split(",")):
                name, type_str = col.split(" ", 1)
                return_cols.append(ReturnColumnMetadata(name=name, type=type_str))
    return FunctionMetadataResponse(
        name=fn.name,
        schema=fn.schema,
        object_type=ObjectType(fn.object_type),
        type=fn.type,
        description=fn.description,
        parameters=params,
        return_type=fn.return_type,
        return_columns=return_cols,
        is_strict=fn.is_strict
    )

def parse_trigger_event(trig, default_schema: str) -> TriggerEventMetadata:
    """Parse trigger event metadata from trigger description, with defaults."""
    timing, events, table_schema, table_name = "AFTER", ["UPDATE"], default_schema, ""
    if trig.description:
        parts = trig.description.split(" ")
        if len(parts) >= 4:
            timing, events = parts[0], [parts[1]]
            table_ref = parts[3]
            if "." in table_ref:
                table_schema, table_name = table_ref.split(".", 1)
            else:
                table_name = table_ref
    return TriggerEventMetadata(
        timing=timing,
        events=events,
        table_schema=table_schema,
        table_name=table_name
    )

# --- Endpoint Functions (Refactored) ---

def get_tables(dt_router: APIRouter, model_forge: ModelForge):
    from fastapi.encoders import jsonable_encoder

    @dt_router.get("/{schema}/tables", response_model=List[TableMetadata])
    def get_tables_by_schema(schema: str):
        tables = [
            build_table_metadata(table.name, table, schema)
            for table, _ in model_forge.table_cache.values()
            if table.schema == schema
        ]
        if not tables:
            raise HTTPException(status_code=404, detail=f"Schema '{schema}' not found")
        # This encoder will exclude fields set to None (i.e. is_pk and is_enum if not true)
        return jsonable_encoder(tables, exclude_none=True)


def get_views(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/views", response_model=List[TableMetadata])
    def get_views_by_schema(schema: str):
        views = []
        for key, (view_table, _) in model_forge.view_cache.items():
            view_schema, view_name = key.split(".", 1)
            if view_schema == schema:
                views.append(build_table_metadata(view_name, view_table, schema))
        if not views:
            raise HTTPException(status_code=404, detail=f"No views found in schema '{schema}'")
        return views

def get_enums(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/enums", response_model=List[SimpleEnumInfo])
    def get_enums_by_schema(schema: str):
        enums = [
            SimpleEnumInfo(name=enum_info.name, values=enum_info.values)
            for enum_info in model_forge.enum_cache.values()
            if enum_info.schema == schema
        ]
        if not enums:
            raise HTTPException(status_code=404, detail=f"No enums found in schema '{schema}'")
        return enums

def get_functions(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/functions", response_model=List[FunctionMetadataResponse])
    def get_fn_by_schema(schema: str):
        functions = [
            build_function_metadata(fn)
            for fn in model_forge.fn_cache.values()
            if fn.schema == schema
        ]
        if not functions:
            raise HTTPException(status_code=404, detail=f"No functions found in schema '{schema}'")
        return functions

def get_procedures(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/procedures", response_model=List[FunctionMetadataResponse])
    def get_proc_by_schema(schema: str):
        procedures = [
            build_function_metadata(proc)
            for proc in model_forge.proc_cache.values()
            if proc.schema == schema
        ]
        if not procedures:
            raise HTTPException(status_code=404, detail=f"No procedures found in schema '{schema}'")
        return procedures

def get_triggers(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/{schema}/triggers", response_model=List[TriggerMetadataResponse])
    def get_triggers_by_schema(schema: str):
        triggers = [
            TriggerMetadataResponse(
                name=trig.name,
                schema=trig.schema,
                object_type=ObjectType(trig.object_type),
                type=trig.type,
                description=trig.description,
                parameters=[build_function_param_metadata(p) for p in trig.parameters],
                is_strict=trig.is_strict,
                trigger_data=parse_trigger_event(trig, schema)
            )
            for trig in model_forge.trig_cache.values()
            if trig.schema == schema
        ]
        if not triggers:
            raise HTTPException(status_code=404, detail=f"No triggers found in schema '{schema}'")
        return triggers

def get_schemas(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/schemas", response_model=List[SchemaMetadata])
    def get_schemas():
        schemas = []
        for schema_name in model_forge.include_schemas:
            schema_tables = {
                key.split('.')[1]: build_table_metadata(key.split('.')[1], table_data[0], schema_name)
                for key, table_data in model_forge.table_cache.items()
                if key.split('.')[0] == schema_name
            }
            schema_views = {
                key.split('.')[1]: build_table_metadata(key.split('.')[1], view_table, schema_name)
                for key, (view_table, _) in model_forge.view_cache.items()
                if key.split('.')[0] == schema_name
            }
            schema_enums = {
                enum_name: SimpleEnumInfo(name=enum_info.name, values=enum_info.values)
                for enum_name, enum_info in model_forge.enum_cache.items()
                if enum_info.schema == schema_name
            }
            schema_functions = {
                key.split('.')[1]: build_function_metadata(fn_metadata)
                for key, fn_metadata in model_forge.fn_cache.items()
                if key.split('.')[0] == schema_name
            }
            schema_procedures = {
                key.split('.')[1]: build_function_metadata(proc_metadata)
                for key, proc_metadata in model_forge.proc_cache.items()
                if key.split('.')[0] == schema_name
            }
            # For triggers, we use default event metadata (as per your original code)
            schema_triggers = {
                key.split('.')[1]: TriggerMetadataResponse(
                    name=trig_metadata.name,
                    schema=trig_metadata.schema,
                    object_type=trig_metadata.object_type,
                    type=trig_metadata.type,
                    description=trig_metadata.description,
                    parameters=[build_function_param_metadata(p) for p in trig_metadata.parameters],
                    is_strict=trig_metadata.is_strict,
                    trigger_data=TriggerEventMetadata(
                        timing="AFTER",
                        events=["UPDATE"],
                        table_schema=schema_name,
                        table_name=""
                    )
                )
                for key, trig_metadata in model_forge.trig_cache.items()
                if key.split('.')[0] == schema_name
            }
            schemas.append(SchemaMetadata(
                name=schema_name,
                tables=schema_tables,
                views=schema_views,
                enums=schema_enums,
                functions=schema_functions,
                procedures=schema_procedures,
                triggers=schema_triggers
            ))
        if not schemas:
            raise HTTPException(status_code=404, detail="No schemas found")
        return schemas
