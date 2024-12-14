from typing import Callable, List, Dict, Any, Optional, Type, Union
from forge.utils import *
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Table
from pydantic import BaseModel, create_model, Field
from enum import Enum
from sqlalchemy import Enum as SQLAlchemyEnum
from enum import Enum as PyEnum


class CRUD:
    """Class to handle CRUD operations with FastAPI routes."""
    
    def __init__(
        self,
        table: Table,
        pydantic_model: Type[BaseModel],
        sqlalchemy_model: Type[Any],
        router: APIRouter,
        db_dependency: Callable,
        tags: Optional[List[Union[str, Enum]]] = None,
        prefix: str = ""
    ):
        """Initialize CRUD handler with common parameters."""
        self.table = table
        self.pydantic_model = pydantic_model
        self.sqlalchemy_model = sqlalchemy_model
        self.router = router
        self.db_dependency = db_dependency
        self.tags = tags
        self.prefix = prefix
        
        # Create query params model once for reuse
        self.query_params = self._create_query_params()

    def _create_query_params(self) -> Type[BaseModel]:
        """Create a Pydantic model for query parameters."""
        query_fields = {}
        
        # Get fields from pydantic model
        for field_name, field in self.pydantic_model.__annotations__.items():
            # Make all fields optional for query params
            if hasattr(field, "__origin__") and field.__origin__ is Union:
                # If field is already Optional
                query_fields[field_name] = (field, Field(default=None))
            else:
                # Make field Optional
                query_fields[field_name] = (Optional[field], Field(default=None))

        # Create the query params model
        return create_model(
            f"{self.pydantic_model.__name__}QueryParams",
            **query_fields,
            __base__=BaseModel
        )

    def _get_route_path(self, operation: str = "") -> str:
        """Generate route path with optional prefix."""
        base_path = f"/{self.table.name.lower()}"
        if operation:
            base_path = f"{base_path}/{operation}"
        return f"{self.prefix}{base_path}"

    def create(self) -> None:
        """Add CREATE route."""
        @self.router.post(
            self._get_route_path(),
            response_model=self.pydantic_model,
            tags=self.tags,
            summary=f"Create {self.table.name}",
            description=f"Create a new {self.table.name} record"
        )
        def create_resource(
            resource: self.pydantic_model,
            db: Session = Depends(self.db_dependency)
        ) -> self.pydantic_model:
            data = resource.model_dump(exclude_unset=True)
            
            # Only remove the primary key UUID if it exists, keep foreign key UUIDs
            for column in self.table.columns:
                if column.type.python_type == uuid.UUID and column.primary_key:
                    data.pop(column.name, None)
                    
            try:
                db_resource = self.sqlalchemy_model(**data)
                db.add(db_resource)
                db.commit()
                db.refresh(db_resource)
                result_dict = {
                    column.name: getattr(db_resource, column.name) 
                    for column in self.table.columns
                }
                return self.pydantic_model(**result_dict)
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=400, detail=f"Creation failed: {str(e)}")

    def read(self) -> None:
        """Add READ route."""
        @self.router.get(
            self._get_route_path(),
            response_model=List[self.pydantic_model],
            tags=self.tags,
            summary=f"Get {self.table.name} resources",
            description=f"Retrieve {self.table.name} records with optional filtering"
        )
        def read_resources(
            db: Session = Depends(self.db_dependency),
            filters: self.query_params = Depends()
        ) -> List[self.pydantic_model]:
            query = db.query(self.sqlalchemy_model)
            filters_dict = filters.model_dump(exclude_unset=True)

            for column_name, value in filters_dict.items():
                if value is not None:
                    column = getattr(self.sqlalchemy_model, column_name)
                    if isinstance(column.type, SQLAlchemyEnum):
                        if isinstance(value, str):
                            query = query.filter(column == value)
                        elif isinstance(value, PyEnum):
                            query = query.filter(column == value.value)
                    else:
                        query = query.filter(column == value)

            resources = query.all()
            return [
                self.pydantic_model.model_validate(resource.__dict__) 
                for resource in resources
            ]


    # todo: Fix the return "updated_data"
    # todo: - The "updated_data" currently returns [] for all cases
    # todo: - But the "old_data" returns the correct data (old data before update)
    def update(self) -> None:
        """Add UPDATE route."""
        @self.router.put(
            self._get_route_path(),
            response_model=Dict[str, Any],
            tags=self.tags,
            summary=f"Update {self.table.name}",
            description=f"Update {self.table.name} records that match the filter criteria"
        )
        def update_resource(
            resource: self.pydantic_model,
            db: Session = Depends(self.db_dependency),
            filters: self.query_params = Depends()
        ) -> Dict[str, Any]:
            update_data = resource.model_dump(exclude_unset=True)
            filters_dict = filters.model_dump(exclude_unset=True)

            if not filters_dict:
                raise HTTPException(status_code=400, detail="No filters provided")

            try:
                query = db.query(self.sqlalchemy_model)
                for attr, value in filters_dict.items():
                    if value is not None:
                        query = query.filter(getattr(self.sqlalchemy_model, attr) == value)

                old_data = [
                    self.pydantic_model.model_validate(data.__dict__) 
                    for data in query.all()
                ]

                if not old_data:
                    raise HTTPException(status_code=404, detail="No matching resources found")

                updated_count = query.update(update_data)
                db.commit()

                updated_data = [
                    self.pydantic_model.model_validate(data.__dict__) 
                    for data in query.all()
                ]

                return {
                    "updated_count": updated_count,
                    "old_data": [d.model_dump() for d in old_data],
                    "updated_data": [d.model_dump() for d in updated_data]
                }
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=400, detail=f"Update failed: {str(e)}")

    def delete(self) -> None:
        """Add DELETE route."""
        @self.router.delete(
            self._get_route_path(),
            response_model=Dict[str, Any],
            tags=self.tags,
            summary=f"Delete {self.table.name}",
            description=f"Delete {self.table.name} records that match the filter criteria"
        )
        def delete_resource(
            db: Session = Depends(self.db_dependency),
            filters: self.query_params = Depends()
        ) -> Dict[str, Any]:
            filters_dict = filters.model_dump(exclude_unset=True)
            
            if not filters_dict:
                raise HTTPException(status_code=400, detail="No filters provided")

            query = db.query(self.sqlalchemy_model)
            for attr, value in filters_dict.items():
                if value is not None:
                    query = query.filter(getattr(self.sqlalchemy_model, attr) == value)
            
            try:
                # Get resources before deletion
                to_delete = query.all()
                if not to_delete:
                    return {"message": "No resources found matching the criteria"}
                
                # Store the data before deletion
                deleted_resources = [
                    self.pydantic_model.model_validate(resource.__dict__).model_dump() 
                    for resource in to_delete
                ]
                
                # Perform deletion
                deleted_count = query.delete(synchronize_session=False)
                db.commit()
                
                return {
                    "message": f"{deleted_count} resource(s) deleted successfully",
                    "deleted_resources": deleted_resources
                }
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=400, detail=f"Deletion failed: {str(e)}")

    def generate_all(self) -> None:
        """Generate all CRUD routes."""
        # print(f"\tGen {gray("CRUD")} -> {self.table.name}")
        self.create()
        self.read()
        self.update()
        self.delete()
