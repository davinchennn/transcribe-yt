import type { CSSProperties } from 'react';
import type { NavigationAnalysis, NavigationNode, Passage } from '../api/client';
import { formatTime, segmentPosition } from '../lib/navigation';

interface Props {
  analysis: NavigationAnalysis;
  duration: number;
  currentTime: number;
  selected: Passage | null;
  onSelect: (passage: Passage) => void;
  timelineSelection: string[];
  onTimelineSelectionChange: (ids: string[]) => void;
}

interface HierarchyEntry {
  node: NavigationNode;
  color: number;
  depth: number;
  titles: string[];
}

interface TopicBand {
  entries: HierarchyEntry[];
  start: number;
  end: number;
}

const colors = ['#818cf8', '#34d399', '#fb923c', '#f472b6', '#38bdf8', '#a78bfa'];
const colorStyle = (index: number) => ({ '--tile-color': colors[index % colors.length] }) as CSSProperties;
const containsTime = (passage: { start: number; end: number }, time: number) => time >= passage.start && time < passage.end;

function hierarchyEntries(nodes: NavigationNode[]): HierarchyEntry[] {
  const entries: HierarchyEntry[] = [];
  function visit(node: NavigationNode, depth: number, color: number, parentTitles: string[]) {
    const titles = [...parentTitles, node.title];
    entries.push({ node, depth, color, titles });
    node.children.forEach((child) => visit(child, depth + 1, color, titles));
  }
  nodes.forEach((node, color) => visit(node, 0, color, []));
  return entries;
}

function timelineMinimumWidth(bands: TopicBand[]): number {
  let width = 780;
  for (const { entries, start, end } of bands) {
    const range = Math.max(1, end - start);
    // Brief asides use the selected summary panel. They should not stretch an
    // otherwise readable timeline just to fit a few seconds of text.
    const minimumSpan = Math.min(30000, range / 8);
    for (const { node } of entries) {
      const span = Math.min(end, node.end) - Math.max(start, node.start);
      if (span >= minimumSpan) width = Math.max(width, 180 * range / span);
    }
  }
  return Math.ceil(Math.min(width, 6000));
}

function TimeAxis({ duration, start = 0, end = duration }: { duration: number; start?: number; end?: number }) {
  return <div className="time-axis" aria-hidden="true">
    {Array.from({ length: 5 }, (_, index) => <span key={index}>{formatTime(start + (end - start) * index / 4)}</span>)}
  </div>;
}

function Playhead({ time, duration, start = 0, end = duration }: { time: number; duration: number; start?: number; end?: number }) {
  if (time < start || time > end) return null;
  return <span className="nav-playhead" style={{ left: `${(time - start) / Math.max(1, end - start) * 100}%` }} aria-hidden="true" />;
}

function TimelineTopicBand({ entries, depth, duration, currentTime, start = 0, end = duration, parentTitle, selectedId, onTopicSelect, onPassageSelect, selectedPassageId }: {
  entries: HierarchyEntry[]; depth: number; duration: number; currentTime: number;
  start?: number; end?: number; parentTitle?: string; selectedId?: string;
  onTopicSelect?: (entry: HierarchyEntry) => void;
  onPassageSelect?: (passage: Passage) => void;
  selectedPassageId?: string;
}) {
  if (entries.length === 0) return null;
  return <div className="timeline-band" data-depth={depth}>
    <span className="band-label">{depth === 0 ? 'Chapters' : depth === 1 ? 'Subtopics · select a topic' : `Level ${depth + 1} · ${parentTitle}`} {depth >= 2 && `· ${formatTime(start)}–${formatTime(end)}`}</span>
    {depth >= 2 && <TimeAxis duration={duration} start={start} end={end} />}
    <div className={`timeline-track ${depth >= 1 ? 'subtopic-track' : ''}`}>
      {entries.map((entry) => {
        const { node, color, titles } = entry;
        const chosen = selectedId === node.id;
        const className = `timeline-tile topic-tile ${containsTime(node, currentTime) ? 'is-current' : ''} ${onTopicSelect ? 'is-selectable' : ''} ${chosen ? 'is-chosen' : ''}`;
        const style = { ...segmentPosition(node.start, node.end, start, end), ...colorStyle(color) };
        const title = `${titles.join(' / ')} · ${formatTime(node.start)}–${formatTime(node.end)}${node.summary ? ` · ${node.summary}` : ''}`;
        const hasChapterPassages = depth === 0 && node.children.length === 0 && node.occurrences.length > 0 && !!onPassageSelect;
        const content = <span className={`timeline-tile-content ${hasChapterPassages ? 'has-chapter-passages' : ''}`}>
          <span className="tile-time">{formatTime(node.start)}–{formatTime(node.end)}</span>
          <strong>{node.title}</strong>
          {depth >= 1 && node.summary && <span className="subtopic-summary">{node.summary}</span>}
          <span className="tile-kind">{node.children.length > 0 ? `${node.children.length} subtopics` : `${node.occurrences.length} passage${node.occurrences.length === 1 ? '' : 's'}`}{onTopicSelect && <span className="tile-selection-label">{chosen ? '✓ Selected' : 'Select ↓'}</span>}</span>
          {depth === 0 && node.children.length === 0 && onPassageSelect && <span className="chapter-passage-links">
            {node.occurrences.map((passage) => <button key={passage.id} type="button"
              className={`chapter-passage-link ${selectedPassageId === passage.id ? 'is-selected' : ''}`}
              title={passage.text} aria-label={`Go to ${node.title} passage at ${formatTime(passage.start)}`}
              onClick={() => onPassageSelect(passage)}>{formatTime(passage.start)} ↗</button>)}
          </span>}
        </span>;
        return onTopicSelect ? <button key={node.id} className={className} style={style} title={title}
          aria-label={`Select ${node.title}, ${formatTime(node.start)} to ${formatTime(node.end)}`}
          aria-pressed={chosen} onClick={() => onTopicSelect(entry)}>{content}</button>
          : <div key={node.id} className={className} style={style} title={title}>{content}</div>;
      })}
      <Playhead time={currentTime} duration={duration} start={start} end={end} />
    </div>
  </div>;
}

function TimelineBands({ analysis, duration, currentTime, selected, onSelect, timelineSelection, onTimelineSelectionChange }: Props) {
  const entries = hierarchyEntries(analysis.nodes);
  const chapters = entries.filter((entry) => entry.depth === 0);
  const subtopics = entries.filter((entry) => entry.depth === 1);
  const entryById = new Map(entries.map((entry) => [entry.node.id, entry]));
  const chosen: HierarchyEntry[] = [];
  let candidates = subtopics;
  // Only keep the valid prefix. IDs from old analyses or unrelated branches
  // must never expose children under the wrong parent.
  for (const id of timelineSelection) {
    const entry = candidates.find((candidate) => candidate.node.id === id);
    if (!entry) break;
    chosen.push(entry);
    candidates = entry.node.children.flatMap((child) => {
      const childEntry = entryById.get(child.id);
      return childEntry ? [childEntry] : [];
    });
  }
  const chooseTopic = (entry: HierarchyEntry, index: number) => {
    if (chosen[index]?.node.id === entry.node.id) return;
    onTimelineSelectionChange([...chosen.slice(0, index).map((item) => item.node.id), entry.node.id]);
  };
  const deepest = chosen.at(-1);
  const childBands = chosen.map((parent) => ({
    parent,
    start: parent.node.start,
    end: parent.node.end,
    entries: parent.node.children.flatMap((child) => {
      const entry = entryById.get(child.id);
      return entry ? [entry] : [];
    }),
  }));
  const minimumWidth = timelineMinimumWidth([{ entries: subtopics, start: 0, end: duration }, ...childBands]);
  const passageStart = deepest?.node.start ?? 0;
  const passageEnd = deepest?.node.end ?? duration;
  const passageEntries = deepest ? [deepest] : entries.filter(({ node, depth }) => depth <= 1 && node.children.length === 0);
  const passages = passageEntries.flatMap((entry) => entry.node.occurrences.map((passage) => ({ entry, passage })))
    .sort((a, b) => a.passage.start - b.passage.start);

  return <>
    {chosen.length > 0 && <section className="selected-topic-summaries" aria-label="Selected subtopic summaries">
      <span className="section-eyebrow">Selected subtopics</span>
      {chosen.map(({ node, color, titles }) => <article className="selected-topic-summary" key={node.id} style={colorStyle(color)}>
        <div className="selected-topic-summary-heading">
          <h4>{titles.slice(1).join(' / ')}</h4>
          <span className="tile-time">{formatTime(node.start)}–{formatTime(node.end)}</span>
        </div>
        {node.summary && <p>{node.summary}</p>}
      </article>)}
    </section>}
    <div className="timeline-scroll" role="region" aria-label="Complete chronological hierarchy" tabIndex={0}>
    <div className="timeline-content" style={{ minWidth: minimumWidth }}>
      <TimeAxis duration={duration} />
      <TimelineTopicBand entries={chapters} depth={0} duration={duration} currentTime={currentTime} onPassageSelect={onSelect} selectedPassageId={selected?.id} />
      <TimelineTopicBand entries={subtopics} depth={1} duration={duration} currentTime={currentTime} selectedId={chosen[0]?.node.id} onTopicSelect={(entry) => chooseTopic(entry, 0)} />
      {childBands.map(({ parent, entries, start, end }, index) => <TimelineTopicBand key={parent.node.id} entries={entries} depth={index + 2} duration={duration} currentTime={currentTime}
        start={start} end={end} parentTitle={parent.node.title}
        selectedId={chosen[index + 1]?.node.id} onTopicSelect={(entry) => chooseTopic(entry, index + 1)} />)}
      <p className="timeline-selection-guidance" role="status">
        {!deepest ? subtopics.length > 0 ? 'Select a subtopic to reveal its next level. Chapters and subtopics remain visible; playback stays where it is.' : 'These chapters have no deeper subtopics. Select a timed passage below to seek.'
          : deepest.node.children.length === 0 ? `${deepest.node.title} has no deeper subtopics. Select a passage below to seek.`
          : `Select a topic within ${deepest.node.title} to reveal the next level. Earlier rows stay visible.`}
      </p>
      {passages.length > 0 && <div className="timeline-band">
        <span className="band-label">Passages{deepest ? ` · ${deepest.node.title}` : ''} · click to seek</span>
        {deepest && <TimeAxis duration={duration} start={passageStart} end={passageEnd} />}
        <div className="timeline-track passage-track">
          {passages.map(({ entry, passage }) => <button key={`${entry.node.id}-${passage.id}`}
            className={`timeline-tile passage-tile ${selected?.id === passage.id ? 'is-selected' : ''} ${containsTime(passage, currentTime) ? 'is-current' : ''}`}
            style={{ ...segmentPosition(passage.start, passage.end, passageStart, passageEnd), ...colorStyle(entry.color) }}
            onClick={() => onSelect(passage)}
            title={`${entry.titles.join(' / ')} · ${formatTime(passage.start)}–${formatTime(passage.end)} · ${passage.text}`}
            aria-label={`Go to ${entry.node.title} passage at ${formatTime(passage.start)}: ${passage.text}`}>
            <span className="timeline-tile-content">
              <span className="tile-time">{formatTime(passage.start)}–{formatTime(passage.end)}</span>
              <span className="passage-excerpt">{passage.text}</span>
              <span className="tile-action">Seek ↗</span>
            </span>
          </button>)}
          <Playhead time={currentTime} duration={duration} start={passageStart} end={passageEnd} />
        </div>
      </div>}
    </div>
    </div>
  </>;
}

function TopicTracks({ analysis, duration, currentTime, selected, onSelect }: Props) {
  const entries = hierarchyEntries(analysis.nodes);
  return <div className="topics-scroll" role="region" aria-label="Complete recurring topic hierarchy" tabIndex={0}>
    <div className="topics-content">
      <div className="topic-track-header"><span>Subject / subtopic</span><TimeAxis duration={duration} /></div>
      {entries.map(({ node, depth, color, titles }) => <div className={`topic-row ${depth === 0 ? 'is-root' : ''}`} key={node.id} style={colorStyle(color)} data-depth={depth}>
        <div className="topic-label" style={{ paddingLeft: `${depth * 18}px` }} title={`${titles.join(' / ')}${node.summary ? ` · ${node.summary}` : ''}`}>
          <strong>{depth > 0 && <span className="topic-branch-mark" aria-hidden="true">↳ </span>}{node.title}</strong>
          {depth >= 1 && node.summary && <p className="subtopic-summary">{node.summary}</p>}
          <span>{node.occurrences.length} passage{node.occurrences.length === 1 ? '' : 's'}</span>
        </div>
        <div className="topic-track">
          {node.occurrences.map((passage) => <button key={passage.id}
            className={`topic-occurrence ${selected?.id === passage.id ? 'is-selected' : ''} ${containsTime(passage, currentTime) ? 'is-current' : ''}`}
            style={segmentPosition(passage.start, passage.end, 0, duration)}
            title={`${titles.join(' / ')} · ${formatTime(passage.start)}–${formatTime(passage.end)} · ${passage.text}`}
            aria-label={`Go to ${node.title} passage at ${formatTime(passage.start)}`}
            onClick={() => onSelect(passage)}><span>{formatTime(passage.start)}</span></button>)}
          <Playhead time={currentTime} duration={duration} />
        </div>
      </div>)}
    </div>
  </div>;
}

export function NavigationCanvas(props: Props) {
  const { analysis, currentTime } = props;
  return <div className="navigation-canvas">
    <div className="navigation-caption">
      <div>
        <h3>{analysis.view === 'timeline' ? 'How the discussion unfolds' : 'Subjects across the video'}</h3>
        <p>{analysis.summary ?? (analysis.view === 'timeline' ? 'Chapters and subtopics stay visible. Select a subtopic to reveal its next level.' : 'All subjects, subtopics, and their occurrences across the video.')}</p>
      </div>
      <span className="playback-clock" title="Current video time">{formatTime(currentTime)}</span>
    </div>
    {analysis.view === 'timeline' ? <TimelineBands {...props} /> : <TopicTracks {...props} />}
    {analysis.nodes.length === 0 && <p className="nav-empty">No topics were found in this transcript.</p>}
    <p className="navigation-hint">{analysis.view === 'timeline' ? 'Scroll horizontally to explore the timeline. Topic selection reveals children and the full summary without moving playback. Passage tiles seek the video.' : 'All hierarchy levels stay visible. Passage markers seek the video.'} The vertical line follows playback.</p>
  </div>;
}
