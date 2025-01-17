"""Main file for showcasing the database structure using DBForge"""
# std imports
import os
# 3rd party imports
from fastapi import FastAPI
# Local imports
from forge import *  # * import forge prelude (main module exports)


# ? DB Forge -------------------------------------------------------------------------------------
db_manager = DBForge(config=DBConfig(
    db_type=os.getenv('DB_TYPE', 'postgresql'),
    driver_type=os.getenv('DRIVER_TYPE', 'sync'),
    database=os.getenv('DB_NAME', 'a_hub'),
    user=os.environ.get('DB_OWNER_ADMIN') or 'a_hub_admin',
    password=os.environ.get('DB_OWNER_PWORD') or 'password',
    host=os.environ.get('DB_HOST') or 'localhost',
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
        # * Default schemas
        'public',
        'account',
        'auth',
        # * A-Hub schemas
        'agnostic',
        'infrastruct',
        'hr',
        'academic',
        'course_offer',
        'student',
        'library',
    ],
)
# model_forge.log_schema_tables()
model_forge.log_schema_views()
# model_forge.log_schema_fns()
model_forge.log_metadata_stats()

# print(type(model_forge))
# print(type(model_forge.table_cache))
# print(model_forge.table_cache)

# ? Main API Forge -----------------------------------------------------------------------------------
app: FastAPI = FastAPI()  # * Create a FastAPI app (needed when calling the script directly)

app_forge = Forge(  # * Create a Forge instance
    app=app,
    info=ForgeInfo(
        PROJECT_NAME="Academic Hub API",
        VERSION="0.3.1",
        DESCRIPTION="A simple API to manage an academic institution's data",
        AUTHOR="yrrrrrf",
    ),
)
# * The main forge store the app and creates routes for the models (w/ the static type checking)
app_forge.gen_table_routes(model_forge)
app_forge.gen_view_routes(model_forge)
# api_forge.gen_fn_routes(model_forge)
app_forge.gen_metadata_routes(model_forge)


# # ^ Add the health route...
# # ^ This is just a temporary route to check if the API is running...
# # ^ Later on this route must be also available in the API Forge...
# # todo: Add 'status' routes to the API Forge...
# # todo: - '/status'
# # todo: - '/status/db'
# # todo: - '/status/api'
# # todo: - '/status/app'
# def add_app_routes():
#     from fastapi import APIRouter

#     app_router = APIRouter()
    
#     @app_router.get("/health")
#     async def health(): return {"status": "healthy"}

#     app.include_router(app_router)

# add_app_routes()


if __name__ == "__main__":
    import uvicorn  # import uvicorn for running the FastAPI app
    # * Run the FastAPI app using Uvicorn (if the script is called directly)
    uvicorn.run(
        "main:app", 
        host=app_forge.uvicorn_config.host,
        port=app_forge.uvicorn_config.port,
        reload=app_forge.uvicorn_config.reload,
    )
