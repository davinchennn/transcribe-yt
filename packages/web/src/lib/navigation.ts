import type { Passage, Transcript, Utterance, Word } from '../api/client';

export function formatTime(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}

export function youtubeVideoId(value: string): string | null {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    let id: string | null = null;
    if (host === 'youtu.be') id = url.pathname.split('/')[1];
    else if (['youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com'].includes(host)) {
      const parts = url.pathname.split('/');
      id = ['embed', 'shorts', 'live', 'v'].includes(parts[1]) ? parts[2] : url.searchParams.get('v');
    }
    return id && /^[\w-]{11}$/.test(id) ? id : null;
  } catch {
    return null;
  }
}

export function youtubeTimeUrl(url: string, milliseconds: number): string {
  const id = youtubeVideoId(url);
  if (!id) return url;
  return `https://www.youtube.com/watch?v=${id}&t=${Math.floor(Math.max(0, milliseconds) / 1000)}s`;
}

export function transcriptDuration(transcript: Transcript): number {
  return Math.max(
    (transcript.duration ?? 0) * 1000,
    transcript.utterances.at(-1)?.end ?? 0,
    transcript.words.at(-1)?.end ?? 0,
    1,
  );
}

export function segmentPosition(start: number, end: number, rangeStart: number, rangeEnd: number) {
  const duration = Math.max(1, rangeEnd - rangeStart);
  const clippedStart = Math.min(rangeEnd, Math.max(rangeStart, start));
  const clippedEnd = Math.min(rangeEnd, Math.max(clippedStart, end));
  return {
    left: `${((clippedStart - rangeStart) / duration) * 100}%`,
    width: `${((clippedEnd - clippedStart) / duration) * 100}%`,
  };
}

export function passageUtterances(transcript: Transcript, passage: Passage): Utterance[] {
  return transcript.utterances
    .slice(Math.max(0, passage.utterance_start), passage.utterance_end + 1)
    .filter((utterance) => utterance.end > passage.start && utterance.start < passage.end);
}

export function passageWords(words: Word[], start: number, end: number): Word[] {
  return words.filter((word) => word.start >= start && word.start < end);
}

export function selectedWords(transcript: Transcript, passage: Passage): Word[] {
  if (passage.word_start != null && passage.word_end != null) {
    return transcript.words.slice(passage.word_start, passage.word_end + 1);
  }
  return passageWords(transcript.words, passage.start, passage.end);
}

interface SeekablePlayer {
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  playVideo: () => void;
  pauseVideo: () => void;
}

export function seekMilliseconds(player: SeekablePlayer, milliseconds: number, wasPlaying: boolean) {
  player.seekTo(Math.max(0, milliseconds) / 1000, true);
  if (wasPlaying) player.playVideo();
  else player.pauseVideo();
}
