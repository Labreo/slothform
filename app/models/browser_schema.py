"""Pydantic schemas and models for Browserbase cloud automation and DOM extraction."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FieldType(str, Enum):
    """Supported interactive input element types."""
    TEXT = "text"
    EMAIL = "email"
    TEL = "tel"
    URL = "url"
    NUMBER = "number"
    DATE = "date"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    COMBOBOX = "combobox"


class SelectOption(BaseModel):
    """Option descriptor for select and combobox elements."""
    label: str
    value: str


class FormField(BaseModel):
    """Schema descriptor for a single extracted interactive form field."""
    field_id: str
    selector: str
    field_type: FieldType
    label: str
    required: bool = False
    placeholder: Optional[str] = None
    options: List[SelectOption] = Field(default_factory=list)
    current_value: Optional[str] = None
    frame_index: int = 0
    name_attr: Optional[str] = None


class SubmitButton(BaseModel):
    """Descriptor for a detected form submission button."""
    selector: str
    text: str
    is_primary: bool = True


class FormSchema(BaseModel):
    """Structured form representation extracted from the target page DOM."""
    url: str
    page_title: str
    fields: List[FormField] = Field(default_factory=list)
    submit_buttons: List[SubmitButton] = Field(default_factory=list)
    has_iframes: bool = False
    detected_platform: Optional[str] = None  # "greenhouse", "lever", "ashby", "w8ben", "generic"


class FillPlanItem(BaseModel):
    """An individual field assignment within an execution plan."""
    field_id: str
    selector: str
    field_type: FieldType
    value: Any
    frame_index: int = 0


class FillPlan(BaseModel):
    """Complete, validated plan for populating a target form."""
    target_url: str
    items: List[FillPlanItem] = Field(default_factory=list)
    resume_path: Optional[str] = None


class BrowserbaseSession(BaseModel):
    """Browserbase cloud session model."""
    id: str
    connect_url: str
    status: Optional[str] = "RUNNING"
    proxy_bytes: Optional[int] = 0


class FillResult(BaseModel):
    """Outcome of a form fill execution run."""
    status: str  # "DRY_RUN_SUCCESS", "SUBMITTED", "FAILED"
    session_id: str
    replay_url: str
    live_view_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    fields_filled_count: int = 0
    submit_button_detected: Optional[str] = None
    dry_run: bool = True
    submitted: bool = False
    diff: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
