from pydantic import BaseModel


class LoginRequest(BaseModel):
    telegram_id: int
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
