from forge import *
import uvicorn

from forge.tools.api import APIForge
from forge.tools.db import *
import os

from forge.tools.model import ModelForge


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


api_forge = APIForge(model_forge=model_forge)

# ? Generate Routes -----------------------------------------------------------------------------
api_forge.gen_table_routes()
api_forge.gen_view_routes()
api_forge.gen_fn_routes()


# * Same as just calling it as a module
if __name__ == "__main__":
    uvicorn.run(
        "base-main:app", 
        host=app_forge.uvicorn_config.host,
        port=app_forge.uvicorn_config.port,
        reload=app_forge.uvicorn_config.reload,
    )
