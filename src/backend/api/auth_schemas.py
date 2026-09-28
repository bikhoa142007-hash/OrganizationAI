from pydantic import BaseModel, ConfigDict, Field


class AuthDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(AuthDTO):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    remember_me: bool = False


class RegisterRequest(AuthDTO):
    username: str = Field(min_length=3, max_length=80)
    contact: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=12, max_length=1024)


class AuthenticatedUser(AuthDTO):
    id: str
    user_code: str
    username: str
    email: str | None
    phone: str | None
    display_name: str
    status: str
    roles: list[str]


class AuthResponse(AuthDTO):
    user: AuthenticatedUser
