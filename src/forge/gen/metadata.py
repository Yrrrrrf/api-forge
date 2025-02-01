
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
    is_pk: bool = False
    is_enum: bool = False
    references: Optional[ColumnRef] = None

class TableMetadata(BaseModel):
    """Table metadata matching TypeScript expectations"""
    name: str
    schema: str
    columns: List[ColumnMetadata] = []

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
                        is_pk=col.primary_key,
                        is_enum=col.type.__class__.__name__ == 'Enum',
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
        for _, fn in model_forge.fn_cache.items():
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


# * SCHEMA METADATA!

# src/gen/metadata.py

class SchemaMetadata(BaseModel):
    """Schema metadata matching TypeScript expectations"""
    name: str
    tables: Dict[str, TableMetadata] = {}
    views: Dict[str, ViewMetadata] = {}
    enums: Dict[str, SimpleEnumInfo] = {}
    functions: Dict[str, FunctionMetadataResponse] = {}
    procedures: Dict[str, FunctionMetadataResponse] = {}
    triggers: Dict[str, TriggerMetadataResponse] = {}

def get_schemas(dt_router: APIRouter, model_forge: ModelForge):
    @dt_router.get("/schemas", response_model=List[SchemaMetadata])
    # todo: Add some query parameters to filter schemas!!!
    # todo: Add some query parameters to filter schemas!!!
    # todo: Add some query parameters to filter schemas!!!
    # def get_schemas(schema: Optional[str] = None):
    def get_schemas():
        """Get all schemas with their metadata"""
        schemas = []
        for schema_name in model_forge.include_schemas:
            # Tables processing remains the same
            schema_tables = {
                table_key.split('.')[1]: TableMetadata(
                    name=table_key.split('.')[1],
                    schema=schema_name,
                    columns=[
                        ColumnMetadata(
                            name=col.name,
                            type=str(col.type),
                            nullable=col.nullable,
                            is_pk=col.primary_key,
                            is_enum=col.type.__class__.__name__ == 'Enum',
                            references=ColumnRef(
                                schema=next(iter(col.foreign_keys)).column.table.schema,
                                table=next(iter(col.foreign_keys)).column.table.name,
                                column=next(iter(col.foreign_keys)).column.name
                            ) if col.foreign_keys else None
                        )
                        for col in table_data[0].columns
                    ]
                )
                for table_key, table_data in model_forge.table_cache.items()
                if table_key.split('.')[0] == schema_name
            }

            # Views processing remains the same
            schema_views = {
                view_key.split('.')[1]: ViewMetadata(
                    name=view_key.split('.')[1],
                    schema=schema_name,
                    viewColumns=[
                        ViewColumnMetadata(
                            name=col.name,
                            type=str(col.type),
                            nullable=col.nullable
                        )
                        for col in view_data[0].columns
                    ]
                )
                for view_key, view_data in model_forge.view_cache.items()
                if view_key.split('.')[0] == schema_name
            }

            # Enums processing remains the same
            schema_enums = {
                enum_name: SimpleEnumInfo(
                    name=enum_info.name,
                    schema=enum_info.schema,
                    values=enum_info.values
                )
                for enum_name, enum_info in model_forge.enum_cache.items()
                if enum_info.schema == schema_name
            }

            # Functions processing
            schema_functions = {
                fn_name.split('.')[1]: FunctionMetadataResponse(
                    name=fn_metadata.name,
                    schema=fn_metadata.schema,
                    object_type=fn_metadata.object_type,
                    type=fn_metadata.type,
                    description=fn_metadata.description,
                    parameters=[
                        FunctionParameterMetadata(
                            name=p.name,
                            type=p.type,
                            mode=p.mode,
                            has_default=p.has_default,
                            default_value=str(p.default_value) if p.default_value else None
                        ) for p in fn_metadata.parameters
                    ],
                    return_type=fn_metadata.return_type,
                    return_columns=None,  # Add if needed
                    is_strict=fn_metadata.is_strict
                )
                for fn_name, fn_metadata in model_forge.fn_cache.items()
                if fn_name.split('.')[0] == schema_name
            }

            # Procedures processing
            schema_procedures = {
                proc_name.split('.')[1]: FunctionMetadataResponse(
                    name=proc_metadata.name,
                    schema=proc_metadata.schema,
                    object_type=proc_metadata.object_type,
                    type=proc_metadata.type,
                    description=proc_metadata.description,
                    parameters=[
                        FunctionParameterMetadata(
                            name=p.name,
                            type=p.type,
                            mode=p.mode,
                            has_default=p.has_default,
                            default_value=str(p.default_value) if p.default_value else None
                        ) for p in proc_metadata.parameters
                    ],
                    is_strict=proc_metadata.is_strict
                )
                for proc_name, proc_metadata in model_forge.proc_cache.items()
                if proc_name.split('.')[0] == schema_name
            }

            # Triggers processing
            schema_triggers = {
                trig_name.split('.')[1]: TriggerMetadataResponse(
                    name=trig_metadata.name,
                    schema=trig_metadata.schema,
                    object_type=trig_metadata.object_type,
                    type=trig_metadata.type,
                    description=trig_metadata.description,
                    parameters=[
                        FunctionParameterMetadata(
                            name=p.name,
                            type=p.type,
                            mode=p.mode,
                            has_default=p.has_default,
                            default_value=str(p.default_value) if p.default_value else None
                        ) for p in trig_metadata.parameters
                    ],
                    is_strict=trig_metadata.is_strict,
                    trigger_data=TriggerEventMetadata(
                        timing="AFTER",  # Default timing
                        events=["UPDATE"],  # Default events
                        table_schema=schema_name,
                        table_name=""  # You'll need to extract this from metadata
                    )
                )
                for trig_name, trig_metadata in model_forge.trig_cache.items()
                if trig_name.split('.')[0] == schema_name
            }

            schema_metadata = SchemaMetadata(
                name=schema_name,
                tables=schema_tables,
                views=schema_views,
                enums=schema_enums,
                functions=schema_functions,
                procedures=schema_procedures,
                triggers=schema_triggers
            )
            schemas.append(schema_metadata)

        if not schemas:
            raise HTTPException(status_code=404, detail="No schemas found")
        return schemas
