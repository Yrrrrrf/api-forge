# std imports
import os
# 3rd party imports
from fastapi import FastAPI
# * Local imports
from forge import *  # * import forge prelude (main module exports)


app: FastAPI = FastAPI()  # * Create a FastAPI app instance

# ? Main Forge -----------------------------------------------------------------------------------
app_forge = Forge(  # * Create a Forge instance
    info=ForgeInfo(PROJECT_NAME="MyAPI"),
    app=app,
)

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
# todo: Improve the log_schema_*() fn's to be more informative & also add some 'verbose' flag
model_forge.log_schema_tables()
model_forge.log_schema_views()
model_forge.log_schema_fns()
model_forge.log_metadata_stats()

# ? API Forge -----------------------------------------------------------------------------------
api_forge = APIForge(model_forge=model_forge)

api_forge.gen_table_routes()
api_forge.gen_view_routes()
api_forge.gen_fn_routes()

# Add the routes to the FastAPI app
# [app.include_router(r) for r in api_forge.get_routers()]

# * Same as just calling it as a module
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "base-main:app", 
        host=app_forge.uvicorn_config.host,
        port=app_forge.uvicorn_config.port,
        reload=app_forge.uvicorn_config.reload,
    )
