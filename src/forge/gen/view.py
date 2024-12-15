from typing import Dict, List, Optional, Type, Any, Tuple
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import Table, MetaData, Engine, inspect, text

from forge.tools.sql_mapping import get_eq_type, JSONBType, ArrayType

class ViewBase(BaseModel):
    """Base class for Pydantic view models - used for API validation"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

def create_view_model(
    view_table: Table,
    schema: str,
    db_dependency: Any,  # Type hint for the database dependency
) -> Tuple[Type[BaseModel], Type[BaseModel]]:
    """
    Create a Pydantic model for a view.
    The view itself is already represented by the SQLAlchemy Table object.
    """
    """Generate view routes with dynamic JSONB handling."""
    
    # First, get a sample of data to infer JSONB structures
    sample_data = {}
    try:
        with next(db_dependency()) as db:
            query = f"SELECT * FROM {schema}.{view_table.name} LIMIT 1"
            result = db.execute(text(query)).first()
            if result:
                sample_data = dict(result._mapping)
    except Exception as e:
        print(f"Warning: Could not get sample data: {str(e)}")

    # Create query params and response field models
    view_query_fields = {}
    response_fields = {}
    
    for column in view_table.columns:
        column_type = str(column.type)
        nullable = column.nullable
        field_type = get_eq_type(
            column_type,
            sample_data.get(column.name) if 'jsonb' in column_type.lower() else None,
            nullable=nullable
        )
        
        view_query_fields[column.name] = (Optional[str], Field(default=None))
        match field_type:
            case _ if isinstance(field_type, JSONBType):  # * JSONB type
                model = field_type.get_model(f"{view_table.name}_{column.name}")
                match sample_data.get(column.name, []):  # * Infer JSONB structure
                    case _ if isinstance(sample_data.get(column.name, []), list):  # * List of objects
                        response_fields[column.name] = (List[model], Field(default_factory=list))
                    case _:  # * Single object
                        response_fields[column.name] = (Optional[model] if nullable else model, Field(default=None))
            case _ if isinstance(field_type, ArrayType):  # * Array type
                response_fields[column.name] = (List[field_type.item_type], Field(default_factory=list))
            case _:  # * Simple type
                view_query_fields[column.name] = (Optional[field_type], Field(default=None))
                response_fields[column.name] = (field_type, Field(default=None))

    # Create models with proper base classes
    ViewQueryParamsModel = create_model(
        f"View_{view_table.name}_QueryParams",
        __base__=ViewBase,
        **view_query_fields
    )
    
    ViwsResponseModel = create_model(
        f"View_{view_table.name}",
        __base__=ViewBase,
        **response_fields
    )

    return ViewQueryParamsModel, ViwsResponseModel


def load_views(
    metadata: MetaData,
    engine: Engine,
    include_schemas: List[str],
    db_dependency: Any = None,
) -> Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseModel]]]]:
    """
    Returns a dictionary mapping view names to their Table object and Pydantic model

    # Returns dict in the form of:
    {
        "schema.view_name": (Table, (QueryModel, ResultModel)), ...
    }
    """
    view_cache: Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseModel]]]] = {}
    for schema in include_schemas:
        if schema not in include_schemas:
            continue
            
        for table in metadata.tables.values():
            if table.name in inspect(engine).get_view_names(schema=schema):                
                query_model, result_model = create_view_model(table, schema, db_dependency)
                
                # Store the Table object and the Pydantic model
                view_cache[f"{schema}.{table.name}"] = (table, (query_model, result_model))
    
    return view_cache
