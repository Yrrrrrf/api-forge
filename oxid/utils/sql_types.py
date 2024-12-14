import re
from typing import Any, Dict, Type, List, Optional, Union, get_args, get_origin
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, create_model, Field, ConfigDict

class DynamicBase(BaseModel):
    """Base class for dynamically created models"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

class ArrayType(BaseModel):
    """Wrapper class for array types"""
    item_type: Type = Field(...)

    def __call__(self) -> List:
        return list()

def infer_type(value: Any) -> Type:
    """Infer Python type from a value"""
    match value:
        case None: return Any
        case _ if isinstance(value, bool): return bool
        case _ if isinstance(value, int): return int
        case _ if isinstance(value, float): return float
        case _ if isinstance(value, datetime): return datetime
        case _ if isinstance(value, UUID): return UUID
        case _ if isinstance(value, str):
            try: return UUID(value)  # Try to parse as UUID
            except: return str  # Default to string


def create_dynamic_model(json_data: Any, model_name: str) -> Type[BaseModel]:
    """Create a Pydantic model dynamically from JSON data"""
    match json_data:
        # todo: Add tuple?
        case _ if isinstance(json_data, list) and json_data: template = json_data[0]
        case _ if isinstance(json_data, dict): template = json_data
        case _: raise ValueError("Cannot create model from this JSON structure")

    fields = {}
    for key, value in template.items():
        match value:
            case _ if isinstance(value, dict):  # * Nested object
                nested_model = create_dynamic_model(value, f"{model_name}_{key}")
                fields[key] = (nested_model, Field(default_factory=nested_model))
            case _ if isinstance(value, list) and value and isinstance(value[0], dict):  # * List of objects
                nested_model = create_dynamic_model(value[0], f"{model_name}_{key}_item")
                fields[key] = (List[nested_model], Field(default_factory=list))
            case _:  # * Simple type
                fields[key] = (Optional[infer_type(value)], Field(default=None))

    return create_model(
        model_name,
        __base__=DynamicBase,
        **fields
    )

class JSONBType:
    """Wrapper class for JSONB types with dynamic model creation"""
    def __init__(self, sample_data: Any = None):
        self.sample_data = sample_data
        self._model_cache = {}

    def get_model(self, name: str) -> Type[BaseModel]:
        """Get or create a model for the JSONB structure"""
        if name not in self._model_cache:
            if self.sample_data is None:
                return dict
            self._model_cache[name] = create_dynamic_model(self.sample_data, name)
        return self._model_cache[name]

SQL_TYPE_MAPPING: Dict[str, Type] = {
    r'uuid': UUID,
    r'varchar(\(\d+\))?': str,
    r'character\s+varying(\(\d+\))?': str,
    r'text': str,
    r'char(\(\d+\))?': str,
    r'integer': int,
    r'bigint': int,
    r'smallint': int,
    r'decimal(\(\d+,\s*\d+\))?': Decimal,
    r'numeric(\(\d+,\s*\d+\))?': Decimal,
    r'real': float,
    r'double\s+precision': float,
    r'bit': bool,
    r'bytea': bytes,
    r'boolean': bool,
    r'date': date,
    r'time(\(\d+\))?(\s+with(out)?\s+time\s+zone)?': time,
    r'timestamp(\(\d+\))?(\s+with(out)?\s+time\s+zone)?': datetime,
    r'interval': timedelta,
    r'json': dict,
    r'jsonb': dict,
    r'enum': str,
}

def parse_array_type(sql_type: str) -> Type:
    base_type = sql_type.replace('[]', '').strip()
    element_type = get_eq_type(base_type, nullable=False)
    if hasattr(element_type, "__origin__") and element_type.__origin__ is Union:
        element_type = element_type.__args__[0]
    return List[element_type]  # Return List directly

def make_optional(type_: Type) -> Type:
    """Make a type optional if it isn't already"""
    match get_origin(type_) is Union and type(None) in get_args(type_):
        case True: return type_
        case _: return Optional[type_]  # Add Optional wrapper

def get_eq_type(sql_type: str, sample_data: Any = None, nullable: bool = True) -> Type:
    """Enhanced type mapping with JSONB support and nullable handling"""
    match sql_type.lower():
        case 'jsonb': return JSONBType(sample_data)
        case 'timestamp': return make_optional(datetime) if nullable else datetime
        case _ if sql_type.endswith('[]'):  # Handle array types
            array_type = parse_array_type(sql_type.lower())
            return make_optional(array_type) if nullable else array_type
        case _:  # * Handle other types (including JSONB)
            for pattern, py_type in SQL_TYPE_MAPPING.items():
                if re.match(pattern, sql_type.lower()):
                    return make_optional(py_type) if nullable else py_type
            return Any  # Default fallback
