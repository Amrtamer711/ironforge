"""
Platform-agnostic text formatting utilities.

This module provides a central place for text formatting that can be
converted to any platform's native format.
"""

import re
from typing import List, Tuple
from .base import MessageFormat


class ChannelFormatter:
    """
    Unified text formatter that converts between formats.

    Standard input format is Markdown. Each channel adapter can use
    this to convert to their platform-specific format.
    """

    @staticmethod
    def markdown_to_slack(text: str) -> str:
        """
        Convert standard markdown to Slack's mrkdwn format.

        Conversions:
        - **bold** -> *bold*
        - *italic* -> _italic_
        - `code` -> `code` (same)
        - [link](url) -> <url|link>
        - # Header -> *Header*
        - - bullet -> • bullet
        """
        if not text:
            return text

        # Store code blocks to avoid processing them
        code_blocks: List[Tuple[str, str]] = []
        inline_codes: List[Tuple[str, str]] = []

        # Preserve code blocks
        def save_code_block(match):
            placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
            code_blocks.append((placeholder, match.group(0)))
            return placeholder

        def save_inline_code(match):
            placeholder = f"__INLINE_CODE_{len(inline_codes)}__"
            inline_codes.append((placeholder, match.group(0)))
            return placeholder

        # Save code blocks and inline code
        text = re.sub(r'```[\s\S]*?```', save_code_block, text)
        text = re.sub(r'`[^`]+`', save_inline_code, text)

        # Convert bold: **text** or __text__ -> *text*
        text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
        text = re.sub(r'__(.+?)__', r'*\1*', text)

        # Convert italic: *text* (single) -> _text_
        # Be careful not to convert already-converted bold
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'_\1_', text)

        # Convert links: [text](url) -> <url|text>
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', text)

        # Convert headers: # Header -> *Header*
        text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)

        # Convert bullet points: - item or * item -> • item
        text = re.sub(r'^[\-\*]\s+', '• ', text, flags=re.MULTILINE)

        # Convert numbered lists: 1. item -> 1. item (keep as-is)

        # Convert blockquotes: > text -> > text (Slack supports this)

        # Convert strikethrough: ~~text~~ -> ~text~
        text = re.sub(r'~~(.+?)~~', r'~\1~', text)

        # Restore code blocks and inline code
        for placeholder, original in code_blocks:
            text = text.replace(placeholder, original)
        for placeholder, original in inline_codes:
            text = text.replace(placeholder, original)

        return text

    @staticmethod
    def markdown_to_teams(text: str) -> str:
        """
        Convert standard markdown to Microsoft Teams format.

        Teams uses a variant of markdown with some differences.
        """
        if not text:
            return text

        # Teams supports most standard markdown
        # Main differences:
        # - Mentions: <at>user</at>
        # - Some HTML support

        # For now, return mostly as-is since Teams supports markdown
        return text

    @staticmethod
    def markdown_to_html(text: str) -> str:
        """
        Convert markdown to basic HTML for web interfaces.
        """
        if not text:
            return text

        # Store code blocks
        code_blocks: List[Tuple[str, str]] = []
        inline_codes: List[Tuple[str, str]] = []

        def save_code_block(match):
            placeholder = f"__CODE_BLOCK_{len(code_blocks)}__"
            lang = match.group(1) or ""
            code = match.group(2)
            html = f'<pre><code class="language-{lang}">{code}</code></pre>'
            code_blocks.append((placeholder, html))
            return placeholder

        def save_inline_code(match):
            placeholder = f"__INLINE_CODE_{len(inline_codes)}__"
            inline_codes.append((placeholder, f'<code>{match.group(1)}</code>'))
            return placeholder

        # Save code blocks
        text = re.sub(r'```(\w*)\n?([\s\S]*?)```', save_code_block, text)
        text = re.sub(r'`([^`]+)`', save_inline_code, text)

        # Convert bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)

        # Convert italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)

        # Convert links
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

        # Convert headers
        text = re.sub(r'^#{6}\s+(.+)$', r'<h6>\1</h6>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{5}\s+(.+)$', r'<h5>\1</h5>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{4}\s+(.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{3}\s+(.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{2}\s+(.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^#{1}\s+(.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

        # Convert bullet points
        text = re.sub(r'^[\-\*]\s+(.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)

        # Convert blockquotes
        text = re.sub(r'^>\s+(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)

        # Convert strikethrough
        text = re.sub(r'~~(.+?)~~', r'<del>\1</del>', text)

        # Convert line breaks
        text = text.replace('\n', '<br>\n')

        # Restore code
        for placeholder, html in code_blocks:
            text = text.replace(placeholder, html)
        for placeholder, html in inline_codes:
            text = text.replace(placeholder, html)

        return text

    @staticmethod
    def markdown_to_plain(text: str) -> str:
        """
        Strip markdown formatting to plain text.
        """
        if not text:
            return text

        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)

        # Remove inline code backticks
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Remove bold/italic markers
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)

        # Convert links to just text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Remove header markers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Convert bullet points to dashes
        text = re.sub(r'^[\-\*]\s+', '- ', text, flags=re.MULTILINE)

        # Remove blockquote markers
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)

        # Remove strikethrough
        text = re.sub(r'~~(.+?)~~', r'\1', text)

        return text

    @classmethod
    def convert(
        cls,
        text: str,
        target_format: MessageFormat,
        source_format: MessageFormat = MessageFormat.MARKDOWN,
    ) -> str:
        """
        Convert text from one format to another.

        Args:
            text: Input text
            target_format: Desired output format
            source_format: Input format (default: MARKDOWN)

        Returns:
            Converted text
        """
        if not text:
            return text

        if source_format == target_format:
            return text

        # If source is not markdown, first convert to markdown
        # (For now, assume all input is markdown)

        # Convert from markdown to target
        if target_format == MessageFormat.PLAIN:
            return cls.markdown_to_plain(text)
        elif target_format == MessageFormat.MARKDOWN:
            return text
        elif target_format == MessageFormat.RICH:
            # Rich format depends on platform, return as-is
            return text

        return text


# Convenience functions for direct import
def to_slack(text: str) -> str:
    """Convert markdown to Slack mrkdwn format."""
    return ChannelFormatter.markdown_to_slack(text)


def to_teams(text: str) -> str:
    """Convert markdown to Teams format."""
    return ChannelFormatter.markdown_to_teams(text)


def to_html(text: str) -> str:
    """Convert markdown to HTML."""
    return ChannelFormatter.markdown_to_html(text)


def to_plain(text: str) -> str:
    """Strip markdown to plain text."""
    return ChannelFormatter.markdown_to_plain(text)
