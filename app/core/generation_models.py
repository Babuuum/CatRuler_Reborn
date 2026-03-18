TEXT_MODEL_KEYS = (
    "or_gemini",
    "or_mistral",
    "hf_deepseek",
    "hf_llama",
    "hf_qwen",
    "hf_phi",
)

IMAGE_MODEL_KEYS = (
    "pollen_flux",
    "pollen_flux_realism",
    "pollen_turbo",
    "hf_sd_spaces",
)

DEFAULT_TEXT_MODEL_KEY = "or_gemini"
DEFAULT_IMAGE_MODEL_KEY = "pollen_flux"

TEXT_MODEL_LABELS = {
    "or_gemini": "OpenRouter Gemma",
    "or_mistral": "OpenRouter Mistral",
    "hf_deepseek": "HF DeepSeek",
    "hf_llama": "HF Llama",
    "hf_qwen": "HF Qwen",
    "hf_phi": "HF Phi",
}

IMAGE_MODEL_LABELS = {
    "pollen_flux": "Pollen Flux",
    "pollen_flux_realism": "Pollen Flux Realism",
    "pollen_turbo": "Pollen Turbo",
    "hf_sd_spaces": "HF Stable Diffusion",
}


def is_valid_text_model_key(value: str) -> bool:
    return value in TEXT_MODEL_KEYS


def is_valid_image_model_key(value: str) -> bool:
    return value in IMAGE_MODEL_KEYS


def get_available_model_keys() -> dict[str, list[str]]:
    return {
        "text_model_keys": list(TEXT_MODEL_KEYS),
        "image_model_keys": list(IMAGE_MODEL_KEYS),
    }
