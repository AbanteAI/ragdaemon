from spice.utils import count_string_tokens


DEFAULT_COMPLETION_MODEL = "gpt-4-0125-preview"


def token_counter(
    text: str, model: str | None = None, full_message: bool = False
) -> int:
    if model is None:
        model = DEFAULT_COMPLETION_MODEL
    return count_string_tokens(message=text, model=model, full_message=full_message)
