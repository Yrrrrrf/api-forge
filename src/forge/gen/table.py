from typing import Dict, List, Optional, Type, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import MetaData, Engine, Table, inspect, text
from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy.ext.declarative import declared_attr

from forge.gen import CRUD
from forge.tools.sql_mapping import ArrayType, JSONBType, get_eq_type

from typing import *
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.declarative import declared_attr


class BaseSQLModel(DeclarativeBase):
    """Base class for all generated SQLAlchemy models."""
    
    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower()

    @classmethod
    def get_fields(cls) -> Dict[str, Any]:
        """Get all model fields."""
        return {
            column.name: column for column in cls.__table__.columns
        }

def load_tables(
    metadata: MetaData,
    engine: Engine,
    include_schemas: List[str],
    exclude_tables: List[str] = [],
    db_dependency: Any = None  # Add db_dependency parameter
) -> Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseSQLModel]]]]:
    """Generate and return both Pydantic and SQLAlchemy models for tables."""
    model_cache: Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseSQLModel]]]] = {}
    
    for schema in metadata._schemas:
        if schema not in include_schemas:
            continue

        for table in metadata.tables.values():
            if (table.name in inspect(engine).get_table_names(schema=schema) and 
                table.name not in exclude_tables):
                
                # Get sample data for JSONB fields
                sample_data = {}
                # if db_dependency:
                #     try:
                #         with next(db_dependency()) as db:
                #             query = f"SELECT * FROM {schema}.{table.name} LIMIT 1"
                #             result = db.execute(text(query)).first()
                #             if result:
                #                 sample_data = dict(result._mapping)
                #     except Exception as e:
                #         print(f"Warning: Could not get sample data for {table.name}: {str(e)}")

                fields = {}
                for column in table.columns:
                    column_type = str(column.type)
                    field_type = get_eq_type(
                        column_type,
                        sample_data.get(column.name) if 'jsonb' in column_type.lower() else None,
                        nullable=column.nullable
                    )
                    
                    match field_type:
                        case _ if isinstance(field_type, JSONBType):
                            model = field_type.get_model(f"{table.name}_{column.name}")
                            if sample_data.get(column.name) and isinstance(sample_data[column.name], list):
                                fields[column.name] = (
                                    List[model] if not column.nullable else Optional[List[model]],
                                    Field(default_factory=list if not column.nullable else None)
                                )
                            else:
                                fields[column.name] = (
                                    model if not column.nullable else Optional[model],
                                    Field(default=... if not column.nullable else None)
                                )
                        case _ if isinstance(field_type, ArrayType):
                            fields[column.name] = (
                                List[field_type.item_type] if not column.nullable else Optional[List[field_type.item_type]],
                                Field(default_factory=list if not column.nullable else None)
                            )
                        case _:
                            fields[column.name] = (
                                field_type if not column.nullable else Optional[field_type],
                                Field(default=... if not column.nullable else None)
                            )

                # Create Pydantic model with explicit configuration
                model_config = ConfigDict(
                    from_attributes=True,
                    arbitrary_types_allowed=True,
                    populate_by_name=True
                )

                pydantic_model = create_model(
                    f"Pydantic_{table.name}",
                    __config__=model_config,
                    **fields
                )

                # Create SQLAlchemy model
                sqlalchemy_model = type(
                    f"SQLAlchemy_{table.name.lower()}",
                    (BaseSQLModel,),
                    {
                        '__table__': table,
                        '__tablename__': table.name,
                        'model_config': model_config
                    }
                )

                model_cache[f"{schema}.{table.name}"] = (table, (pydantic_model, sqlalchemy_model))
    
    return model_cache

def gen_table_crud(
    table_data: Tuple[Table, Tuple[Type[BaseModel], Type[BaseSQLModel]]],
    router: APIRouter,
    db_dependency: Callable,
) -> None:
    """
    Generate CRUD routes for a database table.
    
    Args:
        table_data: Tuple containing (Table, (PydanticModel, SQLAlchemyModel))
        router: FastAPI router instance
        db_dependency: Database session dependency
        tags: Optional list of tags for the routes
        prefix: Optional prefix for the routes
    """
    table, (pydantic_model, sqlalchemy_model) = table_data
    CRUD(
        table=table,
        pydantic_model=pydantic_model,
        sqlalchemy_model=sqlalchemy_model,
        router=router,
        db_dependency=db_dependency,
        prefix=f"/{table.schema}"
    ).generate_all()
