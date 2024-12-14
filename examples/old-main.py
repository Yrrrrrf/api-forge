"""Main file for showcasing the database structure using DBForge"""
from fastapi import APIRouter, FastAPI
import os

# Import our enhanced DBForge and related classes
from forge.gen.fn import FnForge
from forge.utils import *
from forge.db import DBForge, DBConfig, PoolConfig
from forge.api import APIForge
from forge.model import ModelForge
from forge.gen.metadata import get_metadata_router


# ? Create the FastAPI app ----------------------------------------------------------------------
app = FastAPI()
allow_all_middleware(app)
#  * add the logging setup configuration...(forge.utils.setup_logging)

# Initialize configuration
app_config = AppConfig(
    PROJECT_NAME="Pharma Care",
    VERSION="0.3.1",
    DESCRIPTION="A simple API for managing a pharmacy",
    AUTHOR="Fernando Byran Reza Campos",
)
app_config.set_app_data(app)

# ? DB Forge ------------------------------------------------------------------------------------
db_manager = DBForge(config=DBConfig(
    db_type=os.getenv('DB_TYPE', 'postgresql'),
    driver_type=os.getenv('DRIVER_TYPE', 'sync'),
    database=os.getenv('DB_NAME', 'pharmacy_management'),
    user=os.getenv('DB_USER', 'pharmacy_management_owner'),
    password=os.getenv('DB_PASSWORD', 'secure_pharmacy_pwd'),
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', 5432),
    echo=False,
    pool_config=PoolConfig(
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True
    ),
))
db_manager.log_metadata_stats()
app.include_router(get_metadata_router(db_manager.metadata))  # * add the metadata router

# ? Model Forge ---------------------------------------------------------------------------------
model_forge = ModelForge(
    db_manager=db_manager,
    include_schemas=[
        'public', 
        'pharma', 
        'management',
        'analytics'
    ],
)
# model_forge.log_metadata_stats()
# todo: Improve the log_schema_*() fn's to be more informative & also add some 'verbose' flag
# model_forge.log_schema_tables()
# model_forge.log_schema_views()
# todo: FnForge::log_schema_functions()

# * Add some logging to the model_forge...
# [print(f"{bold('Models:')} {table}") for table in model_forge.model_cache]
# [print(f"{bold('Views:')} {view}") for view in model_forge.view_cache]
# [print(f"{bold('PyEnum:')} {enum}") for enum in model_forge.enum_cache]
# todo: Print the 'Functions' as well
# [print(f"{bold('Functions:')} {enum}") for enum in model_forge.fn_cache]


# ? Function Forge -----------------------------------------------------------------------------
function_forge = FnForge(
    db_dependency=db_manager.get_db,
    include_schemas=model_forge.include_schemas  # Reuse same schemas
)
# Discover and set up functions
function_forge.discover_functions()
function_forge.generate_function_models()

# todo: Add this to the FnForge class
# todo: FnForge::log_schema_functions()
function_forge.log_metadata_stats()

print(f"\n{bold('Functions:')} {len(function_forge.function_cache)}")
for schema in model_forge.include_schemas:
    print(f"\n{bold('\t')} {schema}")
    for key, value in function_forge.function_cache.items():
        if key.startswith(schema):
            # Add object_type to the output
            print(f"\t\t{dim(f'{value.object_type.value:>10}')} {dim(f'{value.type.name:>16}')} {key.split('.')[1]}")
            for param in value.parameters:
                print(f"\t\t\t\t\t{param.name} {param.type}")
            print()

fn_router = APIRouter()

function_forge.generate_function_routes(fn_router)
app.include_router(fn_router)




# ? API Forge -----------------------------------------------------------------------------------
api_forge = APIForge(model_forge=model_forge)
# # * THE ROUTES MUST BE GENERATED AFTER THE MODELS!
# api_forge.gen_table_routes()
# api_forge.gen_view_routes()
# * Print the routers
[app.include_router(router) for router in api_forge.routers.values()]

print(f"\n\n{bold(app_config.PROJECT_NAME)} on {underline(italic(bold(green("http://localhost:8000/docs"))))}\n\n")
