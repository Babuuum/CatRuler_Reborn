from pydantic import BaseModel


class AvailableModelsResponse(BaseModel):
    text_model_keys: list[str]
    image_model_keys: list[str]
