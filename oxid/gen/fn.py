from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Tuple
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, create_model
from pytest import Session
from sqlalchemy import text
from forge.utils import *

from forge.utils.sql_types import ArrayType, get_eq_type


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

# ? FnForge class ------------------------------------------------------------------
# ? 
# ? This class is responsible for discovering functions in a PostgreSQL database
# ? and generating Pydantic models for input and output parameters.
# ? 
# ? The class is designed to be used as a dependency in FastAPI applications.
# ?.todo: Add some way to generalize this to more databases than just PostgreSQL

class FnForge(BaseModel):
    """Handles PostgreSQL function discovery and route generation."""
    db_dependency: Callable
    include_schemas: List[str]
    exclude_functions: List[str] = Field(default_factory=list)
    
    # Caches for models and metadata
    function_cache: Dict[str, FunctionMetadata] = Field(default_factory=dict)
    model_cache: Dict[str, Tuple[Type[BaseModel], Type[BaseModel]]] = Field(default_factory=dict)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='allow'
    )

    def _get_object_type(self, prokind: str) -> PostgresObjectType:
        """Convert PostgreSQL function kind code to PostgresObjectType enum."""
        return {
            'f': PostgresObjectType.FUNCTION,
            'p': PostgresObjectType.PROCEDURE,
            'a': PostgresObjectType.AGGREGATE,
            'w': PostgresObjectType.WINDOW,
            't': PostgresObjectType.TRIGGER
        }.get(prokind, PostgresObjectType.FUNCTION)

    def discover_functions(self) -> None:
        query = """
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
                AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                AND p.proname NOT LIKE 'pg_%%'
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
            ORDER BY n.nspname, p.proname;
        """
        
        with next(self.db_dependency()) as db:
            result = db.execute(text(query))
            
            for row in result:
                if row.name in self.exclude_functions:
                    continue
                    
                fn_type = self._determine_function_type(row)
                parameters = self._parse_parameters(row.arguments)

                metadata = FunctionMetadata(
                    schema=row.schema,
                    name=row.name,
                    return_type=row.return_type if row.return_type else 'void',
                    parameters=parameters,
                    type=fn_type,
                    object_type=PostgresObjectType(row.object_type),  # Direct conversion from SQL result
                    volatility=self._get_volatility(row.volatility),
                    security_type=SecurityType.DEFINER if row.security_definer else SecurityType.INVOKER,
                    is_strict=row.is_strict,
                    description=row.description
                )
                
                self.function_cache[f"{row.schema}.{row.name}"] = metadata

    def generate_function_models(self) -> None:
        """Generate input and output models for functions."""
        for func_id, metadata in self.function_cache.items():
            # Generate input model
            input_fields = {}
            for param in metadata.parameters:
                field_type = get_eq_type(param.type)
                
                # Handle ArrayType case
                if isinstance(field_type, ArrayType):
                    field_type = List[field_type.item_type]
                
                input_fields[param.name] = (
                    field_type if param.has_default else field_type,
                    Field(default=param.default_value if param.has_default else ...)
                )
            
            # Create input model
            input_model = create_model(
                f"{metadata.name}_Input",
                __base__=BaseModel,
                **input_fields
            )
            
            # Generate output model
            if metadata.type in (FunctionType.TABLE, FunctionType.SET_RETURNING):
                output_fields = self._parse_table_return(metadata.return_type)
            else:
                output_type = get_eq_type(metadata.return_type)
                # Handle ArrayType in output
                if isinstance(output_type, ArrayType):
                    output_type = List[output_type.item_type]
                output_fields = {"result": (output_type, ...)}
                # Use the function name as the field
                # output_fields = {metadata.name: (output_type, ...)}
            output_model = create_model(
                f"{metadata.name}_Output",
                __base__=BaseModel,
                **output_fields
            )
            
            # Cache models
            self.model_cache[func_id] = (input_model, output_model)

    def _parse_table_return(self, return_type: str) -> Dict[str, Tuple[Type, Any]]:
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

    def _determine_function_type(self, row: Any) -> FunctionType:
        if row.returns_set:
            return FunctionType.SET_RETURNING
        if "TABLE" in (row.return_type or ""):
            return FunctionType.TABLE
        if row.kind == 'a':
            return FunctionType.AGGREGATE
        if row.kind == 'w':
            return FunctionType.WINDOW
        return FunctionType.SCALAR

    def _get_volatility(self, volatility_char: str) -> FunctionVolatility:
        return {
            'i': FunctionVolatility.IMMUTABLE,
            's': FunctionVolatility.STABLE,
            'v': FunctionVolatility.VOLATILE
        }.get(volatility_char, FunctionVolatility.VOLATILE)

    def _parse_parameters(self, args_str: str) -> List[FunctionParameter]:
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

    def log_metadata_stats(self) -> None:
        """Print statistics about discovered functions."""
        print(header("FunctionForge Statistics"))

        # Collect statistics
        function_counts = {}
        active_types = set()

        # First pass to get max lengths
        max_schema_len = len("Schema")  # minimum width for header
        for metadata in self.function_cache.values():
            max_schema_len = max(max_schema_len, visible_len(metadata.schema))
            if metadata.schema not in function_counts:
                function_counts[metadata.schema] = {
                    FunctionType.SCALAR: 0,
                    FunctionType.TABLE: 0,
                    FunctionType.SET_RETURNING: 0,
                    FunctionType.AGGREGATE: 0,
                    FunctionType.WINDOW: 0
                }
            function_counts[metadata.schema][metadata.type] += 1
            if function_counts[metadata.schema][metadata.type] > 0:
                active_types.add(metadata.type)

        # Headers with tabs
        print(f"Schema\t\tscalar\tset\tTotal")
        
        # Print rows
        for schema, counts in function_counts.items():
            schema_total = sum(counts.values())
            scalar_count = counts[FunctionType.SCALAR]
            set_count = counts[FunctionType.SET_RETURNING]
            
            colored_schema = magenta(schema.rjust(max_schema_len))
            colored_scalar = green(str(scalar_count).rjust(2))
            colored_set = green(str(set_count).rjust(1))
            colored_total = bright(str(schema_total).rjust(2))
            
            print(f"{colored_schema}\t{colored_scalar}\t{colored_set}\t{colored_total}")
        
        # Print totals with proper spacing
        total_scalar = str(sum(counts[FunctionType.SCALAR] for counts in function_counts.values())).rjust(2)
        total_set = str(sum(counts[FunctionType.SET_RETURNING] for counts in function_counts.values())).rjust(1)
        grand_total = str(sum(sum(counts.values()) for counts in function_counts.values())).rjust(2)
        
        # Color the totals after right justification
        colored_total_scalar = bright(total_scalar)
        colored_total_set = bright(total_set)
        colored_grand_total = bright(grand_total)
        
        print(f"{'Total'.rjust(max_schema_len)}\t{colored_total_scalar}\t{colored_total_set}\t{colored_grand_total}")

    def generate_function_routes(self, router: APIRouter) -> None:
        """Generate routes for all discovered functions."""
        for func_id, metadata in self.function_cache.items():
            if metadata.object_type not in [PostgresObjectType.TRIGGER]:  # Skip triggers
                gen_fn_route(
                    schema=metadata.schema,
                    function_metadata=metadata,
                    router=router,
                    db_dependency=self.db_dependency,
                    get_eq_type=get_eq_type
                )

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


def gen_fn_route(
    schema: str,
    function_metadata: FunctionMetadata,
    router: APIRouter,
    db_dependency: Callable,
    get_eq_type: Callable
) -> None:
    """Generate routes for PostgreSQL functions with proper type handling."""
    
    # Generate input model fields
    input_fields = {}
    for param in function_metadata.parameters:
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
        f"Function_{function_metadata.name}_Input",
        __base__=FunctionBase,
        **input_fields
    )

    # Generate output model fields based on function type
    if function_metadata.type in (FunctionType.TABLE, FunctionType.SET_RETURNING):
        output_fields = _parse_table_return_type(function_metadata.return_type)
        is_set = True
    else:
        output_type = get_eq_type(function_metadata.return_type)
        if isinstance(output_type, ArrayType):
            output_type = List[output_type.item_type]
        output_fields = {"result": (output_type, ...)}
        is_set = False

    # Create output model
    FunctionOutputModel = create_model(
        f"Function_{function_metadata.name}_Output",
        __base__=FunctionBase,
        **output_fields
    )

    # Generate the route based on function type
    if function_metadata.object_type == PostgresObjectType.PROCEDURE:
        @router.post(
            f"/{function_metadata.name}",
            response_model=None,
            tags=[f"{schema.upper()} Procedures"],
            summary=f"Execute {function_metadata.name} procedure",
            description=function_metadata.description or f"Execute the {function_metadata.name} procedure"
        )
        async def execute_procedure(
            params: FunctionInputModel,
            db: Session = Depends(db_dependency)
        ):
            # Build procedure call
            param_list = [f":{p}" for p in input_fields.keys()]
            query = f"CALL {schema}.{function_metadata.name}({', '.join(param_list)})"
            await db.execute(text(query), params.model_dump())
            return {"status": "success"}

    else:
        @router.post(
            f"/{function_metadata.name}",
            response_model=List[FunctionOutputModel] if is_set else FunctionOutputModel,
            tags=[f"{schema.upper()} Functions"],
            summary=f"Execute {function_metadata.name} function",
            description=function_metadata.description or f"Execute the {function_metadata.name} function"
        )
        def execute_function(  # <-- This is async
            params: FunctionInputModel,
            db: Session = Depends(db_dependency)
        ):
            # Build function call
            param_list = [f":{p}" for p in input_fields.keys()]
            query = f"SELECT * FROM {schema}.{function_metadata.name}({', '.join(param_list)})"
            result = db.execute(text(query), params.model_dump())

            if is_set:
                records = result.fetchall()
                return [FunctionOutputModel.model_validate(dict(r._mapping)) for r in records]
            else:
                record = result.fetchone()
                # Transform the data to match your model
                transformed_data = {"result": list(record._mapping.values())[0]}  # Get the first value
                return FunctionOutputModel.model_validate(transformed_data)
                # return FunctionOutputModel.model_validate(dict(record._mapping))
