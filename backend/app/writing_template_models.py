"""Reusable email content, separate from sequence step templates."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Scoped


class WritingTemplate(Scoped, Base):
    __tablename__ = "writing_templates"

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), default="Custom")
    subject: Mapped[str] = mapped_column(String(1000), default="")
    body_html: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
