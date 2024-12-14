from sqlalchemy import CursorResult, Inspector, MetaData, Table, inspect, text, Index
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase
from sqlalchemy.ext.automap import automap_base
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Generator, List, Optional, Any, Type, Union, Set, Tuple
from enum import Enum
from contextlib import contextmanager
from forge.utils import *


class DBType(str, Enum):
    """Supported database types."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MSSQL = "mssql"  # Added support for Microsoft SQL Server

class DriverType(str, Enum):
    """Available driver types for database connections."""
    SYNC = "sync"
    ASYNC = "async"

class PoolConfig(BaseModel):
    """Database connection pool configuration."""
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    pool_pre_ping: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 1800,
                "pool_pre_ping": True
            }
        }
    )

class DBConfig(BaseModel):
    """Enhanced database configuration with connection pooling."""
    db_type: Union[DBType, str]
    driver_type: Union[DriverType, str]
    user: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    database: str
    port: Optional[int] = None
    echo: bool = False
    pool_config: Optional[PoolConfig] = Field(default_factory=PoolConfig)
    schema_exclude: List[str] = Field(default=["information_schema", "pg_catalog"])
    ssl_mode: Optional[str] = None  # * idk if this is the right place for this

    model_config = ConfigDict(use_enum_values=True)

    def __init__(self, **data):
        super().__init__(**data)
        self.db_type = DBType(self.db_type) if isinstance(self.db_type, str) else self.db_type
        self.driver_type = DriverType(self.driver_type) if isinstance(self.driver_type, str) else self.driver_type

    @property
    def url(self) -> str:
        """Generate database URL based on configuration."""
        if self.db_type == DBType.SQLITE:
            return f"sqlite:///{self.database}"
        
        if self.db_type in (DBType.POSTGRESQL, DBType.MYSQL, DBType.MSSQL):
            if not all([self.user, self.password, self.host]):
                raise ValueError(f"Incomplete configuration for {self.db_type}")
            
            dialect = self.db_type.value
            driver = self._get_driver()
            
            port_str = f":{self.port}" if self.port is not None else ""
            ssl_str = f"?sslmode={self.ssl_mode}" if self.ssl_mode else ""
            
            return f"{dialect}{driver}://{self.user}:{self.password}@{self.host}{port_str}/{self.database}{ssl_str}"
        
        raise ValueError(f"Unsupported database type: {self.db_type}")

    def _get_driver(self) -> str:
        """Get appropriate database driver based on configuration."""
        if self.db_type == DBType.POSTGRESQL:
            return "+asyncpg" if self.driver_type == DriverType.ASYNC else "+psycopg2"
        elif self.db_type == DBType.MYSQL:
            return "+aiomysql" if self.driver_type == DriverType.ASYNC else "+pymysql"
        elif self.db_type == DBType.MSSQL:
            return "+pytds" if self.driver_type == DriverType.ASYNC else "+pyodbc"
        return ""


class DBForge(BaseModel):
    """Enhanced database management with extended functionality."""
    config: DBConfig = Field(...)
    engine: Engine = Field(default=None)
    metadata: MetaData = Field(default_factory=MetaData)
    Base: Type[DeclarativeBase] = Field(default_factory=automap_base)
    SessionLocal: sessionmaker = Field(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, **data):
        super().__init__(**data)
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        # self._test_connection()  # * Uncomment to test connection on initialization
        self._load_metadata()

    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine with connection pooling."""
        pool_kwargs = self.config.pool_config.model_dump() if self.config.pool_config else {}
        return create_engine(
            self.config.url,
            echo=self.config.echo,  # ^ Uncomment for verbose logging
            **pool_kwargs
        )

    def _test_connection(self) -> None:
        """Test database connection and log connection info."""
        try:
            user, database = self.exec_raw_sql("SELECT current_user, current_database()").fetchone()
            print(f"\n{gray('Connected to')} {bold(database)} {gray('as')} {bold(user)}")
            print(f"{green('Database connection test successful!')}")
        except Exception as e:
            print(f"{red('Database connection test failed:')} {str(e)}")
            raise
        print()

    def _load_metadata(self) -> None:
        """Enhanced metadata loading with schema filtering and error handling."""
        inspector: Inspector = inspect(self.engine)
        
        # Create our base declarative base class first
        class Base(DeclarativeBase):
            pass
        
        self.Base = Base  # Store the actual base class, not the DeclarativeBase

        # Load tables and views into metadata
        # # todo: Change this to filter the schemas depending on...
        # # todo: User permissions or configuration settings...
        # # * To enable some kind of MULTI-TENANCY support
        for schema in sorted(set(inspector.get_schema_names()) - set(self.config.schema_exclude)):
            [Table(t, self.metadata, autoload_with=self.engine, schema=schema) for t in inspector.get_table_names(schema=schema)]
            [Table(v, self.metadata, autoload_with=self.engine, schema=schema) for v in inspector.get_view_names(schema=schema)]


        # self.Base.prepare(self.engine, reflect=True)

    # * PUBLIC METHODS (OPERATIONS)
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Context manager for database sessions."""
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally: session.close()

    def get_db(self) -> Generator[Session, None, None]:
        """Generator for database sessions (FastAPI dependency)."""
        # todo: Add typing to the generator
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def exec_raw_sql(self, query: str) -> CursorResult:
        """Execute raw SQL query."""
        with self.engine.connect() as connection: return connection.execute(text(query))

    def get_db_version(self) -> str:
        """Get database version information."""
        match self.config.db_type:
            case DBType.POSTGRESQL | DBType.MYSQL: query = "SELECT version()"
            case DBType.SQLITE: query = "SELECT sqlite_version()"
            case DBType.MSSQL: query = "SELECT @@VERSION"

        if query: return str(self.exec_raw_sql(query).scalar()).split('\n')[0]  # First line of version info
        return "Unknown"

    def log_metadata_stats(self) -> None:
        """Log metadata statistics."""
        user, database = self.exec_raw_sql("SELECT current_user, current_database()").fetchone()

        print(f"{gray('Connected to')} {bold(database)} {gray('as')} {bold(user)}")
        print(f"{gray('Database version:')} {bold(self.get_db_version())}")

        print(f"\n{bold('DB Connection Information:')}")
        print(f"\t{f"Type:":<12}{green(self.config.db_type.name)}")
        print(f"\t{f"Driver:":<12}{green(self.config.driver_type.name)}")
        print(f"\t{f"DB:":<12}{green(italic(bold(self.config.database)))}")

        if not self.metadata.tables:
            print(f"{yellow(bold("No tables or views found in the database after reflection."))}")
            return

    def analyze_table_relationships(self) -> Dict[str, List[Dict[str, str]]]:
        """Analyze and return table relationships."""
        relationships = {}
        for table_name, table in self.metadata.tables.items():
            relationships[table_name] = []
            for fk in table.foreign_keys:
                relationships[table_name].append({
                    "from_col": fk.parent.name,
                    "to_table": fk.column.table.name,
                    "to_col": fk.column.name
                })
        return relationships
