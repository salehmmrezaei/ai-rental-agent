from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


Password = Annotated[SecretStr, Field(min_length=12, max_length=128)]
Name = Annotated[str, Field(min_length=1, max_length=150)]


class Register(EmailInput):
    password: Password
    full_name: Name
    role: Literal["tenant", "landlord"] = "tenant"

    @field_validator("full_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class Login(EmailInput):
    password: SecretStr = Field(min_length=1, max_length=128)


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: str
    role: Literal["tenant", "landlord", "admin"]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserProfile


class ProfileUpdate(Input):
    full_name: Name | None = None
    email: EmailStr | None = Field(default=None, max_length=254)
    current_password: SecretStr | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("full_name", "email", mode="before")
    @classmethod
    def clean(cls, value, info):
        if value is None:
            raise ValueError("Field cannot be null")
        if isinstance(value, str):
            value = value.strip()
            if info.field_name == "email": value = value.lower()
        return value

    @model_validator(mode="after")
    def validate_change(self):
        if not ({"email", "full_name"} & self.model_fields_set):
            raise ValueError("Provide email or full_name")
        if "email" in self.model_fields_set and not self.current_password:
            raise ValueError("Email changes require current_password")
        return self


class PasswordUpdate(Input):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: Password


class UserPage(BaseModel):
    items: list[UserProfile]
    total: int
    page: int
    page_size: int
