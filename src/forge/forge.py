from typing import Optional, List, Dict

from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import MetaData

from forge.core.config import UvicornConfig
from forge.core.logging import bold, underline, italic, green


class ForgeInfo(BaseModel):
    PROJECT_NAME: str = Field(..., description="The name of your project")
    VERSION: str = Field(default="0.1.0", description="The version of your project")
    DESCRIPTION: Optional[str] = Field(default=None, description="A brief description of your project")
    AUTHOR: Optional[str] = Field(default=None)
    EMAIL: Optional[str] = Field(default=None)  # contact mail
    LICENSE: Optional[str] = Field(default='MIT', description="The license for the project")
    LICENSE_URL: Optional[str] = Field(default='https://choosealicense.com/licenses/mit/')

                
class Forge(BaseModel):
    info: ForgeInfo = Field(..., description="The information about the project")
    app: Optional[FastAPI] = Field(default=None, description="FastAPI application instance")
    uvicorn_config: UvicornConfig = Field(
        default_factory=UvicornConfig,
        description="Uvicorn server configuration"
    )
    
    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        self._initialize_app()
        self._print_welcome_message()

    def _initialize_app(self) -> None:
        """Initialize FastAPI app if not provided."""
        if self.app is None:
            # * Set up FastAPI app with project info
            self.app = FastAPI(
                title=self.info.PROJECT_NAME,
                version=self.info.VERSION,
                description=self.info.DESCRIPTION,
                contact={
                    "name": self.info.AUTHOR,
                    "email": self.info.EMAIL
                },
                license_info={
                    "name": self.info.LICENSE,
                    "url": self.info.LICENSE_URL
                } if self.info.LICENSE else None
            )

            # * Add CORS middleware by default
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

    def _print_welcome_message(self) -> None:
        """Print welcome message with app information."""
        print(f"\n\n{bold(self.info.PROJECT_NAME)} on {underline(italic(bold(green(f'http://{self.uvicorn_config.host}:{self.uvicorn_config.port}/docs'))))}\n\n")



# * Add some metadata routes...

class ColumnMetadata(BaseModel):
    name: str  # Column name
    type: str
    is_primary_key: bool
    is_foreign_key: bool = False

class TableMetadata(BaseModel):
    name: str  # Table name
    columns: List[ColumnMetadata] = []

class SchemaMetadata(BaseModel):
    name: str  # Schema name
    tables: Dict[str, TableMetadata] = {}


def get_metadata_router(metadata: MetaData, prefix: str = "/dt") -> APIRouter:
    dt_router: APIRouter = APIRouter(prefix=prefix, tags=["METADATA"])

    @dt_router.get("/schemas", response_model=List[SchemaMetadata])
    def get_schemas():
        schemas = {}
        for table in metadata.tables.values():
            if table.schema not in schemas:
                schemas[table.schema] = SchemaMetadata(name=table.schema)

            table_metadata = TableMetadata(name=table.name)
            for column in table.columns:
                column_metadata = ColumnMetadata(
                    name=column.name,
                    type=str(column.type),
                    is_primary_key=column.primary_key,
                    is_foreign_key=bool(column.foreign_keys)
                )
                table_metadata.columns.append(column_metadata)
            
            schemas[table.schema].tables[table.name] = table_metadata
        
        return list(schemas.values())

    @dt_router.get("/{schema}/tables", response_model=List[TableMetadata])
    def get_tables(schema: str):
        tables = []
        for table in metadata.tables.values():
            if table.schema == schema:
                table_metadata = TableMetadata(name=table.name)
                for column in table.columns:
                    column_metadata = ColumnMetadata(
                        name=column.name,
                        type=str(column.type),
                        is_primary_key=column.primary_key,
                        is_foreign_key=bool(column.foreign_keys)
                    )
                    table_metadata.columns.append(column_metadata)
                tables.append(table_metadata)
        
        if not tables:
            raise HTTPException(status_code=404, detail=f"Schema '{schema}' not found")
        return tables

    @dt_router.get("/{schema}/{table}/columns", response_model=List[ColumnMetadata])
    def get_columns(schema: str, table: str):
        full_table_name = f"{schema}.{table}"
        if full_table_name not in metadata.tables:
            raise HTTPException(status_code=404, detail=f"Table '{full_table_name}' not found")
        
        table_obj = metadata.tables[full_table_name]
        columns = []
        for column in table_obj.columns:
            column_metadata = ColumnMetadata(
                name=column.name,
                type=str(column.type),
                is_primary_key=column.primary_key,
                is_foreign_key=bool(column.foreign_keys)
            )
            columns.append(column_metadata)
        return columns

    return dt_router
