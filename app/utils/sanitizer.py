import re

# Dangerous HTML tags
DANGEROUS_TAGS_PATTERN = re.compile(
    r"<\s*(script|iframe|object|embed|applet|meta|form|input|button|svg|base)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)

SELF_CLOSING_DANGEROUS_TAGS = re.compile(
    r"<\s*(script|iframe|object|embed|applet|meta|form|input|button|svg|base)\b[^>]*>",
    re.IGNORECASE,
)

# Inline events: onload=, onerror=, onclick=, etc.
EVENT_HANDLERS_PATTERN = re.compile(
    r"\s+on[a-zA-Z]+\s*=\s*([\"'][^\"']*[\"']|[^\s>]+)",
    re.IGNORECASE,
)

# Javascript URIs in markdown links [text](javascript:...) or HTML href="javascript:..."
JAVASCRIPT_URI_HTML = re.compile(
    r"""(href|src)\s*=\s*["']\s*javascript:[^"']*["']""",
    re.IGNORECASE,
)
JAVASCRIPT_URI_MD = re.compile(
    r"""\[([^\]]+)\]\(\s*javascript:[^)]*\)""",
    re.IGNORECASE,
)

# External image tags in HTML <img src="...">
IMG_TAG_PATTERN = re.compile(
    r"<\s*img\b[^>]*>",
    re.IGNORECASE,
)

# Markdown external images ![alt](http...)
MD_EXTERNAL_IMAGE = re.compile(
    r"!\[([^\]]*)\]\((https?://[^)]+)\)",
    re.IGNORECASE,
)

# CSS expressions inside style attributes
CSS_EXPRESSION_PATTERN = re.compile(
    r"""style\s*=\s*["'][^"']*expression\s*\([^"']*["']""",
    re.IGNORECASE,
)


def sanitize_llm_markdown(content: str) -> str:
    """
    Sanitizes LLM-generated markdown to neutralize prompt-injection XSS payloads
    and dangerous HTML constructs.
    """
    if not content:
        return ""

    sanitized = content

    # 1. Remove dangerous paired tags (<script>...</script>, etc.)
    sanitized = DANGEROUS_TAGS_PATTERN.sub("", sanitized)
    sanitized = SELF_CLOSING_DANGEROUS_TAGS.sub("", sanitized)

    # 2. Remove inline event handlers (onerror=..., onload=...)
    sanitized = EVENT_HANDLERS_PATTERN.sub("", sanitized)

    # 3. Neutralize CSS expressions
    sanitized = CSS_EXPRESSION_PATTERN.sub("", sanitized)

    # 4. Remove javascript: links
    sanitized = JAVASCRIPT_URI_HTML.sub(r'\1="#"', sanitized)
    sanitized = JAVASCRIPT_URI_MD.sub(r"[\1](#)", sanitized)

    # 5. Remove raw HTML <img> tags
    sanitized = IMG_TAG_PATTERN.sub("", sanitized)

    # 6. Neutralize external images in markdown
    sanitized = MD_EXTERNAL_IMAGE.sub(r"[Imagen Externa Omitida: \1]", sanitized)

    return sanitized
