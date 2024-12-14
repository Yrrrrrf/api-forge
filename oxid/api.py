"""
APIForge: Enhanced API route generation with proper model handling.
Integrates with ModelForge for model management and route generation.
"""
from typing import Dict, List, Optional
from enum import Enum
# import session
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Table, text
from pydantic.main import create_model

from forge.gen.view import generate_view_routes
from forge.utils import *
from forge.model import ModelForge
from forge.gen.crud import CRUD
# from forge.gen.view import register_view_routes

class RouteType(str, Enum):
    """Available route types."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

class APIForge(BaseModel):
    """
    Manages API route generation and CRUD operations.
    Works in conjunction with ModelForge for model handling.
    """
    model_forge: ModelForge  # * ModelForge instance for model management
    routers: Dict[str, APIRouter] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        super().__init__(**data)
        # * Initialize the routers for each schema
        for schema in sorted(self.model_forge.include_schemas):
            self.routers[schema] = APIRouter(prefix=f"/{schema}", tags=[schema.upper()])
            self.routers[f"{schema}_views"] = APIRouter(prefix=f"/{schema}", tags=[f"{schema.upper()} Views"])

    def gen_table_routes(self) -> None:
        """Generate CRUD routes for all tables in the model cache."""
        print(f"\n{bold('[Generating Routes]')}")
        for table in self.model_forge.model_cache.keys():
            self.gen_table_crud(*table.split("."))

    def gen_table_crud(self, schema: str,  table_name: str) -> None:
        """Generate the curd routes for a certain Table..."""
        full_table_name = f"{schema}.{table_name}"
        if full_table_name not in self.model_forge.model_cache:
            raise KeyError(f"No models found for {full_table_name}")

        pydantic_model, sqlalchemy_model = self.model_forge.model_cache[full_table_name]
        CRUD(
            table=self.model_forge.db_manager.metadata.tables[full_table_name],
            pydantic_model=pydantic_model,
            sqlalchemy_model=sqlalchemy_model,
            router=self.routers[schema],
            db_dependency=self.model_forge.db_manager.get_db,
            tags=[schema.upper()]
        ).generate_all()

        print(f"\t{gray('gen crud for:')} {schema}.{bold(cyan(table_name))}")

    def gen_view_routes(self) -> None:
        """Generate routes for all views in the view cache."""
        print(f"\n{bold('[Generating View Routes]')}")
        for view_name, view_table in self.model_forge.view_cache.items():
            self.gen_view_route(view_name, view_table)

    def gen_view_route(self, view_name: str, view_table: Table) -> None:
        """Generate the GET route for a View with proper array type handling."""
        schema = view_table.schema
        print(f"\t{gray('gen view for:')} {schema}.{bold(cyan(view_name))}")
        try:
            generate_view_routes(
                view_table=view_table,
                schema=schema,
                # TODO: Decide on a better way to handle this... (maybe a config?)
                # router=self.routers[schema],
                router=self.routers[f"{schema}_views"],  # * Use the views router
                db_dependency=self.model_forge.db_manager.get_db,
                get_eq_type=get_eq_type
            )
        except Exception as e:
            print(f"\t{red(f'Error generating view route for {view_name}: {str(e)}')}")
