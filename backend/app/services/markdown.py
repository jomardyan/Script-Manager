"""
Markdown rendering service
"""
import markdown
import bleach
from pymdownx import emoji, superfences


# Allowed HTML tags and attributes for sanitization
ALLOWED_TAGS = [
    'a', 'abbr', 'acronym', 'b', 'blockquote', 'code', 'em', 'i', 'li', 'ol', 'pre',
    'strong', 'ul', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'span', 'div',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img', 'del', 'ins', 'sub', 'sup'
]

ALLOWED_ATTRIBUTES = {
    '*': ['class', 'id'],
    'a': ['href', 'title', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'table': ['align'],
    'td': ['align', 'colspan', 'rowspan'],
    'th': ['align', 'colspan', 'rowspan'],
}


def render_markdown(content: str, safe: bool = True) -> str:
    """
    Render markdown content to HTML
    
    Args:
        content: Markdown text to render
        safe: If True, sanitize output to prevent XSS
    
    Returns:
        Rendered HTML string
    """
    # Configure extensions
    extensions = [
        'markdown.extensions.fenced_code',
        'markdown.extensions.tables',
        'markdown.extensions.nl2br',
        'markdown.extensions.sane_lists',
        'markdown.extensions.toc',
        'pymdownx.superfences',
        'pymdownx.tasklist',
        'pymdownx.emoji',
        'pymdownx.highlight',
        'pymdownx.inlinehilite',
        'pymdownx.magiclink'
    ]
    
    # Configure extension settings
    extension_configs = {
        'pymdownx.tasklist': {
            'custom_checkbox': True
        },
        'pymdownx.emoji': {
            'emoji_index': emoji.twemoji,
            'emoji_generator': emoji.to_svg
        },
        'pymdownx.superfences': {
            'custom_fences': [
                {
                    'name': 'mermaid',
                    'class': 'mermaid',
                    'format': superfences.fence_code_format
                }
            ]
        }
    }
    
    # Render markdown
    md = markdown.Markdown(
        extensions=extensions,
        extension_configs=extension_configs,
        output_format='html5'
    )
    
    html = md.convert(content)
    
    # Sanitize HTML using bleach for production-grade XSS protection
    if safe:
        html = bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True
        )
        # Also linkify URLs
        html = bleach.linkify(html)
    
    return html


def extract_markdown_preview(content: str, max_length: int = 200) -> str:
    """
    Extract a plain text preview from markdown content
    
    Args:
        content: Markdown text
        max_length: Maximum length of preview
    
    Returns:
        Plain text preview
    """
    # Remove markdown formatting for preview
    # Remove headers
    preview = content
    for i in range(6, 0, -1):
        preview = preview.replace('#' * i + ' ', '')
    
    # Remove code blocks
    lines = preview.split('\n')
    filtered_lines = []
    in_code_block = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            filtered_lines.append(line)
    
    preview = '\n'.join(filtered_lines)
    
    # Remove inline formatting
    preview = preview.replace('**', '').replace('*', '').replace('`', '')
    preview = preview.replace('[', '').replace(']', '').replace('(', '').replace(')', '')
    
    # Truncate to max length
    if len(preview) > max_length:
        preview = preview[:max_length].rsplit(' ', 1)[0] + '...'
    
    return preview.strip()


def validate_markdown(content: str) -> dict:
    """
    Validate markdown content and return info
    
    Args:
        content: Markdown text to validate
    
    Returns:
        Dictionary with validation results
    """
    try:
        # Try to render
        html = render_markdown(content, safe=True)
        
        # Count elements
        lines = content.split('\n')
        headers = sum(1 for line in lines if line.strip().startswith('#'))
        code_blocks = content.count('```') // 2
        links = content.count('[')
        images = content.count('![')
        
        return {
            'valid': True,
            'rendered_length': len(html),
            'source_length': len(content),
            'headers': headers,
            'code_blocks': code_blocks,
            'links': links,
            'images': images
        }
    except Exception as e:
        return {
            'valid': False,
            'error': str(e)
        }
