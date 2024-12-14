# CRUD FORGE

[![PyPI version](https://badge.fury.io/py/crud-forge.svg)](https://badge.fury.io/py/crud-forge)
[![Documentation Status](https://readthedocs.org/projects/crud-forge/badge/?version=latest)](https://crud-forge.readthedocs.io/en/latest/?badge=latest)

## Overview

Python library designed onntop of [fast-api](https://fastapi.tiangolo.com/) to **handle any db model & route** responsabilities.

It provides a robust type system for managing API responses, reducing boilerplate code, and ensuring type safety throughout your application.
It automatically generates API routes, database models, and even provides metadata endpoints, significantly reducing development time and boilerplate code.

## Key Features

- **Automatic Model Generation**: Instantly create SQLAlchemy and Pydantic models from your existing database schema.
- **Dynamic CRUD Route Generation**: Automatically generate FastAPI routes for all your models.
- **Metadata API**: Built-in routes to explore your database structure programmatically.
- **Flexible Database Connection Management**: Easy setup for various database types including PostgreSQL, MySQL, and SQLite.
- **Customizable Route Generation**: Tailor the generated routes to your specific needs.
- **Advanced Filtering**: Built-in filtering capabilities for GET requests.
- **Comprehensive Error Handling**: Robust error management out of the box.
- **Type Hinting**: Full type hint support for better IDE integration and code quality.

## Installation

Install CRUD FORGE using pip:

```bash
pip install api-forge==0.0.1
```

## Quick Start

Here's how you can leverage CRUD FORGE's automatic generators:

```python
from fastapi import FastAPI
from forge.db import DBForge
from forge.models import generate_models_from_metadata
from forge.crud import generate_crud
from forge.routes import generate_metadata_routes, generate_default_routes

# Set up FastAPI app and database
app = FastAPI()
db_manager = DBForge(db_url="postgresql://user:password@localhost/dbname")

metadata = db_manager.metadata  # get the metadata from the database

# recieve the fastapi app to generate default routes
generate_default_routes(app)

# Generate metadata routes
app.include_router(generate_metadata_routes(metadata, db_manager.get_db))

# Automatically generate models from database metadata
models = generate_models_from_metadata(metadata)

# Generate CRUD routes for all models
for schema, models in models.items():
    for table_name, (sqlalchemy_model, pydantic_model) in models.items():
        generate_crud(sqlalchemy_model, pydantic_model, app, db_manager.get_db)

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

This example automatically generates models and CRUD routes for your entire database schema!

## Package Structure

![CRUD FORGE MAIN STRUCTURE](docs/images/pkg.svg)

## Detailed Usage

### Database Connection

Use the `DBForge` to set up your database connection:

```python
from forge.db import DBForge

# Using a database URL
db_manager = DBForge(db_url="postgresql://user:password@localhost/dbname")

# Or using individual parameters
db_manager = DBForge(
    db_type="postgresql",
    user="user",
    password="password",
    host="localhost",
    database="dbname"
)
```

### Automatic Model Generation

Use `generate_models_from_metadata` to automatically create models:

```python
from forge.models import generate_models_from_metadata

models = generate_models_from_metadata(db_manager.metadata)
```

### Dynamic CRUD Route Generation

Generate CRUD routes for all your models dynamically:

```python
from forge.crud import generate_crud

for schema, models in models.items():
    for table_name, (sqlalchemy_model, pydantic_model) in models.items():
        generate_crud(sqlalchemy_model, pydantic_model, app, db_manager.get_db, tags=[f"{schema}_{table_name}"])
```

### Metadata API

CRUD FORGE includes built-in routes to explore your database structure:

```python
from forge.routes import generate_metadata_routes

metadata_router = generate_metadata_routes(db_manager.metadata, db_manager.get_db)
app.include_router(metadata_router)
```

This will create the following endpoints:

- `GET /dt/schemas`: List all schemas in the database
- `GET /dt/{schema}/tables`: List all tables in a specific schema
- `GET /dt/{schema}/{table}/columns`: Get details of columns in a specific table

### Default Routes

CRUD FORGE can generate some default routes for your application:

```python
from forge.routes import generate_default_routes

generate_default_routes(app)
```

This will create the following endpoints:

- `GET /`: Root endpoint with basic API information
- `GET /health`: Health check endpoint
- `GET /version`: Version information endpoint

## Documentation

For more detailed information about the API and advanced usage, please refer to our [documentation](https://crud-forge.readthedocs.io).

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for more details.

## License

CRUD FORGE is released under the MIT License. See the [LICENSE](LICENSE) file for more details.