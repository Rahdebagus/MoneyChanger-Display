"""Auth, user and branch payloads."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class BranchSummary(ORMModel):
    id: int
    name: str
    timezone: str
    is_active: bool


class UserOut(ORMModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    branches: List[BranchSummary] = []


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    full_name: Optional[str] = Field(None, max_length=128)
    role: str = UserRole.STAFF.value
    branch_ids: List[int] = []

    @field_validator("username")
    @classmethod
    def _username_shape(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise ValueError("Username hanya boleh huruf, angka, titik, strip, garis bawah.")
        return cleaned

    @field_validator("role")
    @classmethod
    def _role_known(cls, value: str) -> str:
        if value not in {UserRole.ADMIN.value, UserRole.STAFF.value}:
            raise ValueError("Role harus admin atau staff.")
        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=256)
    branch_ids: Optional[List[int]] = None

    @field_validator("role")
    @classmethod
    def _role_known(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {UserRole.ADMIN.value, UserRole.STAFF.value}:
            raise ValueError("Role harus admin atau staff.")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    timezone: str = Field("Asia/Makassar", max_length=64)


class BranchUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    timezone: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None
