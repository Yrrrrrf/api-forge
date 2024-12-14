"""
ModelForge: Enhanced model management for database entities.
Handles Pydantic and SQLAlchemy model generation, caching, and type mapping.
"""
from typing import Dict, List, Optional, Type, Any
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import Column, Table, inspect, Enum as SQLAlchemyEnum
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.declarative import declared_attr

from enum import Enum as PyEnum

from forge.db import DBForge
from forge.utils import *

class EnumInfo(BaseModel):
    """Store information about database enums."""
    name: str
    values: List[str]
    python_enum: Optional[Type[PyEnum]] = None
    schema: Optional[str] = None

    def create_enum(self) -> Type[PyEnum]:
        """Create a Python Enum from the enum information."""
        if not self.python_enum:
            self.python_enum = PyEnum(self.name, {v: v for v in self.values})
        return self.python_enum


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

# todo: Add some utility for the 'exclude_tables' field
class ModelForge(BaseModel):
    """
    Manages model generation and caching for database entities.
    Handles both Pydantic and SQLAlchemy models with support for enums.
    """
    db_manager: DBForge = Field(..., description="Database manager instance")
    include_schemas: List[str] = Field(..., description="Schemas to include in model generation")
    exclude_tables: List[str] = Field(default_factory=list)

    # Caches
    model_cache: Dict[str, tuple[Type[BaseModel], Type[BaseSQLModel]]] = Field(default_factory=dict)
    enum_cache: Dict[str, EnumInfo] = Field(default_factory=dict)
    view_cache: Dict[str, Table] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')

    def __init__(self, **data):
        super().__init__(**data)
        self._load_models()
        self._load_enums()
        self._load_views()

    def _load_enums(self) -> None:
        """Load and cache enum types from database, properly handling views."""
        # First pass: collect all unique enum value sets from base tables
        for schema in self.include_schemas:
            for table in self.db_manager.metadata.tables.values():
                if table.name in inspect(self.db_manager.engine).get_table_names(schema=schema):
                    for column in table.columns:
                        if isinstance(column.type, SQLAlchemyEnum):
                            enum_name = f"{column.name}_enum"
                            if enum_name not in self.enum_cache:
                                self.enum_cache[enum_name] = EnumInfo(
                                    name=enum_name,
                                    values=list(column.type.enums),
                                    python_enum=PyEnum(enum_name, {v: v for v in column.type.enums})
                                )
                                # print(f"\t{bold(enum_name):>32} {gray(column.type):>24} {italic(column.type.enums)}")

    def _load_models(self) -> None:
        """Generate and register both Pydantic and SQLAlchemy models for a table."""
        for schema in self.db_manager.metadata._schemas:
            for table in self.db_manager.metadata.tables.values():
                if table.name in inspect(self.db_manager.engine).get_table_names(schema=schema):
                    fields = {}
                    for column in table.columns:
                        field_type = get_eq_type(str(column.type))
                        fields[column.name] = (
                            Optional[field_type] if column.nullable else field_type,
                            Field(default=None if column.nullable else ...)
                        )

                    # * GET THE PYDANTIC MODEL
                    pydantic_model: Type[BaseModel] = create_model(
                        f"Pydantic_{table.name}",
                        __config__=ConfigDict(from_attributes=True),
                        **fields
                    )
                    # * GET THE SQLALCHEMY MODEL
                    sqlalchemy_model: Type[BaseSQLModel] = type(
                        f"SQLAlchemy_{table.name.lower()}",
                        (BaseSQLModel,),
                        { '__table__': table, '__tablename__': table.name}
                    )
                    self.model_cache[f"{table.schema}.{table.name}"] = pydantic_model, sqlalchemy_model

    def _load_views(self) -> None:
        """Load and cache view tables from the database."""
        for schema in self.db_manager.metadata._schemas:
            for table in self.db_manager.metadata.tables.values():
                if table.name in inspect(self.db_manager.engine).get_view_names(schema=schema):
                    self.view_cache[table.name] = table

    def log_metadata_stats(self) -> None:
        """Print metadata statistics for the database with improved formatting."""
        inspector = inspect(self.db_manager.engine)
        print(header("ModelForge Statistics"))
        print(f"\n{cyan(bullet('Schemas'))}: {bright(len(self.include_schemas))}")

        for schema in self.include_schemas:
            table_count = len(inspector.get_table_names(schema=schema))
            view_count = len(inspector.get_view_names(schema=schema))
            print(f"\t{magenta(arrow(schema)):<32}{dim('Tables:')} {green(f"{table_count:>4}")}\t{dim('Views: ')} {blue(f"{view_count:>4}")}")

        # Summary statistics in a structured format
        print(f"\n{cyan('Summary Statistics:')}")
        print(f"  {bullet(dim('Enums')):<16} {yellow(f"{len(self.enum_cache):>4}")}")
        print(f"  {bullet(dim('Views')):<16} {blue(f"{len(self.view_cache):>4}")}")
        print(f"  {bullet(dim('Models')):<16} {green(f"{len(self.model_cache):>4}")}")
        
        print(f"\n{bright('Total Components:')} {len(self.enum_cache) + len(self.view_cache) + len(self.model_cache)}\n")

    def log_schema_tables(self) -> None:
        for schema in self.include_schemas:
            print(f"\n{'Schema:'} {bold(schema)}")
            for table in self.db_manager.metadata.tables.values():
                if table.name in inspect(self.db_manager.engine).get_table_names(schema=schema):
                    print_table_structure(table)

    def log_schema_views(self) -> None:
        for schema in self.include_schemas:
            print(f"\n{'Schema:'} {bold(schema)}")
            for table in self.db_manager.metadata.tables.values():
                if table.name in inspect(self.db_manager.engine).get_view_names(schema=schema):
                    print_table_structure(table)

def print_table_structure(table: Table) -> None:
    """Print detailed table structure with columns and enums."""
    
    def get_column_flags(column: Column) -> List[str]:
        """Get formatted flags for a column."""
        flags = []
        if column.primary_key: flags.append(f'{green("PK")}')
        if column.foreign_keys:
            ref_table = next(iter(column.foreign_keys)).column.table
            flags.append(f'{blue(f"FK → {ref_table.schema}.{bold(ref_table.name)}")}')
        return flags

    def get_base_type(type_: Any) -> str:
        """Extract base type from Optional types."""
        type_str = str(type_)  # Get the string representation

        if "typing.Optional" in type_str:
            return re.search(r"\[(.*)\]", type_str).group(1).split(".")[-1]
        
        match isinstance(type_, type):  # Handle non-Optional types
            case True: return type_.__name__  # ^ Return class name if it's a type
            case False: return str(type_)  # ^ Return string representation otherwise

    # Print table name and comment
    print(f"\t{cyan(table.schema)}.{bold(cyan(table.name))}", end=' ')
    match table.comment:
        case None: print()
        case _: print(f"({italic(gray(table.comment))})")

    # Print columns
    for column in table.columns:
        flags_str = ' '.join(get_column_flags(column))
        py_type = get_eq_type(str(column.type))
        nullable = "" if column.nullable else "*"
        
        # # Determine type string and values based on column type
        match column.type:
            case _  if isinstance(column.type, SQLAlchemyEnum):
                # type_str = f"{yellow(column.type.name)}"
                type_str = f"{yellow(f"Enum({column.type.name})")}"
                values = f"{gray(str(column.type.enums))}"
            case _:
                values = ""
                if isinstance(py_type, JSONBType): type_str = magenta("JSONB")
                else: type_str = magenta(get_base_type(py_type))

        print(f"\t\t{column.name:<24} {red(f'{nullable:<2}')}{gray(str(column.type)[:20]):<32} "
              f"{type_str:<16} {flags_str} {values if values else ''}")

    print()
