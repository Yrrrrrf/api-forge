# API Forge

[![PyPI version](https://badge.fury.io/py/api-forge.svg)](https://badge.fury.io/py/api-forge)
[![Documentation Status](https://readthedocs.org/projects/api-forge/badge/?version=latest)](https://api-forge.readthedocs.io/en/latest/?badge=latest)

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
from forge import *  # import mod prelude (main structures)

# Initialize the main Forge application
app_forge = Forge(
    info=ForgeInfo(
        PROJECT_NAME="MyAPI",
        VERSION="1.0.0"
    )
)
app = app_forge.app

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

# Initialize model management
model_forge = ModelForge(
    db_manager=db_manager,
    include_schemas=['public', 'app']
)

# Set up API routes
api_forge = APIForge(model_forge=model_forge)

# Generate all routes
# This will add the routes to it's respective router
api_forge.gen_table_routes()  # CRUD routes for tables
api_forge.gen_view_routes()   # Read routes for views
api_forge.gen_fn_routes()     # Routes for database functions

# Add the routes to the FastAPI app
[app.include_router(r) for r in api_forge.get_routers()]
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

## License

API Forge is released under the MIT License. See the [LICENSE](LICENSE) file for details.
