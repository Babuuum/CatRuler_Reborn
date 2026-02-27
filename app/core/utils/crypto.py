from cryptography.fernet import Fernet
from app.core.settings import get_settings

def get_fernet() -> Fernet:
    return Fernet(get_settings().ENCRYPTION_KEY.encode())

def encrypt(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    return get_fernet().decrypt(value.encode()).decode()