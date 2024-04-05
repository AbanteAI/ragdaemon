from spice.utils import count_string_tokens


DEFAULT_COMPLETION_MODEL = "gpt-4-0125-preview"


def token_counter(text: str) -> int:
    return count_string_tokens(text, DEFAULT_COMPLETION_MODEL, full_message=True)
