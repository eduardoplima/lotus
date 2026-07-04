"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from db.session import get_session
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

SessionDep = Annotated[AsyncSession, Depends(get_session)]
