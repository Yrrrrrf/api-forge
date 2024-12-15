from typing import Dict, List, Optional, Type, Any
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import MetaData, Engine, Table, inspect
from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy.ext.declarative import declared_attr

from forge.tools.sql_mapping import get_eq_type

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
    exclude_tables: List[str] = []
) -> Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseSQLModel]]]]:
    """Generate and return both Pydantic and SQLAlchemy models for tables."""
    model_cache: Dict[str, tuple[Type[BaseModel], Type[BaseSQLModel]]] = {}
    
    for schema in metadata._schemas:
        if schema not in include_schemas:
            continue

        for table in metadata.tables.values():
            if (table.name in inspect(engine).get_table_names(schema=schema) and 
                table.name not in exclude_tables):
                fields = {}
                for column in table.columns:
                    field_type = get_eq_type(str(column.type))
                    fields[column.name] = (
                        Optional[field_type] if column.nullable else field_type,
                        Field(default=None if column.nullable else ...)
                    )

                # Get the Pydantic model
                pydantic_model: Type[BaseModel] = create_model(
                    f"Pydantic_{table.name}",
                    __config__=ConfigDict(from_attributes=True),
                    **fields
                )
                # Get the SQLAlchemy model
                sqlalchemy_model: Type[BaseSQLModel] = type(
                    f"SQLAlchemy_{table.name.lower()}",
                    (BaseSQLModel,),
                    { '__table__': table, '__tablename__': table.name}
                )
                model_cache[f"{table.schema}.{table.name}"] = (table, (pydantic_model, sqlalchemy_model))
    
    return model_cache