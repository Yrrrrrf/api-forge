from typing import Optional
from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List
from fastapi import APIRouter

from forge.core.logging import bold, gray, cyan, underline, italic, green
from forge.gen.metadata import *
from forge.tools.model import ModelForge
from forge.gen.view import gen_view_route
from forge.gen.table import gen_table_crud
from forge.gen.fn import gen_fn_route


class ForgeInfo(BaseModel):
    PROJECT_NAME: str = Field(..., description="The name of your project")
    VERSION: str = Field(default="0.1.0", description="The version of your project")
    DESCRIPTION: Optional[str] = Field(default=None, description="A brief description of your project")
    AUTHOR: Optional[str] = Field(default=None)  # author name
    EMAIL: Optional[str] = Field(default=None)  # contact mail
    LICENSE: Optional[str] = Field(default='MIT', description="The license for the project")
    LICENSE_URL: Optional[str] = Field(default='https://choosealicense.com/licenses/mit/')

    def to_dict(self) -> dict: return self.model_dump()

    # *  Sames as 'Rust's PartialEq trait' -> derive[(PartialEq)]
    # def __eq__(self, other):
    #     match isinstance(other, ForgeInfo):
    #         case True: return self.to_dict() == other.to_dict()
    #         case False: return False

class UvicornConfig(BaseModel):
    """Configuration for Uvicorn server."""
    host: str = Field(default="127.0.0.1", description="The host to run the server on")    
    port: int = Field(default=8000, description="Port to bind to")
    reload: bool = Field(default=True, description="Enable auto-reload")
    workers: int = Field(default=1, description="Number of worker processes")
    log_level: str = Field(default="info", description="Logging level")

class Forge(BaseModel):
    info: ForgeInfo = Field(..., description="The information about the project")
    app: Optional[FastAPI] = Field(default=None, description="FastAPI application instance")
    routers: Dict[str, APIRouter] = Field(default_factory=dict)
    
    uvicorn_config: UvicornConfig = Field(
        default_factory=UvicornConfig,
        description="Uvicorn server configuration"
    )

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        self._initialize_app()
        self._print_welcome_message()

    def _initialize_app(self) -> None:
        """Initialize FastAPI app if not provided."""
        # todo: Check how to handle this properly... (if app is not provided)
        # app = self.app or FastAPI()  # * this seams to be a better way...

        self.app.title = self.info.PROJECT_NAME
        self.app.version = self.info.VERSION
        self.app.description = self.info.DESCRIPTION
        self.app.contact = {
            "name": self.info.AUTHOR,
            "email": self.info.EMAIL
        }
        self.app.license_info = {
            "name": self.info.LICENSE,
            "url": self.info.LICENSE_URL
        } if self.info.LICENSE else None

        # * Add CORS middleware by default
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _print_welcome_message(self) -> None:
        """Print welcome message with app information."""
        # todo: Somehow, make this message appear at the last...
        # todo: ...after all the FastAPI app routes have been added
        # ^ For now it appears at the beginning (the Forge instance creation)
        print(f"\n\n{bold(self.info.PROJECT_NAME)} on {underline(italic(bold(green(f'http://{self.uvicorn_config.host}:{self.uvicorn_config.port}/docs'))))}\n\n")

    # * Route Generators... (table, view, function)
    def gen_table_routes(self, model_forge: ModelForge) -> None:
        """Generate CRUD routes for all tables."""
        for schema in model_forge.include_schemas:
            self.routers[schema] = APIRouter(prefix=f"/{schema}", tags=[schema.upper()])

        print(f"\n{bold('[Generating Table Routes]')}")

        for table_key, table_data in model_forge.table_cache.items():
            schema, table_name = table_key.split('.')
            print(f"\t{gray('gen crud for:')} {schema}.{bold(cyan(table_name))}")
            gen_table_crud(
                table_data=table_data,
                router=self.routers[schema],
                db_dependency=model_forge.db_manager.get_db,
            )
    
    def gen_view_routes(self, model_forge: ModelForge) -> None:
        """Generate routes for all views."""

        for schema in model_forge.include_schemas:
            self.routers[f"{schema}_views"] = APIRouter(prefix=f"/{schema}", tags=[f"{schema.upper()} Views"])

        print(f"\n{bold('[Generating View Routes]')}")
        
        for view_key, view_data in model_forge.view_cache.items():
            schema, view_name = view_key.split('.')
            print(f"\t{gray('gen view for:')} {schema}.{bold(cyan(view_name))}")
            gen_view_route(
                table_data=view_data,
                router=self.routers[f"{schema}_views"],
                db_dependency=model_forge.db_manager.get_db
            )
    
    def gen_fn_routes(self, model_forge: ModelForge) -> None:
        """Generate routes for all functions."""

        for schema in model_forge.include_schemas:
            self.routers[f"{schema}_fn"] = APIRouter(prefix=f"/{schema}", tags=[f"{schema.upper()} Functions"])

        print(f"\n{bold('[Generating Function Routes]')}")
        
        for fn_key, fn_metadata in model_forge.fn_cache.items():
            schema, fn_name = fn_key.split('.')
            print(f"\t{gray('gen fn for:')} {schema}.{bold(cyan(fn_name))}")
            gen_fn_route(
                fn_metadata=fn_metadata,
                router=self.routers[f"{schema}_fn"],
                db_dependency=model_forge.db_manager.get_db
            )

    def get_routers(self) -> List[APIRouter]:
        """Return list of all routers."""
        return list(self.routers.values())

    # * Metadata Routes
    def gen_metadata_routes(self, model_forge: ModelForge) -> None:
        """Include metadata routes for the app."""
        self.routers["metadata"] = APIRouter(prefix="/dt", tags=["Metadata"])

        print(f"\n{bold('[Generating Metadata Routes]')}")

        for fn in [get_schemas,  get_tables, get_views, get_enums]:
            print(f"\t{gray('gen metadata:')} {bold(cyan(fn.__name__))}")
            fn(self.routers["metadata"], model_forge)

        # * Add the router to the app
        self.app.include_router(self.routers["metadata"])
