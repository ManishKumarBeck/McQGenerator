"""FastAPI dependency providers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .config import Settings
from .database import get_db
from .services.generation import QuestionGenerator


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_generator(request: Request) -> QuestionGenerator:
    return request.app.state.generator


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
Generator = Annotated[QuestionGenerator, Depends(get_generator)]
