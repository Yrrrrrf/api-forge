from typing import List, Optional, Type, Dict
from pydantic import BaseModel
from sqlalchemy import MetaData, Engine, inspect, Enum as SQLAlchemyEnum
from enum import Enum as PyEnum


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


def load_enums(
    metadata: MetaData,
    engine: Engine,
    include_schemas: List[str],
    exclude_tables: List[str],
) -> Dict[str, EnumInfo]:
    """Load and cache enum types from database, properly handling views."""
    enum_cache: Dict[str, EnumInfo] = {}

    # First pass: collect all unique enum value sets from base tables
    for schema in include_schemas:
        for table in metadata.tables.values():
            if (
                table.name in inspect(engine).get_table_names(schema=schema)
                and table.name not in exclude_tables
            ):
                for column in table.columns:
                    if isinstance(column.type, SQLAlchemyEnum):
                        enum_name = f"{column.name}_enum"
                        # todo: Check if the generated enum schema is correct
                        # ^ I've the hint that the schema is not being used correctly...
                        # ^ And it just takes the schema of the table, which is not correct
                        # ^ Sometimes this is not a problem, but it can be a problem
                        # . Sometimes this can be a problem, but I'm not sure if it's a big one
                        if enum_name not in enum_cache:
                            enum_cache[enum_name] = EnumInfo(
                                name=enum_name,
                                values=list(column.type.enums),
                                python_enum=PyEnum(
                                    enum_name, {v: v for v in column.type.enums}
                                ),
                                schema=schema,
                            )

    return enum_cache
