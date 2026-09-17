from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StepInput(StrictInput):
    id: str | None = None
    draft_id: str | None = None
    title: str = Field("Email", min_length=1, max_length=200)
    purpose: str = Field("", max_length=4000)
    delay_days: int = Field(0, ge=0, le=365, strict=True)
    thread_mode: Literal["new_thread", "reply"] = "new_thread"


def validate_order(steps):
    if steps and (steps[0].thread_mode != "new_thread" or steps[0].delay_days != 0):
        raise ValueError("The first step must start a new thread on day 0.")
    return steps


class SequenceCreate(StrictInput):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=4000)
    language: Literal["en", "zh"] = "en"
    contact_id: str | None = None
    persona_id: str | None = None
    template_id: str | None = None
    draft_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def one_source(self):
        if self.template_id and self.draft_ids:
            raise ValueError("Choose either a step template or saved drafts.")
        return self


class SequenceUpdate(StrictInput):
    revision: int = Field(ge=1, strict=True)
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)
    language: Literal["en", "zh"] | None = None
    contact_id: str | None = None
    persona_id: str | None = None
    status: Literal["draft", "ready"] | None = None
    steps: list[StepInput] | None = Field(None, max_length=20)

    @field_validator("steps")
    @classmethod
    def ordered(cls, value):
        return validate_order(value)

    @model_validator(mode="after")
    def no_null_required_fields(self):
        for key in ("name", "description", "language", "status", "steps"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null.")
        return self


class StepCreate(StrictInput):
    revision: int = Field(ge=1, strict=True)
    draft_id: str | None = None
    title: str = Field("Email", min_length=1, max_length=200)
    purpose: str = Field("", max_length=4000)
    delay_days: int = Field(3, ge=0, le=365, strict=True)
    thread_mode: Literal["new_thread", "reply"] = "reply"


class TemplateStep(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field("", max_length=4000)
    delay_days: int = Field(0, ge=0, le=365, strict=True)
    thread_mode: Literal["new_thread", "reply"] = "new_thread"
    subject: str = Field("", max_length=1000)
    body_html: str = Field("<p></p>", max_length=60000)


class TemplateInput(StrictInput):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=4000)
    steps: list[TemplateStep] = Field(min_length=1, max_length=20)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version must be the integer 1.")
        return value

    @field_validator("steps")
    @classmethod
    def ordered(cls, value):
        return validate_order(value)


class SaveTemplateInput(StrictInput):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=4000)


class AIPlanInput(StrictInput):
    revision: int = Field(ge=1, strict=True)
    prompt: str = Field(min_length=1, max_length=6000)
    step_count: int = Field(3, ge=1, le=8, strict=True)
    model: str = Field("", max_length=150)
    language: Literal["en", "zh"] | None = None
