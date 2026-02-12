"""
Markdown rendering service
"""
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.codehilite import CodeHiliteExtension
from pymdownx import emoji, superfences, tasklist


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
    
    # Basic sanitization if safe mode is on
    if safe:
        # Remove potentially dangerous tags and attributes
        # This is a basic implementation - consider using bleach for production
        dangerous_tags = ['<script', '<iframe', '<object', '<embed']
        for tag in dangerous_tags:
            html = html.replace(tag, '&lt;' + tag[1:])
    
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
