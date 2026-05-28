import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PitchShifter } from 'soundtouchjs';
import {
  fetchAlbumTracks,
  fetchArtistTracks,
  fetchTrackWaveform,
  resolveLibraryId,
} from '../../../../api/library';
import { EQ_BANDS, readSpectrumLevels } from '../audioAnalysis';
import { isVideoItem } from '../../../media/mediaItem';

function normalizeQueueItems(items = []) {
  return items.filter(Boolean);
}

function readStoredQueueState() {
  try {
    const payload = JSON.parse(window.localStorage.getItem('triver.audioPlayer.queue') || '{}');
    return {
      queue: normalizeQueueItems(payload.queue || []),
      queueIndex: Number.isInteger(payload.queueIndex) ? payload.queueIndex : -1,
      wasPlaying: Boolean(payload.wasPlaying),
    };
  } catch (_error) {
    return { queue: [], queueIndex: -1, wasPlaying: false };
  }
}

export default function useAudioPlayer() {
  const audioRef = useRef(null);
  const audioGraphRef = useRef(null);
  const sourceRequestRef = useRef(0);
  const pitchEngineRef = useRef({
    context: null,
    gainNode: null,
    shifter: null,
    connected: false,
    trackId: null,
    buffer: null,
    bufferCache: new Map(),
    unsubscribeProgress: null,
  });
  const pitchPlaybackStateRef = useRef({
    currentTime: 0,
    isPlaying: false,
    playbackSpeed: 1,
    pitchSemitones: 0,
    volume: 1,
  });
  const pitchRequestRef = useRef(0);
  const storedQueueStateRef = useRef(null);
  const selectionRangeRef = useRef(null);
  if (storedQueueStateRef.current === null) {
    storedQueueStateRef.current = readStoredQueueState();
  }
  const [libraryId, setLibraryId] = useState(null);
  const [queue, setQueue] = useState(() => storedQueueStateRef.current.queue);
  const [queueIndex, setQueueIndex] = useState(() => storedQueueStateRef.current.queueIndex);
  const [isPlaying, setIsPlaying] = useState(() => storedQueueStateRef.current.wasPlaying);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [loopMode, setLoopMode] = useState('none');
  const [shuffleEnabled, setShuffleEnabled] = useState(false);
  const [selectionRange, setSelectionRange] = useState(null);
  const [visualMode, setVisualMode] = useState('waveform');
  const [cursorLockEnabled, setCursorLockEnabled] = useState(true);
  const [eqPanelOpen, setEqPanelOpen] = useState(false);
  const [eqGains, setEqGains] = useState(() => EQ_BANDS.map(() => 0));
  const [spectrumLevels, setSpectrumLevels] = useState(() => EQ_BANDS.map(() => 0));
  const [speedPanelOpen, setSpeedPanelOpen] = useState(false);
  const [pitchPanelOpen, setPitchPanelOpen] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [pitchSemitones, setPitchSemitones] = useState(0);
  const [waveformBars, setWaveformBars] = useState([]);
  const [waveformTrackId, setWaveformTrackId] = useState(null);
  const [waveformLoading, setWaveformLoading] = useState(false);
  const [waveformZoom, setWaveformZoom] = useState(1);

  const currentTrack = queueIndex >= 0 ? queue[queueIndex] || null : null;
  const currentTrackIsVideo = isVideoItem(currentTrack);
  const pitchEngineActive = Math.abs(pitchSemitones) > 0.001;

  useEffect(() => {
    pitchPlaybackStateRef.current = {
      currentTime,
      isPlaying,
      playbackSpeed,
      pitchSemitones,
      volume,
    };
  }, [currentTime, isPlaying, playbackSpeed, pitchSemitones, volume]);

  const teardownPitchEngine = useCallback(() => {
    const engine = pitchEngineRef.current;
    if (engine.connected && engine.shifter) {
      try {
        engine.shifter.disconnect();
      } catch (_error) {}
    }
    try {
      engine.unsubscribeProgress?.();
    } catch (_error) {}
    try {
      engine.shifter?.off?.();
    } catch (_error) {}
    engine.unsubscribeProgress = null;
    engine.shifter = null;
    engine.connected = false;
    engine.trackId = null;
    engine.buffer = null;
  }, []);

  const ensurePitchContext = useCallback(() => {
    const engine = pitchEngineRef.current;
    if (engine.context && engine.gainNode) {
      return engine;
    }
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) {
      return null;
    }
    const context = engine.context || new AudioContextCtor();
    const gainNode = engine.gainNode || context.createGain();
    gainNode.gain.value = volume;
    try {
      gainNode.connect(context.destination);
    } catch (_error) {
      // Already connected.
    }
    engine.context = context;
    engine.gainNode = gainNode;
    return engine;
  }, [volume]);

  const ensurePitchBuffer = useCallback(async (track) => {
    if (!track?.id || !track.stream_url) {
      return null;
    }
    const engine = ensurePitchContext();
    if (!engine?.context) {
      return null;
    }
    if (engine.bufferCache.has(track.id)) {
      return engine.bufferCache.get(track.id);
    }
    const response = await fetch(new URL(track.stream_url, window.location.origin).href, {
      credentials: 'same-origin',
    });
    if (!response.ok) {
      throw new Error(`Unable to fetch track audio (${response.status})`);
    }
    const arrayBuffer = await response.arrayBuffer();
    const audioBuffer = await engine.context.decodeAudioData(arrayBuffer.slice(0));
    engine.bufferCache.set(track.id, audioBuffer);
    return audioBuffer;
  }, [ensurePitchContext]);

  const syncPitchEngineParams = useCallback(() => {
    const engine = pitchEngineRef.current;
    if (engine.gainNode) {
      engine.gainNode.gain.value = volume;
    }
    if (engine.shifter) {
      engine.shifter.pitchSemitones = pitchSemitones;
      engine.shifter.tempo = playbackSpeed;
    }
  }, [pitchSemitones, playbackSpeed, volume]);

  const advanceQueueAfterTrackEnd = useCallback(() => {
    setQueueIndex((current) => {
      const audio = audioRef.current;
      const engine = pitchEngineRef.current;
      if (loopMode === 'track') {
        if (pitchEngineActive && engine.shifter) {
          const sourceDuration = engine.shifter.duration || currentTrack?.duration_seconds || 0;
          const restartTime = selectionRangeRef.current
            ? Math.min(selectionRangeRef.current.start, selectionRangeRef.current.end)
            : 0;
          engine.shifter.percentagePlayed = sourceDuration > 0 ? restartTime / sourceDuration : 0;
          setCurrentTime(restartTime);
          if (isPlaying) {
            engine.context?.resume?.().catch?.(() => {});
            if (!engine.connected) {
              engine.shifter.connect(engine.gainNode);
              engine.connected = true;
            }
          }
        } else if (audio) {
          audio.currentTime = 0;
          audio.play().then(() => setIsPlaying(true)).catch(() => {});
        }
        return current;
      }
      const hasNext = current + 1 < queue.length;
      if (hasNext) {
        setIsPlaying(true);
        return current + 1;
      }
      if (loopMode === 'queue' && queue.length) {
        setIsPlaying(true);
        return 0;
      }
      setIsPlaying(false);
      return current;
    });
  }, [currentTrack?.duration_seconds, isPlaying, loopMode, pitchEngineActive, queue.length]);

  const ensureAudioGraph = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || audioGraphRef.current) {
      return audioGraphRef.current;
    }

    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) {
      return null;
    }

    try {
      const context = new AudioContextCtor();
      const source = context.createMediaElementSource(audio);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.84;
      const filters = EQ_BANDS.map((band, index) => {
        const filter = context.createBiquadFilter();
        filter.type = 'peaking';
        filter.frequency.value = band.frequency;
        filter.Q.value = 1.1;
        filter.gain.value = Number(eqGains[index]) || 0;
        return filter;
      });

      let previousNode = source;
      filters.forEach((filter) => {
        previousNode.connect(filter);
        previousNode = filter;
      });
      const visualizerNode = previousNode;
      visualizerNode.connect(analyser);
      analyser.connect(context.destination);

      audioGraphRef.current = {
        context,
        source,
        analyser,
        visualizerNode,
        filters,
        frequencyData: new Uint8Array(analyser.frequencyBinCount),
      };
      return audioGraphRef.current;
    } catch (_error) {
      audioGraphRef.current = null;
      return null;
    }
  }, [eqGains]);

  const requestVisualizerAudioInput = useCallback(() => {
    if (pitchEngineActive) {
      const engine = ensurePitchContext();
      if (!engine?.context || !engine?.gainNode) {
        return null;
      }
      engine.context.resume?.().catch?.(() => {});
      return {
        context: engine.context,
        node: engine.gainNode,
      };
    }

    const graph = ensureAudioGraph();
    const node = graph?.visualizerNode || graph?.analyser;
    if (!graph?.context || !node) {
      return null;
    }
    graph.context.resume?.().catch?.(() => {});
    return {
      context: graph.context,
      node,
    };
  }, [ensureAudioGraph, ensurePitchContext, pitchEngineActive]);

  useEffect(() => {
    const graph = audioGraphRef.current;
    if (!graph) {
      return;
    }
    graph.filters.forEach((filter, index) => {
      filter.gain.value = Number(eqGains[index]) || 0;
    });
  }, [eqGains]);

  useEffect(() => {
    const graph = ensureAudioGraph();
    if (!graph || !isPlaying) {
      return;
    }
    graph.context?.resume?.().catch?.(() => {});
  }, [ensureAudioGraph, isPlaying]);

  useEffect(() => {
    const graph = ensureAudioGraph();
    if (!graph || (!isPlaying && !eqPanelOpen && visualMode !== 'spectrum')) {
      setSpectrumLevels(EQ_BANDS.map(() => 0));
      return undefined;
    }

    let frameId = 0;
    function tick() {
      setSpectrumLevels(readSpectrumLevels(graph.analyser, graph.frequencyData));
      frameId = window.requestAnimationFrame(tick);
    }

    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [ensureAudioGraph, eqPanelOpen, isPlaying, visualMode]);

  useEffect(() => {
    selectionRangeRef.current = selectionRange;
  }, [selectionRange]);

  useEffect(() => {
    try {
      window.localStorage.setItem('triver.audioPlayer.queue', JSON.stringify({
        queue,
        queueIndex,
        wasPlaying: isPlaying,
      }));
    } catch (_error) {
      // Local storage can be unavailable in hardened/private contexts.
    }
  }, [isPlaying, queue, queueIndex]);

  useEffect(() => {
    let mounted = true;
    resolveLibraryId()
      .then((nextLibraryId) => {
        if (mounted) {
          setLibraryId(nextLibraryId);
        }
      })
      .catch(() => {
        if (mounted) {
          setLibraryId(null);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || pitchEngineActive) {
      return undefined;
    }

    function onTimeUpdate() {
      const nextTime = audio.currentTime || 0;
      const currentSelectionRange = selectionRangeRef.current;
      if (currentSelectionRange) {
        const selectionStart = Math.min(currentSelectionRange.start, currentSelectionRange.end);
        const selectionEnd = Math.max(currentSelectionRange.start, currentSelectionRange.end);
        if (selectionEnd - selectionStart >= 0.05 && nextTime >= selectionEnd) {
          audio.currentTime = selectionStart;
          setCurrentTime(selectionStart);
          return;
        }
      }
      setCurrentTime(nextTime);
    }

    function onLoadedMetadata() {
      setDuration(audio.duration || currentTrack?.duration_seconds || 0);
    }

    function onEnded() {
      advanceQueueAfterTrackEnd();
    }

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    audio.addEventListener('ended', onEnded);
    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
      audio.removeEventListener('ended', onEnded);
    };
  }, [advanceQueueAfterTrackEnd, currentTrack?.duration_seconds, pitchEngineActive]);

  useEffect(() => {
    if (pitchEngineActive || !isPlaying) {
      return undefined;
    }
    const audio = audioRef.current;
    if (!audio) {
      return undefined;
    }

    let frameId = 0;
    function enforceSelectionLoop() {
      const currentSelectionRange = selectionRangeRef.current;
      if (currentSelectionRange) {
        const selectionStart = Math.min(currentSelectionRange.start, currentSelectionRange.end);
        const selectionEnd = Math.max(currentSelectionRange.start, currentSelectionRange.end);
        if (selectionEnd - selectionStart >= 0.05 && audio.currentTime >= selectionEnd) {
          audio.currentTime = selectionStart;
          setCurrentTime(selectionStart);
        }
      }
      frameId = window.requestAnimationFrame(enforceSelectionLoop);
    }

    frameId = window.requestAnimationFrame(enforceSelectionLoop);
    return () => window.cancelAnimationFrame(frameId);
  }, [isPlaying, pitchEngineActive]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    audio.volume = volume;
  }, [volume]);

  useEffect(() => {
    if (pitchEngineActive) {
      syncPitchEngineParams();
      return;
    }
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    const pitchMultiplier = 2 ** (pitchSemitones / 12);
    const nextPlaybackRate = Math.max(0.25, Math.min(4, playbackSpeed * pitchMultiplier));
    audio.playbackRate = nextPlaybackRate;
    audio.preservesPitch = pitchSemitones === 0;
    audio.mozPreservesPitch = pitchSemitones === 0;
    audio.webkitPreservesPitch = pitchSemitones === 0;
  }, [pitchEngineActive, pitchSemitones, playbackSpeed, syncPitchEngineParams]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }

    let cancelled = false;
    const requestId = sourceRequestRef.current + 1;
    sourceRequestRef.current = requestId;

    if (!currentTrack?.stream_url || currentTrackIsVideo) {
      audio.pause();
      audio.removeAttribute('src');
      delete audio.dataset.trackId;
      setCurrentTime(0);
      setDuration(0);
      return () => {
        cancelled = true;
      };
    }

    if (pitchEngineActive) {
      audio.pause();
      return () => {
        cancelled = true;
      };
    }

    const nextSrc = new URL(currentTrack.stream_url, window.location.origin).href;
    const sourceChanged = (
      audio.dataset.trackId !== String(currentTrack.id)
      || audio.currentSrc !== nextSrc
    );

    const attemptPlay = () => {
      if (cancelled || sourceRequestRef.current !== requestId || !isPlaying) {
        return;
      }
      audio.play().catch((error) => {
        if (!cancelled && sourceRequestRef.current === requestId && error?.name === 'NotAllowedError') {
          setIsPlaying(false);
        }
      });
    };

    if (sourceChanged) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      audio.src = nextSrc;
      audio.dataset.trackId = String(currentTrack.id);
      audio.load();
      audio.currentTime = 0;
      setCurrentTime(0);
      setDuration(currentTrack.duration_seconds || 0);
    } else if (Math.abs((audio.currentTime || 0) - currentTime) > 0.35) {
      try {
        audio.currentTime = currentTime;
      } catch (_error) {
        // Media element may not be seekable yet.
      }
    }

    if (isPlaying) {
      if (!sourceChanged && audio.readyState >= 1) {
        attemptPlay();
      } else {
        audio.addEventListener('loadedmetadata', attemptPlay, { once: true });
        audio.addEventListener('canplay', attemptPlay, { once: true });
      }
    } else if (!sourceChanged) {
      audio.pause();
    }

    return () => {
      cancelled = true;
      audio.removeEventListener('loadedmetadata', attemptPlay);
      audio.removeEventListener('canplay', attemptPlay);
    };
  }, [currentTime, currentTrack, currentTrackIsVideo, isPlaying, pitchEngineActive]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!pitchEngineActive) {
      teardownPitchEngine();
      return undefined;
    }

    if (!currentTrack?.stream_url || currentTrackIsVideo) {
      teardownPitchEngine();
      setCurrentTime(0);
      setDuration(0);
      return undefined;
    }

    if (audio) {
      audio.pause();
    }

    let cancelled = false;
    const requestId = pitchRequestRef.current + 1;
    pitchRequestRef.current = requestId;

    async function preparePitchEngine() {
      try {
        const engine = ensurePitchContext();
        if (!engine?.context) {
          return;
        }
        const audioBuffer = await ensurePitchBuffer(currentTrack);
        if (cancelled || pitchRequestRef.current !== requestId || !audioBuffer) {
          return;
        }

        teardownPitchEngine();

        const shifter = new PitchShifter(engine.context, audioBuffer, 2048, () => {
          if (pitchRequestRef.current === requestId) {
            advanceQueueAfterTrackEnd();
          }
        });

        const latestPlaybackState = pitchPlaybackStateRef.current;
        shifter.pitchSemitones = latestPlaybackState.pitchSemitones;
        shifter.tempo = latestPlaybackState.playbackSpeed;

        const handleProgress = ({ timePlayed }) => {
          if (pitchRequestRef.current !== requestId) {
            return;
          }
          const nextTime = Number(timePlayed) || 0;
          const currentSelectionRange = selectionRangeRef.current;
          if (currentSelectionRange) {
            const selectionStart = Math.min(currentSelectionRange.start, currentSelectionRange.end);
            const selectionEnd = Math.max(currentSelectionRange.start, currentSelectionRange.end);
            if (selectionEnd - selectionStart >= 0.05 && nextTime >= selectionEnd) {
              shifter.percentagePlayed = audioBuffer.duration > 0 ? selectionStart / audioBuffer.duration : 0;
              setCurrentTime(selectionStart);
              return;
            }
          }
          setCurrentTime(nextTime);
        };

        shifter.on('play', handleProgress);

        engine.shifter = shifter;
        engine.trackId = currentTrack.id;
        engine.buffer = audioBuffer;
        engine.connected = false;
        engine.unsubscribeProgress = () => {
          try {
            shifter.off('play');
          } catch (_error) {}
        };
        engine.gainNode.gain.value = latestPlaybackState.volume;

        const seekTime = Math.max(0, Math.min(latestPlaybackState.currentTime || 0, audioBuffer.duration || 0));
        shifter.percentagePlayed = audioBuffer.duration > 0 ? seekTime / audioBuffer.duration : 0;
        setDuration(audioBuffer.duration || currentTrack.duration_seconds || 0);
        setCurrentTime(seekTime);

        if (latestPlaybackState.isPlaying) {
          engine.context.resume?.().catch?.(() => {});
          if (!engine.connected) {
            shifter.connect(engine.gainNode);
            engine.connected = true;
          }
        }
      } catch (_error) {}
    }

    preparePitchEngine();

    return () => {
      cancelled = true;
    };
  }, [
    advanceQueueAfterTrackEnd,
    currentTrack,
    currentTrackIsVideo,
    ensurePitchBuffer,
    ensurePitchContext,
    pitchEngineActive,
    teardownPitchEngine,
  ]);

  useEffect(() => {
    if (!pitchEngineActive) {
      return undefined;
    }
    const engine = pitchEngineRef.current;
    const shifter = engine.shifter;
    if (!shifter || !engine.context || !engine.gainNode) {
      return undefined;
    }
    syncPitchEngineParams();
    if (isPlaying) {
      engine.context.resume?.().catch?.(() => {});
      if (!engine.connected) {
        shifter.connect(engine.gainNode);
        engine.connected = true;
      }
    } else if (engine.connected) {
      try {
        shifter.disconnect();
      } catch (_error) {}
      engine.connected = false;
    }
    return undefined;
  }, [isPlaying, pitchEngineActive, syncPitchEngineParams]);

  useEffect(() => {
    let cancelled = false;
    if (!currentTrack?.id || !currentTrack.waveform_url) {
      setWaveformBars([]);
      setWaveformTrackId(null);
      setWaveformLoading(false);
      return undefined;
    }

    setWaveformBars([]);
    setWaveformTrackId(null);
    setWaveformLoading(true);
    fetchTrackWaveform(currentTrack)
      .then((points) => {
        if (!cancelled) {
          setWaveformBars(points);
          setWaveformTrackId(currentTrack.id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setWaveformBars([]);
          setWaveformTrackId(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setWaveformLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currentTrack?.id, currentTrack?.waveform_url]);

  useEffect(() => {
    setSelectionRange(null);
    setWaveformZoom(1);
  }, [currentTrack?.id]);

  const playQueue = useCallback((items, startIndex = 0) => {
    const nextQueue = normalizeQueueItems(items);
    if (!nextQueue.length) {
      return;
    }
    setQueue(nextQueue);
    setQueueIndex(Math.min(Math.max(startIndex, 0), nextQueue.length - 1));
    setIsPlaying(true);
  }, []);

  const playTrack = useCallback((track) => {
    if (!track) {
      return;
    }
    if (currentTrack?.id === track.id) {
      if (pitchEngineActive) {
        setIsPlaying((current) => !current);
        return;
      }
      const audio = audioRef.current;
      if (isPlaying) {
        audio?.pause();
        setIsPlaying(false);
      } else {
        audio?.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
      }
      return;
    }
    setQueue((current) => {
      const existingIndex = current.findIndex((entry) => entry.id === track.id);
      if (existingIndex >= 0) {
        setQueueIndex(existingIndex);
        return current;
      }
      setQueueIndex(current.length);
      return [...current, track];
    });
    setIsPlaying(true);
  }, [currentTrack?.id, isPlaying, pitchEngineActive]);

  const playSingleTrack = useCallback((track) => {
    if (!track) {
      return;
    }
    if (currentTrack?.id === track.id && queue.length === 1) {
      if (pitchEngineActive) {
        setIsPlaying((current) => !current);
        return;
      }
      const audio = audioRef.current;
      if (isPlaying) {
        audio?.pause();
        setIsPlaying(false);
      } else {
        audio?.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
      }
      return;
    }
    setQueue([track]);
    setQueueIndex(0);
    setIsPlaying(true);
  }, [currentTrack?.id, isPlaying, pitchEngineActive, queue.length]);

  const queueTrack = useCallback((track) => {
    if (!track) {
      return;
    }
    setQueue((current) => (current.some((entry) => entry.id === track.id) ? current : [...current, track]));
  }, []);

  const queueAndPlayTrack = useCallback((track) => {
    if (!track) {
      return;
    }
    setQueue((current) => {
      const existingIndex = current.findIndex((entry) => entry.id === track.id);
      if (existingIndex >= 0) {
        setQueueIndex(existingIndex);
        setIsPlaying(true);
        return current;
      }
      const nextQueue = [...current, track];
      setQueueIndex(nextQueue.length - 1);
      setIsPlaying(true);
      return nextQueue;
    });
  }, []);

  const playQueueIndex = useCallback((nextIndex) => {
    setQueue((currentQueue) => {
      const safeIndex = Math.max(0, Math.min(Number(nextIndex) || 0, currentQueue.length - 1));
      if (currentQueue[safeIndex]) {
        setQueueIndex(safeIndex);
        setIsPlaying(true);
      }
      return currentQueue;
    });
  }, []);

  const removeQueueTrack = useCallback((trackId) => {
    setQueue((currentQueue) => {
      const removedIndex = currentQueue.findIndex((track) => track.id === trackId);
      if (removedIndex < 0) {
        return currentQueue;
      }
      const nextQueue = currentQueue.filter((track) => track.id !== trackId);
      setQueueIndex((currentIndex) => {
        if (!nextQueue.length) {
          setIsPlaying(false);
          return -1;
        }
        if (removedIndex < currentIndex) {
          return Math.max(0, currentIndex - 1);
        }
        if (removedIndex === currentIndex) {
          return Math.min(currentIndex, nextQueue.length - 1);
        }
        return currentIndex;
      });
      return nextQueue;
    });
  }, []);

  const clearQueue = useCallback(() => {
    audioRef.current?.pause();
    teardownPitchEngine();
    setQueue([]);
    setQueueIndex(-1);
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  }, [teardownPitchEngine]);

  const stopPlayback = useCallback(() => {
    audioRef.current?.pause();
    teardownPitchEngine();
    setQueueIndex(-1);
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  }, [teardownPitchEngine]);

  const playAlbum = useCallback(async (album) => {
    if (!album || !libraryId) {
      return;
    }
    const tracks = await fetchAlbumTracks(libraryId, album.id);
    playQueue(tracks, 0);
  }, [libraryId, playQueue]);

  const queueAlbum = useCallback(async (album) => {
    if (!album || !libraryId) {
      return;
    }
    const tracks = await fetchAlbumTracks(libraryId, album.id);
    setQueue((current) => [...current, ...tracks.filter((track) => !current.some((entry) => entry.id === track.id))]);
  }, [libraryId]);

  const playArtist = useCallback(async (artist) => {
    if (!artist || !libraryId) {
      return;
    }
    const tracks = await fetchArtistTracks(libraryId, artist.id);
    playQueue(tracks, 0);
  }, [libraryId, playQueue]);

  const queueArtist = useCallback(async (artist) => {
    if (!artist || !libraryId) {
      return;
    }
    const tracks = await fetchArtistTracks(libraryId, artist.id);
    setQueue((current) => [...current, ...tracks.filter((track) => !current.some((entry) => entry.id === track.id))]);
  }, [libraryId]);

  const togglePlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!currentTrack) {
      return;
    }
    if (pitchEngineActive) {
      const engine = pitchEngineRef.current;
      if (!engine.shifter || !engine.context || !engine.gainNode) {
        return;
      }
      if (isPlaying) {
        if (engine.connected) {
          try {
            engine.shifter.disconnect();
          } catch (_error) {}
          engine.connected = false;
        }
        setIsPlaying(false);
      } else {
        engine.context.resume?.().catch?.(() => {});
        if (!engine.connected) {
          engine.shifter.connect(engine.gainNode);
          engine.connected = true;
        }
        setIsPlaying(true);
      }
      return;
    }
    if (!audio) {
      return;
    }
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    audio.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
  }, [currentTrack, isPlaying, pitchEngineActive]);

  const previous = useCallback(() => {
    setQueueIndex((current) => Math.max(0, current - 1));
    setIsPlaying(true);
  }, []);

  const next = useCallback(() => {
    setQueueIndex((current) => Math.min(queue.length - 1, current + 1));
    setIsPlaying(true);
  }, [queue.length]);

  const cycleLoopMode = useCallback(() => {
    setLoopMode((current) => (current === 'none' ? 'track' : current === 'track' ? 'queue' : 'none'));
  }, []);

  const toggleVisualMode = useCallback(() => {
    setVisualMode((current) => (current === 'waveform' ? 'spectrum' : 'waveform'));
  }, []);

  const seek = useCallback((nextTime) => {
    const audio = audioRef.current;
    const pitchEngine = pitchEngineRef.current;
    const safeDuration = duration || currentTrack?.duration_seconds || audio?.duration || pitchEngine.shifter?.duration || 0;
    const clampedTime = Math.max(0, Math.min(Number(nextTime) || 0, safeDuration || 0));
    if (pitchEngineActive && pitchEngine.shifter) {
      const sourceDuration = pitchEngine.shifter.duration || safeDuration;
      pitchEngine.shifter.percentagePlayed = sourceDuration > 0 ? clampedTime / sourceDuration : 0;
    } else if (audio) {
      audio.currentTime = clampedTime;
    }
    setCurrentTime(clampedTime);
  }, [currentTrack?.duration_seconds, duration, pitchEngineActive]);

  const changeWaveformZoom = useCallback((nextZoom) => {
    setWaveformZoom(Math.max(1, Math.min(Number(nextZoom) || 1, 64)));
  }, []);

  const changeSelectionRange = useCallback((nextRange) => {
    setSelectionRange(nextRange);
  }, []);

  const playerProps = useMemo(() => ({
    audioRef,
    track: currentTrack,
    isPlaying,
    currentTime,
    duration,
    selectionRange,
    loopMode,
    shuffleEnabled,
    volume,
    visualMode,
    pitchEngineActive,
    cursorLockEnabled,
    waveformBars: waveformTrackId === currentTrack?.id ? waveformBars : [],
    waveformKey: waveformTrackId === currentTrack?.id ? `${waveformTrackId}:${waveformBars.length}` : '',
    waveformLoading,
    waveformZoom,
    eqPanelOpen,
    eqGains,
    spectrumLevels,
    speedPanelOpen,
    pitchPanelOpen,
    playbackSpeed,
    pitchSemitones,
    onToggle: togglePlayback,
    onPrevious: previous,
    onNext: next,
    onLoopModeChange: cycleLoopMode,
    onShuffleToggle: () => setShuffleEnabled((current) => !current),
    onVolumeChange: setVolume,
    onClearSelection: () => setSelectionRange(null),
    onToggleVisualMode: toggleVisualMode,
    onToggleCursorLock: () => setCursorLockEnabled((current) => !current),
    onToggleEqPanel: () => setEqPanelOpen((current) => !current),
    onToggleSpeedPanel: () => setSpeedPanelOpen((current) => !current),
    onTogglePitchPanel: () => setPitchPanelOpen((current) => !current),
    onSeek: seek,
    onWaveformZoomChange: changeWaveformZoom,
    onSelectionChange: changeSelectionRange,
    onEqGainChange: (index, value) => setEqGains((current) => current.map((gain, gainIndex) => (gainIndex === index ? value : gain))),
    onEqReset: () => setEqGains(EQ_BANDS.map(() => 0)),
    onPlaybackSpeedChange: setPlaybackSpeed,
    onPitchSemitonesChange: setPitchSemitones,
    onRequestVisualizerAudioInput: requestVisualizerAudioInput,
  }), [
    audioRef,
    currentTrack,
    isPlaying,
    currentTime,
    duration,
    selectionRange,
    loopMode,
    shuffleEnabled,
    volume,
    visualMode,
    pitchEngineActive,
    cursorLockEnabled,
    waveformBars,
    waveformTrackId,
    waveformLoading,
    waveformZoom,
    eqPanelOpen,
    eqGains,
    spectrumLevels,
    speedPanelOpen,
    pitchPanelOpen,
    playbackSpeed,
    pitchSemitones,
    togglePlayback,
    previous,
    next,
    cycleLoopMode,
    toggleVisualMode,
    seek,
    changeWaveformZoom,
    changeSelectionRange,
    requestVisualizerAudioInput,
  ]);

  return {
    audioRef,
    queue,
    queueIndex,
    playerProps,
    actions: {
      playSingleTrack,
      playTrack,
      queueTrack,
      queueAndPlayTrack,
      playAlbum,
      queueAlbum,
      playArtist,
      queueArtist,
      playQueueIndex,
      removeQueueTrack,
      clearQueue,
      stopPlayback,
    },
  };
}
