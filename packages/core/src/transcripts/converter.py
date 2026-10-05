"""Convert JSON transcript to text formats with speaker labels."""

from typing import Callable, Dict, List, Literal

from transcripts.models import Transcript


def format_timestamp(ms: int) -> str:
    """Convert milliseconds to HH:MM:SS format."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_header(data: Dict, style: str = "plain") -> List[str]:
    """Generate header lines. style: 'plain', 'simple', 'markdown', or 'none'"""
    if style == "none":
        return []

    lines = []
    title = data.get('title', 'Transcript')
    duration = data.get('duration')
    video_url = data.get('video_url', 'N/A')

    if style == "markdown":
        lines.append(f"# {title}")
        lines.append("")
        if duration:
            lines.append(f"**Duration:** {duration} seconds ({duration // 60} minutes)")
        lines.append(f"**Video URL:** {video_url}")
        lines.append("")
        lines.append("---")
        lines.append("")
    elif style == "simple":
        lines.append(title)
        if duration:
            lines.append(f"Duration: {duration} seconds ({duration // 60} minutes)")
        lines.append(f"Video URL: {video_url}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")
    else:  # plain
        lines.append(f"# {title}")
        if duration:
            lines.append(f"Duration: {duration} seconds ({duration // 60} minutes)")
        lines.append(f"Video URL: {video_url}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

    return lines


def _format_utterances(data: Dict, line_formatter: Callable[[Dict], List[str]]) -> List[str]:
    """Process utterances with custom line formatter."""
    utterances = data.get('utterances', [])
    if not utterances:
        return [data.get('transcript_text', '')]

    lines = []
    for utterance in utterances:
        text = utterance.get('text', '').strip()
        if text:
            lines.extend(line_formatter(utterance))
    return lines


def convert_to_conversation_format(data: Dict) -> str:
    """
    Format 1: Conversation Style (like a script)

    SPEAKER A: Text here...

    SPEAKER B: Response here...
    """
    lines = _format_header(data, "plain")
    lines += _format_utterances(data, lambda u: [f"SPEAKER {u.get('speaker', 'UNKNOWN')}: {u.get('text', '').strip()}", ""])
    return "\n".join(lines)


def convert_to_timestamped_format(data: Dict) -> str:
    """
    Format 2: Timestamped Conversation

    [00:00:00] SPEAKER A: Text here...
    [00:00:15] SPEAKER B: Response here...
    """
    def format_line(u: Dict) -> List[str]:
        timestamp = format_timestamp(u.get('start', 0))
        return [f"[{timestamp}] SPEAKER {u.get('speaker', 'UNKNOWN')}: {u.get('text', '').strip()}", ""]

    lines = _format_header(data, "plain")
    lines += _format_utterances(data, format_line)
    return "\n".join(lines)


def convert_to_markdown_format(data: Dict) -> str:
    """
    Format 3: Markdown with Headers

    ## Speaker A
    Text here...

    ## Speaker B
    Response here...
    """
    lines = _format_header(data, "markdown")
    lines += _format_utterances(data, lambda u: [f"## Speaker {u.get('speaker', 'UNKNOWN')}", "", u.get('text', '').strip(), ""])
    return "\n".join(lines)


def convert_to_simple_format(data: Dict) -> str:
    """
    Format 4: Simple Text Blocks

    === Speaker A ===
    Text here...

    === Speaker B ===
    Response here...
    """
    lines = _format_header(data, "simple")
    lines += _format_utterances(data, lambda u: [f"=== Speaker {u.get('speaker', 'UNKNOWN')} ===", u.get('text', '').strip(), ""])
    return "\n".join(lines)


def convert_to_compact_format(data: Dict) -> str:
    """
    Format 5: Compact (minimal metadata)

    [A] Text here...
    [B] Response here...
    """
    lines = _format_utterances(data, lambda u: [f"[{u.get('speaker', 'UNKNOWN')}] {u.get('text', '').strip()}"])
    return "\n".join(lines)


FORMAT_FUNCTIONS = {
    'conversation': convert_to_conversation_format,
    'timestamped': convert_to_timestamped_format,
    'markdown': convert_to_markdown_format,
    'simple': convert_to_simple_format,
    'compact': convert_to_compact_format,
}


def convert_transcript_to_text(
    transcript: Transcript,
    format_type: str = 'conversation'
) -> str:
    """
    Convert a Transcript object to text format.

    Args:
        transcript: Transcript object to convert
        format_type: Output format ('conversation', 'timestamped', 'markdown', 'simple', 'compact')

    Returns:
        Formatted text string
    """
    data = transcript.to_dict()
    format_func = FORMAT_FUNCTIONS.get(format_type, convert_to_conversation_format)
    return format_func(data)


def convert_dict_to_text(
    data: Dict,
    format_type: str = 'conversation'
) -> str:
    """
    Convert a transcript dictionary to text format.

    Args:
        data: Dictionary containing transcript data
        format_type: Output format ('conversation', 'timestamped', 'markdown', 'simple', 'compact')

    Returns:
        Formatted text string
    """
    format_func = FORMAT_FUNCTIONS.get(format_type, convert_to_conversation_format)
    return format_func(data)


def get_available_formats() -> List[str]:
    """Get list of available output formats."""
    return list(FORMAT_FUNCTIONS.keys())

