from pydantic import BaseModel, Field, field_validator


class WritingTemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    category: str = Field("Custom", min_length=1, max_length=60)
    subject: str = Field("", max_length=1000)
    body_html: str = Field(min_length=1, max_length=60000)
    revision: int | None = Field(None, ge=1)

    @field_validator("name", "category")
    @classmethod
    def meaningful_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a non-empty value.")
        return value
