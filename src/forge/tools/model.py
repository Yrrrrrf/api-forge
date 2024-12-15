"""
ModelForge: Enhanced model management for database entities.
Handles Pydantic and SQLAlchemy model generation, caching, and type mapping.
"""
from typing import Dict, List, Optional, Tuple, Type, Any
from pydantic import BaseModel, Field, ConfigDict, create_model
from sqlalchemy import Column, Table, inspect, Enum as SQLAlchemyEnum

from forge.gen.enum import EnumInfo
from forge.gen.fn import FunctionMetadata
from forge.gen.table import BaseSQLModel
from forge.tools.sql_mapping import get_eq_type, JSONBType
from forge.tools.db import DBForge
from forge.core.logging import *


#  todo: Add some utility for the 'exclude_tables' field
class ModelForge(BaseModel):
    """
    Manages model generation and caching for database entities.
    Handles both Pydantic and SQLAlchemy models with support for enums.
    """
    db_manager: DBForge = Field(..., description="Database manager instance")
    include_schemas: List[str] = Field(..., description="Schemas to include in model generation")
    exclude_tables: List[str] = Field(default_factory=list)

    # ^ TABLE cache:    { name: (Table, (PydanticModel, SQLAlchemyModel)) }
    model_cache: Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseSQLModel]]]] = Field(default_factory=dict)
    # ^ VIEW cache:     { name: (Table, (QueryModel, ResultModel)) }
    view_cache: Dict[str, Tuple[Table, Tuple[Type[BaseModel], Type[BaseModel]]]] = Field(default_factory=dict)
    # ^ ENUM cache:     { name: EnumInfo , ... }
    enum_cache: Dict[str, EnumInfo] = Field(default_factory=dict)
    # ^ FN cache:       { name: FunctionMetadata , ... }
    fn_cache: Dict[str, FunctionMetadata] = Field(default_factory=dict)
    proc_cache: Dict[str, FunctionMetadata] = Field(default_factory=dict)
    trig_cache: Dict[str, FunctionMetadata] = Field(default_factory=dict)


    model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')

    def __init__(self, **data):
        super().__init__(**data)
        self._load_models()
        self._load_enums()
        self._load_views()
        self._load_fn()

    def _load_enums(self) -> None:
        from forge.gen.enum import load_enums
        self.enum_cache = load_enums(
            metadata=self.db_manager.metadata,
            engine=self.db_manager.engine,
            include_schemas=self.include_schemas,
            exclude_tables=self.exclude_tables
        )

    def _load_models(self) -> None:
        from forge.gen.table import load_tables
        self.model_cache = load_tables(
            metadata=self.db_manager.metadata,
            engine=self.db_manager.engine,
            include_schemas=self.include_schemas,
            exclude_tables=self.exclude_tables
        )

    def _load_views(self) -> None:
        """Load and cache views as Table objects with associated Pydantic models"""
        from forge.gen.view import load_views
        self.view_cache = load_views(
            metadata=self.db_manager.metadata,
            engine=self.db_manager.engine,
            include_schemas=self.include_schemas,
            db_dependency=self.db_manager.get_db
        )

    def _load_fn(self) -> None:
        from forge.gen.fn import load_fn
        fn, proc, trig = load_fn(
            db_dependency=self.db_manager.get_db,
            include_schemas=self.include_schemas
        )
        # [print(f"{cyan('Function:')} {bold(name)}") for name in fn]
        # [print(f"{cyan('Procedure:')} {bold(name)}") for name in proc]
        # [print(f"{cyan('Trigger:')} {bold(name)}") for name in trig]

        self.fn_cache = fn
        self.proc_cache = proc
        self.trig_cache = trig


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
