from forge import *
import uvicorn

from forge.gen.table import gen_table_crud
from forge.gen.view import gen_view_route
from forge.tools.db import *
import os

from forge.tools.model import ModelForge
from forge.gen.fn import gen_fn_route


# ? Main Forge -----------------------------------------------------------------------------------
app_forge = Forge(
    info=ForgeInfo(PROJECT_NAME="MyAPI"),
)
app: FastAPI = app_forge.app

# & `uvicorn examples.base-main:app --reload --env-file .env`
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
# # todo: FnForge::log_schema_functions()

# # * Add some logging to the model_forge...
# [print(f"{bold('Models:')} {table}") for table in model_forge.model_cache]
# [print(f"{bold('Views:')} {view}") for view in model_forge.view_cache]
# [print(f"{bold('PyEnum:')} {enum}") for enum in model_forge.enum_cache]
# # todo: Print the 'Functions' as well
# # [print(f"{bold('Functions:')} {enum}") for enum in model_forge.fn_cache]

# ? Generate the Pydantic models

r_tables = APIRouter()
for _, table_tuple in model_forge.model_cache.items():
    gen_table_crud(table_tuple, r_tables, db_manager.get_db)

r_view = APIRouter(prefix="/view")
for view_tuple in model_forge.view_cache.values():
    gen_view_route(view_tuple, r_view, db_manager.get_db)

r_fn = APIRouter(prefix="/fn")
for _, fn_metadata in model_forge.fn_cache.items(): 
    gen_fn_route(fn_metadata, r_fn, db_manager.get_db)

# add the router to the app
app.include_router(r_tables)
# app.include_router(r_fn)
# app.include_router(r_view)




# * Same as just calling it as a module
if __name__ == "__main__":
    uvicorn.run(
        "base-main:app", 
        host=app_forge.uvicorn_config.host,
        port=app_forge.uvicorn_config.port,
        reload=app_forge.uvicorn_config.reload,
    )
