import assert from 'node:assert/strict';
import test from 'node:test';
import { formatTime, passageUtterances, passageWords, segmentPosition, selectedWords, seekMilliseconds, transcriptDuration, youtubeTimeUrl, youtubeVideoId } from '../src/lib/navigation.ts';

test('timestamps use milliseconds and support hour-long videos', () => {
  assert.equal(formatTime(61000), '1:01');
  assert.equal(formatTime(3661000), '1:01:01');
  assert.equal(formatTime(-1000), '0:00');
});

test('YouTube IDs support watch, short, mobile, live and embed URLs and reject lookalike hosts', () => {
  const id = 'dQw4w9WgXcQ';
  for (const url of [`https://youtube.com/watch?v=${id}`, `https://youtu.be/${id}`, `https://m.youtube.com/watch?v=${id}`, `https://youtube.com/shorts/${id}`, `https://youtube.com/live/${id}`, `https://youtube-nocookie.com/embed/${id}`]) assert.equal(youtubeVideoId(url), id);
  assert.equal(youtubeVideoId(`https://youtube.com.evil.example/watch?v=${id}`), null);
  assert.equal(youtubeVideoId('https://youtube.com/watch?v=invalid'), null);
  assert.equal(youtubeTimeUrl(`https://youtu.be/${id}`, 123456), `https://www.youtube.com/watch?v=${id}&t=123s`);
});

test('timeline duration and clipped geometry keep seconds distinct from source milliseconds', () => {
  assert.equal(transcriptDuration({ duration: 120, utterances: [{ end: 119000 }], words: [] }), 120000);
  assert.equal(transcriptDuration({ duration: null, utterances: [], words: [{ end: 3000 }] }), 3000);
  assert.deepEqual(segmentPosition(0, 8000, 5000, 15000), { left: '0%', width: '30%' });
  assert.deepEqual(segmentPosition(12000, 20000, 5000, 15000), { left: '70%', width: '30%' });
});

test('a selected passage contains only its source range, with inclusive source indices', () => {
  const utterances = [{ start: 0, end: 1000 }, { start: 1000, end: 2000 }, { start: 2000, end: 3000 }];
  const words = [{ start: 1000, end: 1400 }, { start: 1400, end: 1500 }, { start: 1500, end: 1800 }, { start: 2000, end: 2100 }];
  const passage = { start: 1000, end: 2000, utterance_start: 1, utterance_end: 1 };
  assert.deepEqual(passageUtterances({ utterances }, passage), [utterances[1]]);
  assert.deepEqual(passageWords(words, 1000, 1500), words.slice(0, 2));
  assert.deepEqual(selectedWords({ words }, { ...passage, word_start: 1, word_end: 2 }), words.slice(1, 3));
  assert.deepEqual(selectedWords({ words }, passage), words.slice(0, 3));
});

test('seek converts milliseconds to seconds and preserves playback intent', () => {
  const calls = [];
  const player = { seekTo: (...args) => calls.push(['seek', ...args]), playVideo: () => calls.push(['play']), pauseVideo: () => calls.push(['pause']) };
  seekMilliseconds(player, 12345, false);
  seekMilliseconds(player, 45000, true);
  assert.deepEqual(calls, [['seek', 12.345, true], ['pause'], ['seek', 45, true], ['play']]);
});
