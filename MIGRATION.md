# Migrating from api-forge to prism-py

This guide helps you migrate your existing [api-forge](https://github.com/Yrrrrrf/api-forge) code to [prism-py](https://github.com/Yrrrrrf/prism-py), which is the successor library with improved architecture and features.

## Class Name Changes

| api-forge | prism-py | Purpose |
|-----------|----------|---------|
| `Forge` | `ApiPrism` | Main API generator class |
| `ForgeInfo` | `PrismConfig` | API configuration |
| `DBForge` | `DbClient` | Database connection manager |
| `DBConfig` | `DbConfig` | Database configuration |
| `PoolConfig` | `PoolConfig` | Connection pool settings (unchanged) |
| `ModelForge` | `ModelManager` | Model generation manager |

## Import Changes

```python
# api-forge
from forge import Forge, ForgeInfo, DBForge, DBConfig, PoolConfig, ModelForge

# prism-py
from prism import ApiPrism, PrismConfig, DbClient, DbConfig, PoolConfig, ModelManager
```

## Code Migration Examples

### Basic Setup

```python
# api-forge
from forge import Forge, ForgeInfo, DBForge, DBConfig, ModelForge

db_manager = DBForge(
    config=DBConfig(
        db_type="postgresql",
        driver_type="sync",
        database="mydb",
        user="username",
        password="password",
        host="localhost",
        port=5432,
    )
)

model_forge = ModelForge(
    db_manager=db_manager,
    include_schemas=["public", "app"]
)

app_forge = Forge(
    app=app,
    info=ForgeInfo(
        PROJECT_NAME="My API",
        VERSION="1.0.0",
        DESCRIPTION="My API description"
    )
)
```

```python
# prism-py
from prism import ApiPrism, PrismConfig, DbClient, DbConfig, ModelManager

db_client = DbClient(
    config=DbConfig(
        db_type="postgresql",
        driver_type="sync",
        database="mydb",
        user="username",
        password="password",
        host="localhost",
        port=5432,
    )
)

model_manager = ModelManager(
    db_client=db_client,
    include_schemas=["public", "app"]
)

api_prism = ApiPrism(
    app=app,
    config=PrismConfig(
        project_name="My API",
        version="1.0.0",
        description="My API description"
    )
)
```

### Route Generation

```python
# api-forge
app_forge.gen_metadata_routes(model_forge)
app_forge.gen_health_routes(model_forge)
app_forge.gen_table_routes(model_forge)
app_forge.gen_view_routes(model_forge)
app_forge.gen_fn_routes(model_forge)
```

```python
# prism-py
api_prism.gen_metadata_routes(model_manager)
api_prism.gen_health_routes(model_manager)
api_prism.gen_table_routes(model_manager)
api_prism.gen_view_routes(model_manager)
api_prism.gen_fn_routes(model_manager)

# Or use the convenient method that does all of the above:
api_prism.generate_all_routes(model_manager)
```


## Additional Support

For more details about prism-py's features and API, please refer to the [prism-py documentation](https://github.com/Yrrrrrf/prism-py).