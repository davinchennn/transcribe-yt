"""CLI entry point for transcripts package."""

import argparse
import json
import sqlite3
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
    if sys.argv[1:2] == ["list"]:
        _list_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["show"]:
        _show_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["analyze"]:
        _analyze_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["analyses"]:
        _analyses_main(sys.argv[2:])
        return
    if sys.argv[1:2] == ["analysis"]:
        _analysis_main(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(
        description="Download YouTube or X/Twitter videos, extract audio, and generate transcripts using Deepgram (or AssemblyAI)",
        epilog="List saved video data with: transcribe list --help",
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="YouTube video or X/Twitter post URL (required if not using --playlist or --file)",
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
        parser.error("Provide a URL, --playlist, --file, a job management flag, or use 'transcribe list' to inspect saved data")

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


def _show_main(arguments: List[str]) -> None:
    from transcripts.inventory import show_transcript

    parser = argparse.ArgumentParser(prog="transcribe show", description="Read one saved transcript and its metadata without changing records.")
    parser.add_argument("--id", dest="job_id", required=True, help="Exact job ID from transcribe list")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Include metadata, words and timestamped utterances as JSON")
    args = parser.parse_args(arguments)
    try:
        result = show_transcript(args.job_id)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not read saved transcript: {error}\n")
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        job = result["job"]
        print(job["title"] or job["id"])
        print(job["url"])
        print()
        print(job["transcript"].get("transcript_text", ""))


def _list_main(arguments: List[str]) -> None:
    """Inspect saved data before constructing any write-capable storage backend."""
    from transcripts.inventory import list_inventory

    parser = argparse.ArgumentParser(prog="transcribe list", description="List saved videos and available data without changing records.")
    parser.add_argument("--query", help="Match title, URL or job ID (case-insensitive)")
    parser.add_argument("--source", choices=["youtube", "x"], help="Filter by video platform")
    parser.add_argument("--id", dest="job_id", help="Select an exact job ID")
    parser.add_argument("--stage", choices=[stage.value for stage in Stage], help="Filter by processing stage")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print the complete inventory metadata as JSON")
    args = parser.parse_args(arguments)
    try:
        inventory = list_inventory(query=args.query, source=args.source, job_id=args.job_id, stage=args.stage)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not list saved data: {error}\n")
    if args.as_json:
        print(json.dumps(inventory, indent=2, ensure_ascii=False))
        return
    print(f"Storage: {inventory['storage']['backend']} · {inventory['storage']['path']}")
    if not inventory["jobs"]:
        print("No matching jobs found")
        return
    headers = ["ID", "Source", "Stage", "Transcript", "Analyses", "Latest analysis", "Provider", "Title"]
    rows = []
    for job in inventory["jobs"]:
        analyses = job["analyses"]
        latest = analyses[0]["status"] if analyses else (
            "not_supported" if inventory["storage"]["backend"] == "json" else "not_created"
        )
        rows.append([
            job["id"], job["source"] or "Unknown", job["stage"],
            "Yes" if job["transcript"]["available"] else "No",
            str(len(analyses)), latest.replace("_", " ").capitalize(),
            job["transcription_provider"] or "-", " ".join((job["title"] or job["id"]).split()),
        ])
    widths = [max(len(row[index]) for row in [headers] + rows) for index in range(len(headers))]
    for row in [headers] + rows:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip())
    print(f"Total: {inventory['total']}")


def _analyses_main(arguments: List[str]) -> None:
    from transcripts.inventory import saved_analysis_inventory

    parser = argparse.ArgumentParser(prog="transcribe analyses", description="List saved analyses for one transcript without changing records.")
    parser.add_argument("--id", dest="job_id", required=True, help="Exact job ID from transcribe list")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(arguments)
    try:
        result = saved_analysis_inventory(args.job_id)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not read saved analyses: {error}\n")
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(f"Storage: {result['storage']['backend']} · {result['storage']['path']}")
    if not result["analyses"]:
        print("No saved analyses")
        return
    for analysis in result["analyses"]:
        print(f"{analysis['id']}  {analysis['view'] or 'summary'}  {analysis['status']}  {analysis['name']}")
    print(f"Total: {result['total']}")


def _print_saved_analysis(analysis: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        return
    print(analysis["name"])
    print(f"ID: {analysis['id']} · {analysis['view'] or 'summary'} · {analysis['status']}")
    print(f"Model: {analysis.get('provider') or '-'} / {analysis.get('model') or '-'}")
    if analysis.get("prompt"):
        print(f"Prompt: {analysis['prompt']}")
    if analysis.get("error"):
        print(f"Error: {analysis['error']}")
    if analysis.get("summary"):
        print()
        print(analysis["summary"])
    for point in analysis.get("key_points") or []:
        print(f"- {point}")


def _analysis_main(arguments: List[str]) -> None:
    from transcripts.inventory import saved_analysis_inventory

    parser = argparse.ArgumentParser(prog="transcribe analysis", description="Read or delete a specific saved analysis.")
    parser.add_argument("--id", dest="job_id", required=True, help="Exact job ID")
    parser.add_argument("--analysis-id", required=True, help="Exact saved analysis ID")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Include the complete visualization as JSON")
    parser.add_argument("--delete", action="store_true", help="Delete only this analysis")
    args = parser.parse_args(arguments)
    try:
        if args.delete:
            storage = StateManager()._storage
            if not hasattr(storage, "delete_saved_analysis"):
                raise ValueError("Saved analyses require SQLite storage")
            if not storage.delete_saved_analysis(args.job_id, args.analysis_id):
                raise ValueError(f"Analysis not found for job {args.job_id}: {args.analysis_id}")
            print(json.dumps({"deleted": args.analysis_id}) if args.as_json else f"Deleted analysis {args.analysis_id}")
        else:
            result = saved_analysis_inventory(args.job_id, args.analysis_id)
            if args.as_json:
                print(json.dumps({"storage": result["storage"], "analysis": result["analyses"][0]}, indent=2, ensure_ascii=False))
            else:
                _print_saved_analysis(result["analyses"][0], False)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Could not access saved analysis: {error}\n")


def _analyze_main(arguments: List[str]) -> None:
    from transcripts.analyses import AnalysisConflictError, create_and_run_analysis

    parser = argparse.ArgumentParser(prog="transcribe analyze", description="Create a new saved summary and Timeline or Topics analysis. Existing versions are preserved.")
    parser.add_argument("--id", dest="job_id", required=True, help="Exact completed job ID")
    parser.add_argument("--view", choices=["timeline", "topics"], help="Visualization (required for a new analysis)")
    parser.add_argument("--name", help="Name of the saved analysis")
    prompt = parser.add_mutually_exclusive_group()
    prompt.add_argument("--prompt", help="Focus instructions that supplement the existing output format")
    prompt.add_argument("--prompt-file", help="Read focus instructions from a UTF-8 file")
    parser.add_argument("--provider", choices=["kimi", "fireworks"], help="Analysis inference provider")
    parser.add_argument("--model", help="Analysis inference model ID")
    parser.add_argument("--from-analysis", help="Create a new version using this analysis's saved settings, with optional overrides")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Print the complete saved result as JSON")
    args = parser.parse_args(arguments)
    if not args.view and not args.from_analysis:
        parser.error("--view is required unless --from-analysis is supplied")
    try:
        focus = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
        storage = StateManager()._storage
        if not hasattr(storage, "create_saved_analysis"):
            raise ValueError("Saved analyses require SQLite storage")
        previous = None
        if args.from_analysis:
            previous = storage.get_saved_analysis(args.job_id, args.from_analysis)
            if previous is None:
                raise ValueError(f"Analysis not found for job {args.job_id}: {args.from_analysis}")
        view = args.view or (previous.view if previous else None)
        if not view:
            raise ValueError("Choose --view timeline or topics for a legacy summary-only analysis")
        name = args.name if args.name is not None else previous.name if previous else f"{view.title()} analysis"
        provider = args.provider or (previous.provider if previous else None)
        model = args.model
        if model is None and previous and (args.provider is None or args.provider == previous.provider):
            model = previous.model
        if focus is None:
            focus = previous.prompt if previous else ""
        analysis = create_and_run_analysis(storage, args.job_id, name, view, focus, provider, model)
        _print_saved_analysis(analysis.to_dict(), args.as_json)
        if analysis.status.value == "failed":
            raise SystemExit(1)
    except KeyboardInterrupt:
        parser.exit(1, "Analysis interrupted\n")
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AnalysisConflictError) as error:
        parser.exit(1, f"Could not create saved analysis: {error}\n")


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
