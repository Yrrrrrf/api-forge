from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from forge.core.config import UvicornConfig
from forge.core.logging import bold, underline, italic, green


class ForgeInfo(BaseModel):
    PROJECT_NAME: str = Field(..., description="The name of your project")
    VERSION: str = Field(default="0.1.0", description="The version of your project")
    DESCRIPTION: Optional[str] = Field(default=None, description="A brief description of your project")
    AUTHOR: Optional[str] = Field(default=None)  # author name
    EMAIL: Optional[str] = Field(default=None)  # contact mail
    LICENSE: Optional[str] = Field(default='MIT', description="The license for the project")
    LICENSE_URL: Optional[str] = Field(default='https://choosealicense.com/licenses/mit/')

    def to_dict(self) -> dict: return self.model_dump()
    
    # *  Sames as 'Rust's PartialEq trait' -> derive[(PartialEq)]
    # def __eq__(self, other):
    #     match isinstance(other, ForgeInfo):
    #         case True: return self.to_dict() == other.to_dict()
    #         case False: return False

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
        # todo: Somehow, make this message appear at the last...
        # todo: ...after all the FastAPI app routes have been added
        # ^ For now it appears at the beginning (the Forge instance creation)
        print(f"\n\n{bold(self.info.PROJECT_NAME)} on {underline(italic(bold(green(f'http://{self.uvicorn_config.host}:{self.uvicorn_config.port}/docs'))))}\n\n")
