import json
from typing import Callable, Dict, List, Optional, Type, Any, Tuple
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import Table, MetaData, Engine, inspect, text
from sqlalchemy.orm import Session

from forge.tools.sql_mapping import get_eq_type, JSONBType, ArrayType


class ViewBase(BaseModel):
    """Base class for Pydantic view models - used for API validation"""

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, arbitrary_types_allowed=True
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
            sample_data.get(column.name) if "jsonb" in column_type.lower() else None,
            nullable=nullable,
        )

        view_query_fields[column.name] = (Optional[str], Field(default=None))
        match field_type:
            case _ if isinstance(field_type, JSONBType):  # * JSONB type
                model = field_type.get_model(f"{view_table.name}_{column.name}")
                match sample_data.get(column.name, []):  # * Infer JSONB structure
                    case _ if isinstance(
                        sample_data.get(column.name, []), list
                    ):  # * List of objects
                        response_fields[column.name] = (
                            List[model],
                            Field(default_factory=list),
                        )
                    case _:  # * Single object
                        response_fields[column.name] = (
                            Optional[model] if nullable else model,
                            Field(default=None),
                        )
            case _ if isinstance(field_type, ArrayType):  # * Array type
                response_fields[column.name] = (
                    List[field_type.item_type],
                    Field(default_factory=list),
                )
            case _:  # * Simple type
                view_query_fields[column.name] = (
                    Optional[field_type],
                    Field(default=None),
                )
                response_fields[column.name] = (field_type, Field(default=None))

    # Create models with proper base classes
    ViewQueryParamsModel = create_model(
        f"View_{view_table.name}_QueryParams", __base__=ViewBase, **view_query_fields
    )

    ViwsResponseModel = create_model(
        f"View_{view_table.name}", __base__=ViewBase, **response_fields
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
                query_model, result_model = create_view_model(
                    table, schema, db_dependency
                )

                # Store the Table object and the Pydantic model
                view_cache[f"{schema}.{table.name}"] = (
                    table,
                    (query_model, result_model),
                )

    return view_cache


def gen_view_route(
    table_data: Tuple[Table, Tuple[Type[BaseModel], Type[BaseModel]]],
    router: APIRouter,
    db_dependency: Callable,
) -> None:
    """
    Generate FastAPI route for a database view.

    Args:
        table_data: Tuple containing (Table, (QueryModel, ResponseModel))
        router: FastAPI router instance
        db_dependency: Database session dependency
    """
    table, (query_model, response_model) = table_data
    schema = table.schema
    view_name = table.name

    @router.get(
        f"/{view_name}",
        response_model=List[response_model],
        # tags=[f"{schema.upper()} Views"],
        summary=f"Get {view_name} view data",
        description=f"Retrieve records from the {view_name} view with optional filtering",
    )
    async def get_view_data(
        db: Session = Depends(db_dependency),
        filters: query_model = Depends(),
    ) -> List[response_model]:
        # Build query with filters
        query_parts = [f"SELECT * FROM {schema}.{table.name}"]
        params = {}

        # Handle filters
        filter_conditions = []
        for field_name, value in filters.model_dump(exclude_unset=True).items():
            if value is not None:
                column = getattr(table.c, field_name)
                if isinstance(get_eq_type(str(column.type)), (JSONBType, ArrayType)):
                    continue
                else:
                    param_name = f"param_{field_name}"
                    filter_conditions.append(f"{field_name} = :{param_name}")
                    params[param_name] = value

        if filter_conditions:
            query_parts.append("WHERE " + " AND ".join(filter_conditions))

        # Execute query
        result = db.execute(text(" ".join(query_parts)), params)

        # Process results
        processed_records = []
        for row in result:
            record_dict = dict(row._mapping)
            processed_record = {}

            # Process each column value
            for column_name, value in record_dict.items():
                column = table.c[column_name]
                field_type = get_eq_type(str(column.type), value)

                if isinstance(field_type, JSONBType):
                    if value is not None:
                        # Parse JSONB data
                        if isinstance(value, str):
                            json_data = json.loads(value)
                        else:
                            json_data = value
                        processed_record[column_name] = json_data
                    else:
                        processed_record[column_name] = None
                elif isinstance(field_type, ArrayType):
                    if value is not None:
                        if isinstance(value, str):
                            cleaned_value = value.strip("{}").split(",")
                            processed_record[column_name] = [
                                field_type.item_type(item.strip('"'))
                                for item in cleaned_value
                                if item.strip()
                            ]
                        elif isinstance(value, list):
                            processed_record[column_name] = [
                                field_type.item_type(item)
                                for item in value
                                if item is not None
                            ]
                        else:
                            processed_record[column_name] = value
                    else:
                        processed_record[column_name] = []
                else:
                    processed_record[column_name] = value

            processed_records.append(processed_record)

        # Validate records using the response model
        validated_records = []
        for record in processed_records:
            try:
                validated_record = response_model.model_validate(record)
                validated_records.append(validated_record)
            except Exception as e:
                print(f"Validation error for record in {table.name}: {record}")
                print(f"Error: {str(e)}")
                raise

        return validated_records
