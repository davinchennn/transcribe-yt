import assert from 'node:assert/strict';
import test from 'node:test';
import { getVideoUrl } from '../src/api/client.ts';
import { connectNativeVideo, isXVideoUrl, nativeVideoError } from '../src/lib/video.ts';

class FakeVideo extends EventTarget {
  currentTime = 0;
  duration = 120;
  readyState = 1;
  paused = true;
}

test('X video routing accepts post and selected-video URLs on supported hosts', () => {
  for (const host of ['x.com', 'twitter.com', 'www.x.com', 'mobile.twitter.com', 'm.x.com']) {
    for (const path of ['/user/status/123', '/i/web/status/123', '/statuses/123/video/2', '/user/status/123/video/1/']) {
      assert.equal(isXVideoUrl(`https://${host}${path}?s=20`), true);
    }
  }
  for (const url of ['https://x.com.evil.test/user/status/123', 'https://youtube.com/watch?v=dQw4w9WgXcQ', 'https://x.com/user', 'https://x.com/user/status/123/video/0', 'https://x.com/user/status/123/photo/1', 'https://x.com/user/status/123/video/2/extra', 'file://x.com/user/status/123', 'bad-url']) {
    assert.equal(isXVideoUrl(url), false);
  }
});

test('saved video URLs address the job and encode source IDs safely', () => {
  assert.equal(getVideoUrl('x-123-video-2'), '/api/jobs/x-123-video-2/video');
  assert.equal(getVideoUrl('a/b ?'), '/api/jobs/a%2Fb%20%3F/video');
});

test('native passage seeks convert milliseconds, clamp the target and preserve playback state', () => {
  const video = new FakeVideo();
  const reported = [];
  const controller = connectNativeVideo(video, (time) => reported.push(time));
  controller.seek(12345);
  assert.equal(video.currentTime, 12.345);
  assert.equal(video.paused, true);
  video.paused = false;
  controller.seek(45000);
  assert.equal(video.currentTime, 45);
  assert.equal(video.paused, false);
  controller.seek(-1000);
  assert.equal(video.currentTime, 0);
  controller.seek(200000);
  assert.equal(video.currentTime, 120);
  controller.seek(Number.NaN);
  assert.equal(video.currentTime, 120);
  assert.deepEqual(reported, [12345, 45000, 0, 120000]);
  controller.dispose();
});

test('only the latest passage selected before metadata loads is applied', () => {
  const video = new FakeVideo();
  video.readyState = 0;
  video.duration = Number.NaN;
  const reported = [];
  const controller = connectNativeVideo(video, (time) => reported.push(time));
  controller.seek(10000);
  controller.seek(27000);
  assert.equal(video.currentTime, 0);
  assert.deepEqual(reported, []);
  video.readyState = 1;
  video.duration = 120;
  video.dispatchEvent(new Event('loadedmetadata'));
  assert.equal(video.currentTime, 27);
  assert.equal(video.paused, true);
  assert.deepEqual(reported, [27000]);
  controller.dispose();
});

test('native playback reports progress in milliseconds and disposed players cannot affect a new job', () => {
  const firstVideo = new FakeVideo();
  const firstTimes = [];
  const first = connectNativeVideo(firstVideo, (time) => firstTimes.push(time));
  firstVideo.currentTime = 12.5;
  firstVideo.dispatchEvent(new Event('timeupdate'));
  firstVideo.currentTime = 15;
  firstVideo.dispatchEvent(new Event('seeked'));
  first.dispose();
  first.seek(90000);
  firstVideo.dispatchEvent(new Event('timeupdate'));
  assert.deepEqual(firstTimes, [12500, 15000]);
  assert.equal(firstVideo.currentTime, 15);
  const nextVideo = new FakeVideo();
  const nextTimes = [];
  const next = connectNativeVideo(nextVideo, (time) => nextTimes.push(time));
  nextVideo.dispatchEvent(new Event('loadedmetadata'));
  assert.deepEqual(nextTimes, [0]);
  next.dispose();
});

test('unsupported codecs and unavailable files keep the transcript accessible', () => {
  assert.match(nativeVideoError(3), /could not decode/);
  assert.match(nativeVideoError(4), /unavailable or uses a format/);
  assert.match(nativeVideoError(2), /connection failed/);
  for (const code of [1, 2, 3, 4, undefined]) assert.match(nativeVideoError(code), /transcript is still available/);
});
