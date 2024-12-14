from typing import Dict, List, Optional, Type, Any, Callable
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Table, text
from sqlalchemy.orm import Session
from pydantic.main import create_model
import json

from forge.utils.sql_types import ArrayType, JSONBType

class ViewBase(BaseModel):
    """Base class for view models"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

def generate_view_routes(
    view_table: Table,
    schema: str,
    router: APIRouter,
    db_dependency: Callable,
    get_eq_type: Callable
) -> None:
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

        # if isinstance(field_type, JSONBType):
        #     # Create dynamic model for JSONB fields
        #     model = field_type.get_model(f"{view_table.name}_{column.name}")
        #     if isinstance(sample_data.get(column.name, []), list):
        #         view_query_fields[column.name] = (Optional[str], Field(default=None))
        #         response_fields[column.name] = (List[model], Field(default_factory=list))
        #     else:
        #         view_query_fields[column.name] = (Optional[str], Field(default=None))
        #         response_fields[column.name] = (Optional[model] if nullable else model, Field(default=None))
        # elif isinstance(field_type, ArrayType):
        #     view_query_fields[column.name] = (Optional[str], Field(default=None))
        #     response_fields[column.name] = (List[field_type.item_type], Field(default_factory=list))
        # else:
        #     view_query_fields[column.name] = (Optional[field_type], Field(default=None))
        #     response_fields[column.name] = (field_type, Field(default=None))

    # Create models with proper base classes
    ViewQueryParams = create_model(
        f"View_{view_table.name}_QueryParams",
        __base__=ViewBase,
        **view_query_fields
    )
    
    ViewResponseModel = create_model(
        f"View_{view_table.name}",
        __base__=ViewBase,
        **response_fields
    )

    @router.get(
        f"/{view_table.name}",
        response_model=List[ViewResponseModel],
        tags=[f"{schema.upper()} Views"],
        summary=f"Get {view_table.name} view data",
        description=f"Retrieve records from the {view_table.name} view with optional filtering"
    )
    def get_view_data(
        db: Session = Depends(db_dependency),
        filters: ViewQueryParams = Depends(),
    ) -> List[ViewResponseModel]:
        query_parts = [f'SELECT * FROM {schema}.{view_table.name}']
        params = {}

        # Handle filters
        filter_conditions = []
        for field_name, value in filters.model_dump(exclude_unset=True).items():
            if value is not None:
                column = getattr(view_table.c, field_name)
                if isinstance(get_eq_type(str(column.type)), (JSONBType, ArrayType)):
                    # Skip JSONB and array filtering for now
                    continue
                else:
                    param_name = f"param_{field_name}"
                    filter_conditions.append(f"{field_name} = :{param_name}")
                    params[param_name] = value

        if filter_conditions:
            query_parts.append("WHERE " + " AND ".join(filter_conditions))

        # Execute query and process results
        result = db.execute(text(" ".join(query_parts)), params)
        
        processed_records = []
        for row in result:
            record_dict = dict(row._mapping)
            processed_record = {}
            
            for column_name, value in record_dict.items():
                column = view_table.c[column_name]
                field_type = get_eq_type(str(column.type), value, nullable=column.nullable)

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
                            cleaned_value = value.strip('{}').split(',')
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

        # Validate each record
        validated_records = []
        for record in processed_records:
            try:
                validated_record = ViewResponseModel.model_validate(record)
                validated_records.append(validated_record)
            except Exception as e:
                print(f"Validation error for record: {record}")
                print(f"Error: {str(e)}")
                raise

        return validated_records
