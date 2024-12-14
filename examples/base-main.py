from forge import *
import uvicorn

app_forge = Forge(
    info=ForgeInfo(PROJECT_NAME="MyAPI"),
)
app: FastAPI = app_forge.app

# & `uvicorn examples.base-main:app --reload --env-file .env`

# * Same as just calling it as a module
if __name__ == "__main__":
    uvicorn.run(
        "base-main:app", 
        host=app_forge.uvicorn_config.host,
        port=app_forge.uvicorn_config.port,
        reload=app_forge.uvicorn_config.reload,
    )
