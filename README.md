<h1 align="center">
  <div align="center">API Forge</div>
</h1>

<div align="center">

[![PyPI version](https://img.shields.io/pypi/v/api-forge)](https://pypi.org/project/api-forge/)
[![GitHub: API Forge](https://img.shields.io/badge/GitHub-API%20Forge-181717?logo=github)](https://github.com/Yrrrrrf/api-forge)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://choosealicense.com/licenses/mit/)
[![Downloads](https://pepy.tech/badge/api-forge)](https://pepy.tech/project/api-forge)

</div>

## Overview

API Forge is a Python library built on top of [FastAPI](https://fastapi.tiangolo.com/) that streamlines database model management and API route generation. It provides a comprehensive type system for managing API responses, reducing boilerplate code, and ensuring type safety throughout your application.

The library automatically generates API routes, database models, and metadata endpoints, significantly reducing development time while maintaining code quality and type safety.

## Key Features

- **Automatic Model Generation**: Creates SQLAlchemy and Pydantic models from your existing database schema
- **Dynamic Route Generation**: Automatically generates FastAPI routes for tables, views, and functions
- **Database Function Support**: Native support for PostgreSQL functions, procedures, and triggers
- **Metadata API**: Built-in routes to explore your database structure programmatically
- **Flexible Database Connection**: Support for PostgreSQL, MySQL, and SQLite with connection pooling
- **Advanced Type System**: Comprehensive type handling including JSONB and Array types
- **Schema-based Organization**: Route organization based on database schemas
- **Full Type Hinting**: Complete type hint support for better IDE integration

## Installation

Install API Forge using pip:

```bash
pip install api-forge
```

## Quick Start

Here's how to quickly set up an API with API Forge:

```python
from fastapi import FastAPI
from forge import *  # import mod prelude (main structures)


# ? DB Forge ----------------------------------------------------------------------------------
# Configure database connection
db_manager = DBForge(
    config=DBConfig(
        db_type="postgresql",
        driver_type="sync",
        database="mydb",
        user="user",
        password="password",
        host="localhost",
        port=5432,
        pool_config=PoolConfig(
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_pre_ping=True
        )
    )
)
db_manager.log_metadata_stats()  # Log db metadata statistics

# ? Model Forge -------------------------------------------------------------------------------
model_forge = ModelForge(
    db_manager=db_manager,
    # * Define the schemas to include in the model...
    include_schemas=['public', 'app', 'another_schema'],
)
model_forge.log_schema_tables()  # detailed log of the tables in the schema
model_forge.log_schema_views()  # detailed log of the views in the schema
model_forge.log_schema_fns()  # detailed log of the functions in the schema
model_forge.log_metadata_stats()  # Log model metadata statistics


# ? Main API Forge ----------------------------------------------------------------------------
app: FastAPI = FastAPI()  # * Create a FastAPI app (needed when calling the script directly)

app_forge = Forge(  # * Create a Forge instance
    app=app,
    info=ForgeInfo(
        PROJECT_NAME="MyAPI",
        VERSION="1.0.0"
    )
)

# * The main forge store the app and creates routes for the models (w/ the static type checking)
app_forge.gen_metadata_routes(model_forge)  # * add metadata routes (schemas, tables, views, fns)
app_forge.gen_health_routes(model_forge)  # * add health check routes
# * Route Generators... (table, view, function)
app_forge.gen_table_routes(model_forge)  # * add db.table routes (ORM CRUD)
app_forge.gen_view_routes(model_forge)  # * add db.view routes
app_forge.gen_fn_routes(model_forge)  # * add db.[fn, proc, trigger] routes
```
Then run the application using Uvicorn:
```bash
uvicorn myapi:app --reload
```
Or run the script directly:
```python
if __name__ == "__main__":
    import uvicorn  # import the Uvicorn server (ASGI)
    uvicorn.run(
        app=app,
        host=app_forge.uvicorn_config.host,
        port=app_forge.uvicorn_config.port,
        reload=app_forge.uvicorn_config.reload
    )
```

## Generated Routes

API Forge automatically generates the following types of routes:

### Table Routes

- `POST /{schema}/{table}` - Create
- `GET /{schema}/{table}` - Read (with filtering)
- `PUT /{schema}/{table}` - Update
- `DELETE /{schema}/{table}` - Delete

### View Routes

- `GET /{schema}/{view}` - Read with optional filtering

### Function Routes

- `POST /{schema}/fn/{function}` - Execute function
- `POST /{schema}/proc/{procedure}` - Execute procedure

### Metadata Routes

- `GET /dt/schemas` - List all database schemas and their structures
- `GET /dt/{schema}/{{tables, views, fns}}` - List all tables, views, or functions in a schema

### Health Check Routes

- `GET /health` - Get API health status and version information
- `GET /health/ping` - Basic connectivity check
- `GET /health/cache` - Check metadata cache status
- `POST /health/clear-cache` - Clear and reload metadata cache

## License

API Forge is released under the MIT License. See the [LICENSE](LICENSE) file for details.
