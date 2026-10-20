"""SlothForm background and browser automation services."""

from app.services.browserbase_service import BrowserbaseService
from app.services.document_generator import (
    SyntheticDocumentGenerator,
    generate_synthetic_resume,
    generate_synthetic_w8ben,
)
from app.services.dom_extractor import DOMExtractor
from app.services.essay_synthesizer import (
    EssaySynthesizer,
    InvalidTaxIdentifierError,
    MissingTaxIdentifierError,
    W8BENResolver,
)
from app.services.fill_orchestrator import FillOrchestrator
from app.services.form_filler import FormFiller

__all__ = [
    "BrowserbaseService",
    "DOMExtractor",
    "EssaySynthesizer",
    "FillOrchestrator",
    "FormFiller",
    "InvalidTaxIdentifierError",
    "MissingTaxIdentifierError",
    "SyntheticDocumentGenerator",
    "W8BENResolver",
    "generate_synthetic_resume",
    "generate_synthetic_w8ben",
]
