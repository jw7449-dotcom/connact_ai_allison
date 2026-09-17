from typing import Literal
from pydantic import BaseModel, Field, field_validator
import re


class PersonaData(BaseModel):
    name: str = Field("", max_length=200)
    education: str = Field("", max_length=8000)
    experience: str = Field("", max_length=12000)
    skills: str = Field("", max_length=4000)
    sectors: str = Field("", max_length=2000)
    career_goals: str = Field("", max_length=4000)
    target_regions: str = Field("", max_length=2000)
    target_roles: str = Field("", max_length=4000)
    contact_purpose: str = Field("", max_length=4000)


class PersonaInput(BaseModel):
    label: str = Field(min_length=1, max_length=150)
    data: PersonaData
    document_id: str | None = None
    version: int | None = None


class ContactInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str = Field("", max_length=250)
    company: str = Field("", max_length=250)
    location: str = Field("", max_length=250)
    school: str = Field("", max_length=250)
    profile_url: str = Field("", max_length=2000)
    email: str = Field("", max_length=250)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field("", max_length=12000)
    sector: str = Field("", max_length=250)

    @field_validator("profile_url")
    @classmethod
    def safe_url(cls, value):
        if value and not re.match(r"^https?://[^\s]+$", value):
            raise ValueError("Use an http or https profile link.")
        return value

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        if value and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", value):
            raise ValueError("Enter a valid email address or leave it empty.")
        return value


class ContactJobInput(BaseModel):
    kind: Literal["profile", "email", "email_apify"]
    force: bool = False


class SearchInput(BaseModel):
    title: str = Field("", max_length=200)
    company: str = Field("", max_length=200)
    location: str = Field("", max_length=200)
    keywords: str = Field("", max_length=300)
    sector: Literal[
        "",
        "Investment Banking",
        "Private Equity",
        "Asset Management",
        "Venture Capital",
        "Risk Management",
    ] = ""
    page: int = Field(1, ge=1, le=500)
    per_page: int = Field(10, ge=1, le=10)


class AssessmentInput(BaseModel):
    contact_ids: list[str] = Field(min_length=1, max_length=5)
    persona_id: str
    language: Literal["en", "zh"] = "en"


class DraftInput(BaseModel):
    contact_id: str | None = None
    persona_id: str | None = None
    language: Literal["en", "zh"] = "en"
    purpose: str = Field("", max_length=4000)
    starting_point: Literal["Networking", "Informational Interview", "Recruiting", "Follow-up", "Introduction"] = (
        "Networking"
    )
    tone: Literal["professional", "warm", "concise"] = "professional"
    model: str = Field("", max_length=150)
    writing_mode: Literal["assisted", "prompt", "template"] = "assisted"
    length: Literal["short", "medium", "long"] = "medium"
    cta: str = Field("", max_length=2000)
    custom_instructions: str = Field("", max_length=6000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field("", max_length=1000)
    body_html: str = Field("<p></p>", max_length=60000)
    status: Literal["draft", "ready"] = "draft"
    revision: int | None = None


class GenerateInput(BaseModel):
    action: Literal["generate", "shorten", "tone"] = "generate"
    revision: int = Field(ge=1)


class AcceptGenerationInput(BaseModel):
    revision: int = Field(ge=1)
