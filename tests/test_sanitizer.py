from app.utils.sanitizer import sanitize_llm_markdown


def test_sanitize_removes_scripts():
    raw = """
    # Arquitectura
    <script>alert('XSS')</script>
    El sistema se compone de varios módulos.
    <script src="https://evil.com/malware.js"></script>
    """
    cleaned = sanitize_llm_markdown(raw)
    assert "<script>" not in cleaned
    assert "alert('XSS')" not in cleaned
    assert "evil.com" not in cleaned
    assert "El sistema se compone de varios módulos." in cleaned


def test_sanitize_removes_iframes_and_embeds():
    raw = """
    <iframe src="https://attacker.com/steal"></iframe>
    <object data="malicious.swf"></object>
    <embed src="test.swf"></embed>
    Documentación válida.
    """
    cleaned = sanitize_llm_markdown(raw)
    assert "<iframe" not in cleaned
    assert "<object" not in cleaned
    assert "<embed" not in cleaned
    assert "Documentación válida." in cleaned


def test_sanitize_removes_inline_event_handlers():
    raw = """
    <p onclick="stealCookies()">Texto normal</p>
    <img src="valid.png" onerror="alert(1)">
    """
    cleaned = sanitize_llm_markdown(raw)
    assert "onclick=" not in cleaned
    assert "onerror=" not in cleaned


def test_sanitize_neutralizes_javascript_links():
    raw = """
    [Haz click aquí](javascript:alert(document.cookie))
    <a href="javascript:void(0)">Enlace sospechoso</a>
    """
    cleaned = sanitize_llm_markdown(raw)
    assert "javascript:" not in cleaned
    assert "[Haz click aquí](#)" in cleaned


def test_sanitize_neutralizes_external_images():
    raw = """
    ![diagrama](https://tracker.com/pixel.png)
    <img src="https://evil.com/logger.gif" />
    """
    cleaned = sanitize_llm_markdown(raw)
    assert "<img" not in cleaned
    assert "https://tracker.com/pixel.png" not in cleaned
    assert "[Imagen Externa Omitida: diagrama]" in cleaned
