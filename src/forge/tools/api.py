from typing import Dict, List
from fastapi import APIRouter
from pydantic import BaseModel, Field, ConfigDict
from forge.gen.view import gen_view_route
from forge.gen.table import gen_table_crud
from forge.gen.fn import gen_fn_route
from forge.core.logging import bold, gray, cyan
from forge.tools.model import ModelForge

class APIForge(BaseModel):
    """
    Manages API route generation and CRUD operations.
    Works in conjunction with ModelForge for model management.
    """
    model_forge: ModelForge = Field(..., title="Model Forge")
    routers: Dict[str, APIRouter] = Field(default_factory=dict)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._init_routers()

    def _init_routers(self) -> None:
        """Initialize routers for each schema and route type."""
        for schema in sorted(self.model_forge.include_schemas):
            # Main schema router
            self.routers[schema] = APIRouter(prefix=f"/{schema}", tags=[schema.upper()])
            self.routers[f"{schema}_views"] = APIRouter(prefix=f"/{schema}", tags=[f"{schema.upper()} Views"])
            self.routers[f"{schema}_fn"] = APIRouter(prefix=f"/{schema}", tags=[f"{schema.upper()} Functions"])

    def gen_table_routes(self) -> None:
        """Generate CRUD routes for all tables."""
        print(f"\n{bold('[Generating Table Routes]')}")
        
        for table_key, table_data in self.model_forge.model_cache.items():
            schema, table_name = table_key.split('.')
            print(f"\t{gray('gen crud for:')} {schema}.{bold(cyan(table_name))}")
            gen_table_crud(
                table_data=table_data,
                router=self.routers[schema],
                db_dependency=self.model_forge.db_manager.get_db,
            )
    
    def gen_view_routes(self) -> None:
        """Generate routes for all views."""
        print(f"\n{bold('[Generating View Routes]')}")
        
        for view_key, view_data in self.model_forge.view_cache.items():
            schema, view_name = view_key.split('.')
            print(f"\t{gray('gen view for:')} {schema}.{bold(cyan(view_name))}")
            gen_view_route(
                table_data=view_data,
                router=self.routers[f"{schema}_views"],
                db_dependency=self.model_forge.db_manager.get_db
            )
    
    def gen_fn_routes(self) -> None:
        """Generate routes for all functions."""
        print(f"\n{bold('[Generating Function Routes]')}")
        
        for fn_key, fn_metadata in self.model_forge.fn_cache.items():
            schema, fn_name = fn_key.split('.')
            print(f"\t{gray('gen fn for:')} {schema}.{bold(cyan(fn_name))}")
            gen_fn_route(
                fn_metadata=fn_metadata,
                router=self.routers[f"{schema}_fn"],
                db_dependency=self.model_forge.db_manager.get_db
            )
    
    def get_routers(self) -> List[APIRouter]:
        """Return list of all routers."""
        return list(self.routers.values())
