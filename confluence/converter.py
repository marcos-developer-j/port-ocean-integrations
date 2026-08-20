"""
Conversor de contenido HTML de Confluence (storage format) a Markdown.

Confluence almacena el contenido en un formato XML/HTML llamado "storage format".
Este módulo lo convierte a Markdown limpio para usar como documentación.
"""

import re
from typing import Any

from loguru import logger

try:
    from markdownify import markdownify as md
    MARKDOWNIFY_AVAILABLE = True
except ImportError:
    MARKDOWNIFY_AVAILABLE = False
    logger.warning(
        "markdownify not installed. Markdown conversion will use basic fallback. "
        "Install with: pip install markdownify"
    )


def confluence_storage_to_markdown(html_content: str) -> str:
    """
    Convierte el contenido HTML de Confluence (storage format) a Markdown.

    Args:
        html_content: El contenido en formato storage de Confluence.

    Returns:
        Contenido convertido a Markdown.
    """
    if not html_content:
        return ""

    # Pre-procesamiento: manejar macros de Confluence
    content = _preprocess_confluence_macros(html_content)

    if MARKDOWNIFY_AVAILABLE:
        # Usar markdownify para la conversión principal
        markdown = md(
            content,
            heading_style="atx",  # # style headings
            bullets="-",
            code_language_callback=_detect_code_language,
        )
    else:
        # Fallback básico si markdownify no está disponible
        markdown = _basic_html_to_markdown(content)

    # Post-procesamiento
    markdown = _postprocess_markdown(markdown)

    return markdown


def _preprocess_confluence_macros(html: str) -> str:
    """Convierte macros de Confluence a HTML estándar antes de la conversión."""

    # Macro de código: <ac:structured-macro ac:name="code">...</ac:structured-macro>
    html = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?'
        r'</ac:structured-macro>',
        r'<pre><code>\1</code></pre>',
        html,
        flags=re.DOTALL,
    )

    # Macro de panel/info/warning/note
    for panel_type in ['info', 'warning', 'note', 'tip', 'panel']:
        html = re.sub(
            rf'<ac:structured-macro[^>]*ac:name="{panel_type}"[^>]*>.*?'
            r'<ac:rich-text-body>(.*?)</ac:rich-text-body>.*?'
            r'</ac:structured-macro>',
            rf'<blockquote><strong>{panel_type.upper()}:</strong> \1</blockquote>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Macro de tabla de contenidos: eliminar (no tiene sentido en markdown simple)
    html = re.sub(
        r'<ac:structured-macro[^>]*ac:name="toc"[^>]*>.*?</ac:structured-macro>',
        '',
        html,
        flags=re.DOTALL,
    )

    # Enlaces internos de Confluence
    html = re.sub(
        r'<ac:link><ri:page ri:content-title="([^"]+)"[^/]*/></ac:link>',
        r'[\1]()',
        html,
    )

    # Imágenes de Confluence
    html = re.sub(
        r'<ac:image[^>]*><ri:attachment ri:filename="([^"]+)"[^/]*/></ac:image>',
        r'![\1](attachments/\1)',
        html,
    )

    # Eliminar otros macros no soportados pero mantener contenido
    html = re.sub(
        r'<ac:structured-macro[^>]*>.*?<ac:rich-text-body>(.*?)</ac:rich-text-body>.*?</ac:structured-macro>',
        r'\1',
        html,
        flags=re.DOTALL,
    )

    # Eliminar cualquier otro tag ac: o ri: restante
    html = re.sub(r'</?ac:[^>]*>', '', html)
    html = re.sub(r'</?ri:[^>]*/?>', '', html)

    return html


def _detect_code_language(tag: Any) -> str | None:
    """Detecta el lenguaje de un bloque de código."""
    if tag.get('class'):
        classes = tag.get('class', [])
        for cls in classes:
            if cls.startswith('language-'):
                return cls.replace('language-', '')
    return None


def _basic_html_to_markdown(html: str) -> str:
    """Conversión básica de HTML a Markdown (fallback sin markdownify)."""
    # Headers
    for i in range(6, 0, -1):
        html = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', r'\n' + '#' * i + r' \1\n', html, flags=re.DOTALL)

    # Bold
    html = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', html, flags=re.DOTALL)
    html = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', html, flags=re.DOTALL)

    # Italic
    html = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', html, flags=re.DOTALL)
    html = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', html, flags=re.DOTALL)

    # Code
    html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL)
    html = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', html, flags=re.DOTALL)

    # Links
    html = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', html, flags=re.DOTALL)

    # Lists
    html = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html, flags=re.DOTALL)
    html = re.sub(r'</?[ou]l[^>]*>', '', html)

    # Paragraphs and breaks
    html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.DOTALL)
    html = re.sub(r'<br[^>]*/?\s*>', '\n', html)

    # Blockquotes
    html = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'> \1', html, flags=re.DOTALL)

    # Remove remaining HTML tags
    html = re.sub(r'<[^>]+>', '', html)

    # Decode HTML entities
    import html as html_module
    html = html_module.unescape(html)

    return html


def _postprocess_markdown(markdown: str) -> str:
    """Limpieza final del markdown generado."""
    # Normalizar saltos de línea
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)

    # Eliminar espacios al final de líneas
    markdown = re.sub(r' +$', '', markdown, flags=re.MULTILINE)

    # Eliminar líneas que solo tienen espacios
    markdown = re.sub(r'^\s+$', '', markdown, flags=re.MULTILINE)

    return markdown.strip()


def enrich_page_with_markdown(page: dict) -> dict:
    """
    Enriquece un objeto de página con su contenido convertido a Markdown.

    Args:
        page: Diccionario de página de Confluence con body.storage.value

    Returns:
        Página enriquecida con campo 'markdown'
    """
    body = page.get("body", {})
    storage = body.get("storage", {})
    html_content = storage.get("value", "")

    page["markdown"] = confluence_storage_to_markdown(html_content)

    return page
