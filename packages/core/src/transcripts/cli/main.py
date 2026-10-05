"""CLI entry point for transcripts package."""

import argparse
import sys
from pathlib import Path
from typing import List

from transcripts.processor import TranscriptProcessor
from transcripts.converter import get_available_formats
from transcripts.state import StateManager
from transcripts.models import Stage


def read_urls_from_file(filepath: str) -> List[str]:
    """
    Read URLs from a text file (one URL per line).

    Args:
        filepath: Path to file containing URLs

    Returns:
        List of URLs
    """
    file_path = Path(filepath)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    urls = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    return urls


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Download YouTube videos, extract audio, and generate transcripts using Deepgram (or AssemblyAI)"
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube video URL (required if not using --playlist or --file)",
    )

    parser.add_argument(
        "--playlist",
        type=str,
        help="YouTube playlist URL",
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Path to file containing URLs (one per line)",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="downloads",
        help="Directory for downloaded files (default: downloads)",
    )

    parser.add_argument(
        "--transcripts-dir",
        type=str,
        default="transcripts",
        help="Directory for transcript JSON files (default: transcripts)",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="API key for transcription provider (overrides .env file)",
    )

    parser.add_argument(
        "--provider",
        type=str,
        choices=["assemblyai", "deepgram"],
        default=None,
        help="Transcription provider to use (overrides TRANSCRIPTION_PROVIDER env var, default: deepgram)",
    )

    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Don't download video files, only extract audio",
    )

    parser.add_argument(
        "--upload-video",
        action="store_true",
        help="Upload video file directly to transcription provider (instead of extracting audio first)",
    )

    # File retention options (default: keep both)
    parser.add_argument(
        "--keep-video",
        action="store_true",
        default=None,
        dest="retain_video",
        help="Keep video file after transcription (default behavior)",
    )

    parser.add_argument(
        "--no-keep-video",
        action="store_false",
        dest="retain_video",
        help="Delete video file after successful transcription",
    )

    parser.add_argument(
        "--keep-audio",
        action="store_true",
        default=None,
        dest="retain_audio",
        help="Keep audio file after transcription (default behavior)",
    )

    parser.add_argument(
        "--no-keep-audio",
        action="store_false",
        dest="retain_audio",
        help="Delete audio file after successful transcription",
    )

    parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "txt", "both", "none"],
        default="both",
        help="Output format: 'json', 'txt', 'both', or 'none' (database only). Default: both",
    )

    parser.add_argument(
        "--txt-format",
        type=str,
        choices=get_available_formats(),
        default="conversation",
        help="Text format when --output-format includes 'txt'. "
             f"Options: {', '.join(get_available_formats())} (default: conversation)",
    )

    # Job management arguments
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of all transcription jobs",
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry all failed transcription jobs",
    )

    parser.add_argument(
        "--clear-completed",
        action="store_true",
        help="Clear completed jobs from history",
    )

    parser.add_argument(
        "--clear-all",
        action="store_true",
        help="Clear all jobs from history",
    )

    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate job history from JSON to SQLite storage",
    )

    # Transcript operations
    parser.add_argument(
        "--search",
        type=str,
        metavar="QUERY",
        help="Search transcripts for a keyword or phrase",
    )

    parser.add_argument(
        "--export",
        type=str,
        metavar="JOB_ID",
        help="Export transcript for a job ID to file",
    )

    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "txt"],
        default="json",
        help="Export format when using --export (default: json)",
    )

    args = parser.parse_args()

    # Initialize state manager
    state_manager = StateManager()

    # Handle job management commands first
    if args.status:
        _show_status(state_manager)
        return

    if args.clear_completed:
        count = state_manager.clear_jobs(filter_stage=Stage.COMPLETED)
        print(f"Cleared {count} completed job(s)")
        return

    if args.clear_all:
        response = input("Are you sure you want to clear ALL job history? [y/N] ")
        if response.lower() == "y":
            count = state_manager.clear_jobs()
            print(f"Cleared {count} job(s)")
        else:
            print("Cancelled")
        return

    if args.retry_failed:
        _retry_failed(state_manager, args)
        return

    if args.migrate:
        _migrate_storage()
        return

    if args.search:
        _search_transcripts(state_manager, args.search)
        return

    if args.export:
        _export_transcript(state_manager, args.export, args.format)
        return

    # Validate arguments for normal processing
    if not args.url and not args.playlist and not args.file:
        parser.error("Must provide either a URL, --playlist, --file, or a job management flag (--status, --retry-failed, --clear-completed, --clear-all)")

    if sum([bool(args.url), bool(args.playlist), bool(args.file)]) > 1:
        parser.error("Can only specify one of: URL, --playlist, or --file")

    try:
        # Determine retention options (default to True if not specified)
        keep_video = args.retain_video if args.retain_video is not None else True
        keep_audio = args.retain_audio if args.retain_audio is not None else True

        # Initialize processor with state manager
        processor = TranscriptProcessor(
            download_dir=args.output_dir,
            transcripts_dir=args.transcripts_dir,
            api_key=args.api_key,
            provider=args.provider,
            output_format=args.output_format,
            txt_format=args.txt_format,
            state_manager=state_manager,
            keep_video=keep_video,
            keep_audio=keep_audio,
        )

        # Determine whether to extract audio
        # Default is True, unless --upload-video is specified
        extract_audio = not args.upload_video

        # Process based on input type
        if args.playlist:
            print(f"Processing playlist: {args.playlist}")
            transcripts = processor.process_playlist(
                args.playlist,
                download_video=not args.no_video,
                extract_audio=extract_audio,
            )
            print(f"Processed {len(transcripts)} videos from playlist")

        elif args.file:
            print(f"Processing URLs from file: {args.file}")
            urls = read_urls_from_file(args.file)
            print(f"Found {len(urls)} URLs")
            transcripts = processor.process_batch(
                urls,
                download_video=not args.no_video,
                extract_audio=extract_audio,
            )
            print(f"Processed {len(transcripts)} videos")

        else:
            print(f"Processing video: {args.url}")
            transcript = processor.process_video(
                args.url,
                download_video=not args.no_video,
                extract_audio=extract_audio,
            )
            print(f"Transcript generated for: {transcript.title}")
            print(f"Transcript text length: {len(transcript.transcript_text)} characters")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


def _show_status(state_manager: StateManager) -> None:
    """Display status of all jobs."""
    jobs = state_manager.list_jobs()

    if not jobs:
        print("No jobs found")
        return

    print(f"\n{'Title':<40} {'Stage':<12} {'Provider':<12} {'Updated':<20} {'Error'}")
    print("-" * 105)

    for job in jobs:
        title = (job.title or job.id)[:38]
        stage = job.stage.value
        provider = job.provider or "-"
        updated = job.updated_at[:19].replace("T", " ")
        error = (job.error or "")[:20]

        # Add color indicators for stage
        if job.stage == Stage.COMPLETED:
            stage_display = f"\033[32m{stage}\033[0m"  # Green
        elif job.stage == Stage.FAILED:
            stage_display = f"\033[31m{stage}\033[0m"  # Red
        elif job.stage in (Stage.DOWNLOADING, Stage.TRANSCRIBING):
            stage_display = f"\033[33m{stage}\033[0m"  # Yellow
        else:
            stage_display = stage

        print(f"{title:<40} {stage_display:<21} {provider:<12} {updated:<20} {error}")

    print()

    # Summary
    completed = sum(1 for j in jobs if j.stage == Stage.COMPLETED)
    failed = sum(1 for j in jobs if j.stage == Stage.FAILED)
    in_progress = sum(1 for j in jobs if j.stage not in (Stage.COMPLETED, Stage.FAILED, Stage.PENDING))

    print(f"Total: {len(jobs)} | Completed: {completed} | Failed: {failed} | In Progress: {in_progress}")


def _retry_failed(state_manager: StateManager, args) -> None:
    """Retry all failed jobs."""
    failed_jobs = state_manager.get_failed_jobs()

    if not failed_jobs:
        print("No failed jobs to retry")
        return

    print(f"Found {len(failed_jobs)} failed job(s) to retry\n")

    # Determine retention options (default to True if not specified)
    keep_video = args.retain_video if args.retain_video is not None else True
    keep_audio = args.retain_audio if args.retain_audio is not None else True

    # Initialize processor with state manager
    processor = TranscriptProcessor(
        download_dir=args.output_dir,
        transcripts_dir=args.transcripts_dir,
        api_key=args.api_key,
        provider=args.provider,
        output_format=args.output_format,
        txt_format=args.txt_format,
        state_manager=state_manager,
        keep_video=keep_video,
        keep_audio=keep_audio,
    )

    extract_audio = not args.upload_video

    for i, job in enumerate(failed_jobs, 1):
        print(f"[{i}/{len(failed_jobs)}] Retrying: {job.title or job.id}")

        try:
            # Reset job to pending so it can be reprocessed
            job.stage = Stage.PENDING
            job.error = None
            state_manager.update_job(job)

            transcript = processor.process_video(
                job.url,
                download_video=not args.no_video,
                extract_audio=extract_audio,
            )
            print(f"  Success: {transcript.title}\n")

        except Exception as e:
            print(f"  Failed: {str(e)}\n")
            continue

    print("Retry complete")


def _migrate_storage() -> None:
    """Migrate job history from JSON to SQLite."""
    from transcripts.storage.migrate import migrate_json_to_sqlite, check_migration_needed

    # Check if migration is needed
    jobs_to_migrate = check_migration_needed()

    if jobs_to_migrate is None:
        print("No migration needed (no JSON state file found or no jobs to migrate)")
        return

    print(f"Found {jobs_to_migrate} job(s) to migrate from JSON to SQLite\n")

    response = input("Proceed with migration? [y/N] ")
    if response.lower() != "y":
        print("Migration cancelled")
        return

    print("\nMigrating jobs...")
    try:
        migrated = migrate_json_to_sqlite()
        print(f"\nSuccessfully migrated {migrated} job(s) to SQLite")
        print("You can now use the default SQLite storage backend")
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


def _search_transcripts(state_manager: StateManager, query: str) -> None:
    """Search transcripts for a keyword or phrase."""
    storage = state_manager._storage

    if not hasattr(storage, 'search_transcripts'):
        print("Search is only available with SQLite storage backend", file=sys.stderr)
        sys.exit(1)

    results = storage.search_transcripts(query)

    if not results:
        print(f"No transcripts found matching: {query}")
        return

    print(f"\nFound {len(results)} result(s) for '{query}':\n")

    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title'] or result['job_id']}")
        print(f"   Job ID: {result['job_id']}")
        # Clean up snippet for display (remove HTML tags for terminal)
        snippet = result['snippet'].replace('<mark>', '\033[1m').replace('</mark>', '\033[0m')
        print(f"   ...{snippet}...")
        print()


def _export_transcript(state_manager: StateManager, job_id: str, format: str) -> None:
    """Export transcript for a job ID to file."""
    import json
    from transcripts.converter import convert_transcript_to_text

    storage = state_manager._storage

    if not hasattr(storage, 'get_transcript'):
        print("Export is only available with SQLite storage backend", file=sys.stderr)
        sys.exit(1)

    transcript = storage.get_transcript(job_id)

    if not transcript:
        print(f"No transcript found for job ID: {job_id}", file=sys.stderr)
        sys.exit(1)

    # Generate filename
    safe_title = transcript.title.lower().replace(" ", "-")[:50] if transcript.title else job_id

    if format == "json":
        filename = f"{safe_title}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(transcript.to_dict(), f, indent=2, ensure_ascii=False)
    else:
        filename = f"{safe_title}.txt"
        content = convert_transcript_to_text(transcript, format_type="conversation")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Exported transcript to: {filename}")


if __name__ == "__main__":
    main()
