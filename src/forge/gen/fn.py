from enum import Enum
from typing import Any, Callable, Dict, List, Tuple, Optional, Type, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import text
from sqlalchemy.orm import Session

from forge.core.logging import *
from forge.gen.crud import CRUD
from forge.tools.sql_mapping import ArrayType, get_eq_type

# ? Metadata for some function ---------------------------------------------------

# ?.todo: Add some way to generalize this to more databases than just PostgreSQL
class PostgresObjectType(str, Enum):
    FUNCTION = "function"
    PROCEDURE = "procedure"
    TRIGGER = "trigger"
    AGGREGATE = "aggregate"
    WINDOW = "window"

class FunctionVolatility(str, Enum):
    IMMUTABLE = "IMMUTABLE"
    STABLE = "STABLE"
    VOLATILE = "VOLATILE"

class SecurityType(str, Enum):
    DEFINER = "SECURITY DEFINER"
    INVOKER = "SECURITY INVOKER"

class FunctionType(str, Enum):
    SCALAR = "scalar"
    TABLE = "table"
    SET_RETURNING = "set"
    AGGREGATE = "aggregate"
    WINDOW = "window"

class FunctionParameter(BaseModel):
    name: str
    type: str
    has_default: bool = False
    default_value: Optional[Any] = None
    mode: str = "IN"  # IN, OUT, INOUT, VARIADIC

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )

class FunctionMetadata(BaseModel):
    schema: str
    name: str
    return_type: Optional[str] = None
    parameters: List[FunctionParameter] = Field(default_factory=list)
    type: FunctionType
    object_type: PostgresObjectType  # Add this field
    volatility: FunctionVolatility
    security_type: SecurityType
    is_strict: bool
    description: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )

def load_fn(
    db_dependency: Any,
    include_schemas: List[str],
) -> Tuple[Dict[str, FunctionMetadata], Dict[str, FunctionMetadata], Dict[str, FunctionMetadata]]:
    """
    Discovers database functions, procedures, and triggers and returns them in separate dictionaries.
    
    Args:
        db_dependency: Database dependency function
        include_schemas: List of schemas to include
        
    Returns:
        Tuple of three dictionaries (functions, procedures, triggers), each mapping
        'schema.name' to FunctionMetadata
    """
    # Initialize our categorized caches
    function_cache: Dict[str, FunctionMetadata] = {}
    procedure_cache: Dict[str, FunctionMetadata] = {}
    trigger_cache: Dict[str, FunctionMetadata] = {}
    
    query = """
        WITH function_info AS (
            SELECT 
                n.nspname as schema,
                p.proname as name,
                pg_get_function_identity_arguments(p.oid) as arguments,
                COALESCE(pg_get_function_result(p.oid), 'void') as return_type,
                p.provolatile as volatility,
                p.prosecdef as security_definer,
                p.proisstrict as is_strict,
                d.description,
                p.proretset as returns_set,
                p.prokind as kind,
                CASE 
                    WHEN EXISTS (
                        SELECT 1 
                        FROM pg_trigger t 
                        WHERE t.tgfoid = p.oid
                    ) OR p.prorettype = 'trigger'::regtype::oid THEN 'trigger'
                    WHEN p.prokind = 'p' THEN 'procedure'
                    ELSE 'function'
                END as object_type,
                -- Get trigger event information if it's a trigger function
                CASE 
                    WHEN EXISTS (
                        SELECT 1 
                        FROM pg_trigger t 
                        WHERE t.tgfoid = p.oid
                    ) THEN (
                        SELECT string_agg(DISTINCT evt.event_type, ', ')
                        FROM (
                            SELECT 
                                CASE tg.tgtype::integer & 2::integer 
                                    WHEN 2 THEN 'BEFORE'
                                    ELSE 'AFTER'
                                END || ' ' ||
                                CASE 
                                    WHEN tg.tgtype::integer & 4::integer = 4 THEN 'INSERT'
                                    WHEN tg.tgtype::integer & 8::integer = 8 THEN 'DELETE'
                                    WHEN tg.tgtype::integer & 16::integer = 16 THEN 'UPDATE'
                                    WHEN tg.tgtype::integer & 32::integer = 32 THEN 'TRUNCATE'
                                END as event_type
                            FROM pg_trigger tg
                            WHERE tg.tgfoid = p.oid
                        ) evt
                    )
                    ELSE NULL
                END as trigger_events
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            LEFT JOIN pg_description d ON p.oid = d.objoid
            LEFT JOIN pg_depend dep ON dep.objid = p.oid 
                AND dep.deptype = 'e'
            LEFT JOIN pg_extension ext ON dep.refobjid = ext.oid
            WHERE ext.extname IS NULL
                AND n.nspname = ANY(:schemas)
                AND p.proname NOT LIKE 'pg_%'
                AND p.oid > (
                    SELECT oid 
                    FROM pg_proc 
                    WHERE proname = 'current_database' 
                    LIMIT 1
                )
                AND NOT EXISTS (
                    SELECT 1 
                    FROM pg_depend d2
                    JOIN pg_extension e2 ON d2.refobjid = e2.oid
                    WHERE d2.objid = p.oid
                )
                AND p.pronamespace > (
                    SELECT oid 
                    FROM pg_namespace 
                    WHERE nspname = 'pg_catalog'
                )
        )
        SELECT * FROM function_info
        ORDER BY schema, name;
    """
    
    def _get_volatility(volatility_char: str) -> FunctionVolatility:
        return {
            'i': FunctionVolatility.IMMUTABLE,
            's': FunctionVolatility.STABLE,
            'v': FunctionVolatility.VOLATILE
        }.get(volatility_char, FunctionVolatility.VOLATILE)

    def _determine_function_type(row: Any) -> FunctionType:
        if row.returns_set:
            return FunctionType.SET_RETURNING
        if "TABLE" in (row.return_type or ""):
            return FunctionType.TABLE
        if row.kind == 'a':
            return FunctionType.AGGREGATE
        if row.kind == 'w':
            return FunctionType.WINDOW
        return FunctionType.SCALAR

    def _parse_parameters(args_str: str) -> List[FunctionParameter]:
        if not args_str:
            return []
        
        parameters = []
        for arg in args_str.split(", "):
            parts = arg.split(" ")
            if len(parts) >= 2:
                param_name = parts[0]
                param_type = " ".join(parts[1:])
                parameters.append(FunctionParameter(
                    name=param_name,
                    type=param_type
                ))
        return parameters

    with next(db_dependency()) as db:
        result = db.execute(
            text(query),
            {"schemas": include_schemas}
        )
        
        for row in result:
                
            fn_type = _determine_function_type(row)
            parameters = _parse_parameters(row.arguments)
            
            metadata = FunctionMetadata(
                schema=row.schema,
                name=row.name,
                return_type=row.return_type if row.return_type else 'void',
                parameters=parameters,
                type=fn_type,
                object_type=PostgresObjectType(row.object_type),
                volatility=_get_volatility(row.volatility),
                security_type=SecurityType.DEFINER if row.security_definer else SecurityType.INVOKER,
                is_strict=row.is_strict,
                description=row.description
            )
            
            # Categorize based on object_type
            match row.object_type:
                case 'trigger': trigger_cache[f"{row.schema}.{row.name}"] = metadata
                case 'procedure': procedure_cache[f"{row.schema}.{row.name}"] = metadata
                case 'function' : function_cache[f"{row.schema}.{row.name}"] = metadata
                case _: 
                    # todo: Add support for other object types
                    raise ValueError(f"Unknown object type: {row.object_type}")

    return function_cache, procedure_cache, trigger_cache


class FunctionBase(BaseModel):
    """Base class for function models"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

def _parse_table_return_type(return_type: str) -> Dict[str, Tuple[Type, Any]]:
    """Parse TABLE and SETOF return types into field definitions."""
    fields = {}
    
    if "TABLE" in return_type:
        # Strip 'TABLE' and parentheses
        columns_str = return_type.replace("TABLE", "").strip("()").strip()
        columns = [col.strip() for col in columns_str.split(",")]
        
        for column in columns:
            name, type_str = column.split(" ", 1)
            field_type = get_eq_type(type_str)
            # Handle ArrayType in table columns
            if isinstance(field_type, ArrayType):
                field_type = List[field_type.item_type]
            fields[name] = (field_type, ...)
                
    return fields

def create_fn_models(
    fn_metadata: FunctionMetadata,
) -> Tuple[Type[BaseModel], Type[BaseModel], bool]:
    """
    Create input and output models for PostgreSQL functions.

    Args:
        fn_metadata (FunctionMetadata): Metadata of the function.
        schema (str): The schema name where the function resides.
        get_eq_type (Callable): Function to map SQL types to Python types.

    Returns:
        Tuple[Type[BaseModel], Type[BaseModel], bool]: Input model, output model, and whether it is a set-returning function.
    """
    # Generate input model fields
    input_fields = {}
    for param in fn_metadata.parameters:
        field_type = get_eq_type(param.type)
        
        # Handle array types
        if isinstance(field_type, ArrayType):
            field_type = List[field_type.item_type]
            
        input_fields[param.name] = (
            field_type if not param.has_default else Optional[field_type],
            Field(default=param.default_value if param.has_default else ...)
        )

    # Create input model
    FunctionInputModel = create_model(
        f"Function_{fn_metadata.name}_Input",
        __base__=FunctionBase,
        **input_fields
    )

    # Generate output model fields based on function type
    if fn_metadata.type in (FunctionType.TABLE, FunctionType.SET_RETURNING):
        output_fields = _parse_table_return_type(fn_metadata.return_type)
        is_set = True
    else:
        output_type = get_eq_type(fn_metadata.return_type)
        if isinstance(output_type, ArrayType):
            output_type = List[output_type.item_type]
        output_fields = {"result": (output_type, ...)}
        is_set = False

    # Create output model
    FunctionOutputModel = create_model(
        f"Function_{fn_metadata.name}_Output",
        __base__=FunctionBase,
        **output_fields
    )

    return FunctionInputModel, FunctionOutputModel, is_set

def gen_fn_route(
    fn_metadata: FunctionMetadata,  # Pass the function cache
    router: APIRouter,
    db_dependency: Callable,
) -> None:
    """Generate route for a specific PostgreSQL function/procedure."""

    FunctionInputModel, FunctionOutputModel, is_set = create_fn_models(fn_metadata)
    is_scalar = fn_metadata.type == FunctionType.SCALAR

    if fn_metadata.object_type == PostgresObjectType.PROCEDURE:
        @router.post(
            f"/{fn_metadata.name}",
            response_model=None,
            tags=[f"{fn_metadata.schema.upper()} Procedures"],
            summary=f"Execute {fn_metadata.name} procedure",
            description=fn_metadata.description or f"Execute the {fn_metadata.name} procedure"
        )
        async def execute_procedure(
            params: FunctionInputModel,
            db: Session = Depends(db_dependency)
        ):
            return _execute_proc(
                db=db,
                params=params,
                fn_name=fn_metadata.name,
                schema=fn_metadata.schema
            )

    else:  # Function route
        @router.post(
            f"/{fn_metadata.name}",
            response_model=List[FunctionOutputModel] if is_set else FunctionOutputModel,
            tags=[f"{fn_metadata.schema.upper()} Functions"],
            summary=f"Execute {fn_metadata.name} function",
            description=fn_metadata.description or f"Execute the {fn_metadata.name} function"
        )
        async def execute_function(
            params: FunctionInputModel,
            db: Session = Depends(db_dependency)
        ):
            return _execute_fn(
                db=db,
                params=params,
                fn_name=fn_metadata.name,
                schema=fn_metadata.schema,
                output_model=FunctionOutputModel,
                is_set=is_set,
                is_scalar=is_scalar
            )

def _execute_proc(
    db: Session,
    params: BaseModel,
    fn_name: str,
    schema: str
) -> Dict[str, str]:
    """Execute a stored procedure."""
    param_list = [f":{p}" for p in params.model_fields.keys()]
    query = f"CALL {schema}.{fn_name}({', '.join(param_list)})"
    db.execute(text(query), params.model_dump())
    return {"status": "success"}

def _execute_fn(
    db: Session,
    params: BaseModel,
    fn_name: str,
    schema: str,
    output_model: Type[BaseModel],
    is_set: bool = False,
    is_scalar: bool = False
) -> Union[List[BaseModel], BaseModel]:
    """Execute a database function."""
    param_list = [f":{p}" for p in params.model_fields.keys()]
    query = f"SELECT * FROM {schema}.{fn_name}({', '.join(param_list)})"
    result = db.execute(text(query), params.model_dump())

    if is_set:
        records = result.fetchall()
        return [output_model.model_validate(dict(r._mapping)) for r in records]
    
    record = result.fetchone()
    if is_scalar:
        transformed_data = {"result": list(record._mapping.values())[0]}
        return output_model.model_validate(transformed_data)
    
    return output_model.model_validate(dict(record._mapping))
