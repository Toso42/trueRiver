package com.trueriver.tvshell;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.common.TrackGroup;
import androidx.media3.common.TrackSelectionOverride;
import androidx.media3.common.Tracks;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.ui.PlayerView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NativePlayerActivity extends Activity {
  private static final long HEADER_HIDE_DELAY_MS = 2500L;
  private static final long TRACK_GESTURE_WINDOW_MS = 900L;
  private static final long SEEK_SHORT_MS = 10000L;
  private static final long SEEK_LONG_MS = 60000L;
  private static final long SEEK_REPEAT_INTERVAL_MS = 180L;

  private ExoPlayer player;
  private PlayerView playerView;
  private AudioVisualizerView audioVisualizerView;
  private LinearLayout playerHeaderOverlay;
  private TextView playerTitle;
  private TextView playerSubtitle;
  private TextView playerCaptions;
  private TextView playerAudioTrack;
  private TextView playerProgress;
  private TextView playerNextUp;
  private TextView playerTransportHint;
  private TextView playerStatus;
  private LinearLayout videoSeekControlRow;
  private Button videoRewindLongButton;
  private Button videoRewindShortButton;
  private Button videoForwardShortButton;
  private Button videoForwardLongButton;
  private LinearLayout audioControlRow;
  private Button audioPrevButton;
  private Button audioPlayButton;
  private Button audioNextButton;
  private String playbackPath;
  private String trackJson;
  private String playlistJson;
  private String playlistMode;
  private int playlistStartIndex = 0;
  private int currentPlaylistIndex = 0;
  private volatile int playbackPreparationGeneration = 0;
  private volatile boolean playerActivityVisible = false;
  private final Handler uiHandler = new Handler(Looper.getMainLooper());
  private final Runnable hideHeaderRunnable = this::hideHeaderOverlay;
  private final Runnable hideStatusRunnable = this::hideStatus;
  private final Runnable progressRunnable = new Runnable() {
    @Override
    public void run() {
      refreshNowPlayingOverlay();
      if (player != null) {
        uiHandler.postDelayed(this, 500L);
      }
    }
  };
  private final List<SubtitleOption> subtitleOptions = new ArrayList<>();
  private final List<TrackChoice> audioOptions = new ArrayList<>();
  private final List<PlaylistEpisode> playlistEpisodes = new ArrayList<>();
  private int selectedSubtitleOption = 0;
  private int selectedAudioOption = 0;
  private int pendingTrackGestureKey = 0;
  private long pendingTrackGestureAtMs = 0L;
  private int lastSeekKeyCode = 0;
  private long lastSeekOffsetMs = 0L;
  private long lastSeekAtMs = 0L;
  private volatile boolean preparingPlayback = false;
  private boolean playbackPreparationReady = false;
  private boolean autoSubtitleSelectionPending = true;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    requestWindowFeature(Window.FEATURE_NO_TITLE);
    setContentView(R.layout.activity_native_player);
    bindViews();
    configureWindow();
    configureAudioControls();

    playbackPath = getIntent().getStringExtra("playback_path");
    trackJson = getIntent().getStringExtra("track_json");
    playlistJson = getIntent().getStringExtra("playlist_json");
    playlistMode = getIntent().getStringExtra("playlist_mode");
    playlistStartIndex = Math.max(getIntent().getIntExtra("playlist_index", 0), 0);
    parsePlaylist();
    playerTitle.setText(getIntent().getStringExtra("title"));
    playerSubtitle.setText(getIntent().getStringExtra("subtitle"));
    applySurfaceMode();
    refreshNowPlayingOverlay();
    updateSubtitleOverlay();
    if (playbackPath == null || playbackPath.trim().isEmpty()) {
      showStatus("No playback URL available for this video.");
    }
  }

  @Override
  protected void onStart() {
    super.onStart();
    playerActivityVisible = true;
    initializePlayer();
  }

  @Override
  protected void onResume() {
    super.onResume();
    enterImmersiveMode();
    if (playerView != null) {
      playerView.requestFocus();
    }
  }

  @Override
  protected void onStop() {
    playerActivityVisible = false;
    cancelPlaybackPreparation();
    cancelHeaderHide();
    uiHandler.removeCallbacks(hideStatusRunnable);
    uiHandler.removeCallbacks(progressRunnable);
    releasePlayer();
    super.onStop();
  }

  @Override
  protected void onDestroy() {
    playerActivityVisible = false;
    cancelPlaybackPreparation();
    super.onDestroy();
  }

  @Override
  public void onWindowFocusChanged(boolean hasFocus) {
    super.onWindowFocusChanged(hasFocus);
    if (hasFocus) {
      enterImmersiveMode();
    }
  }

  @Override
  public boolean dispatchKeyEvent(KeyEvent event) {
    if (event.getKeyCode() == KeyEvent.KEYCODE_BACK && event.getAction() == KeyEvent.ACTION_DOWN) {
      finish();
      return true;
    }
    if (event.getAction() == KeyEvent.ACTION_DOWN) {
      boolean audioMode = isCurrentMediaAudio();
      if (isSeekKey(event) && (!isOverlayNavigationFocus() || isMediaSeekKey(event))) {
        return handleSeekKey(event);
      }
      if (audioMode) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_CENTER || event.getKeyCode() == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) {
          toggleAudioPlayback();
          return true;
        }
        if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT) {
          seekBy(SEEK_SHORT_MS);
          return true;
        }
        if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_LEFT) {
          seekBy(-SEEK_SHORT_MS);
          return true;
        }
        if (
          event.getKeyCode() == KeyEvent.KEYCODE_CAPTIONS
            || event.getKeyCode() == KeyEvent.KEYCODE_MENU
            || event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP
            || event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN
        ) {
          revealOverlayForInteraction();
          return true;
        }
      }
      if (
        event.getKeyCode() == KeyEvent.KEYCODE_CAPTIONS
          || event.getKeyCode() == KeyEvent.KEYCODE_MENU
      ) {
        showFullTrackMenu();
        return true;
      }
      if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP) {
        return handleTrackGesture(KeyEvent.KEYCODE_DPAD_UP);
      }
      if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN) {
        return handleTrackGesture(KeyEvent.KEYCODE_DPAD_DOWN);
      }
      if (event.getKeyCode() == KeyEvent.KEYCODE_MEDIA_NEXT) {
        skipToNextEpisode();
        return true;
      }
      if (event.getKeyCode() == KeyEvent.KEYCODE_MEDIA_PREVIOUS) {
        skipToPreviousEpisode();
        return true;
      }
    }
    if (event.getAction() == KeyEvent.ACTION_DOWN) {
      revealOverlayForInteraction();
    }
    return super.dispatchKeyEvent(event);
  }

  private boolean handleTrackGesture(int keyCode) {
    if (isCurrentMediaAudio()) {
      revealOverlayForInteraction();
      return true;
    }
    long now = System.currentTimeMillis();
    boolean repeated = pendingTrackGestureKey == keyCode && now - pendingTrackGestureAtMs <= TRACK_GESTURE_WINDOW_MS;
    pendingTrackGestureKey = keyCode;
    pendingTrackGestureAtMs = now;
    if (!repeated) {
      showTrackGestureHint(keyCode);
      return true;
    }
    pendingTrackGestureKey = 0;
    pendingTrackGestureAtMs = 0L;
    if (keyCode == KeyEvent.KEYCODE_DPAD_UP) {
        autoSubtitleSelectionPending = false;
        cycleSubtitleTrack();
        return true;
      }
    cycleAudioTrack();
    return true;
  }

  private void showTrackGestureHint(int keyCode) {
    showHeaderOverlay();
    String control = keyCode == KeyEvent.KEYCODE_DPAD_UP ? "subtitles" : "audio source";
    showTransientStatus((keyCode == KeyEvent.KEYCODE_DPAD_UP ? "Subtitles" : "Audio source")
      + "\nPress again to change " + control + ".\nMenu opens full controls.");
  }

  private void showFullTrackMenu() {
    showHeaderOverlay();
    hideStatus();
    if (playerCaptions != null && !isCurrentMediaAudio()) {
      playerCaptions.requestFocus();
    }
  }

  private void bindViews() {
    playerView = findViewById(R.id.player_view);
    audioVisualizerView = findViewById(R.id.audio_visualizer_view);
    playerHeaderOverlay = findViewById(R.id.player_header_overlay);
    playerTitle = findViewById(R.id.player_title);
    playerSubtitle = findViewById(R.id.player_subtitle);
    playerCaptions = findViewById(R.id.player_captions);
    playerAudioTrack = findViewById(R.id.player_audio_track);
    playerProgress = findViewById(R.id.player_progress);
    playerNextUp = findViewById(R.id.player_next_up);
    playerTransportHint = findViewById(R.id.player_transport_hint);
    playerStatus = findViewById(R.id.player_status);
    videoSeekControlRow = findViewById(R.id.video_seek_control_row);
    videoRewindLongButton = findViewById(R.id.video_rewind_long_button);
    videoRewindShortButton = findViewById(R.id.video_rewind_short_button);
    videoForwardShortButton = findViewById(R.id.video_forward_short_button);
    videoForwardLongButton = findViewById(R.id.video_forward_long_button);
    audioControlRow = findViewById(R.id.audio_control_row);
    audioPrevButton = findViewById(R.id.audio_prev_button);
    audioPlayButton = findViewById(R.id.audio_play_button);
    audioNextButton = findViewById(R.id.audio_next_button);
  }

  private void configureWindow() {
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    enterImmersiveMode();
  }

  private void configureAudioControls() {
    if (playerCaptions != null) {
      playerCaptions.setOnClickListener((view) -> {
        autoSubtitleSelectionPending = false;
        cycleSubtitleTrack();
      });
      playerCaptions.setOnKeyListener((view, keyCode, event) -> {
        if (event.getAction() == KeyEvent.ACTION_DOWN && (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER)) {
          autoSubtitleSelectionPending = false;
          cycleSubtitleTrack();
          return true;
        }
        return false;
      });
    }
    if (playerAudioTrack != null) {
      playerAudioTrack.setOnClickListener((view) -> cycleAudioTrack());
      playerAudioTrack.setOnKeyListener((view, keyCode, event) -> {
        if (event.getAction() == KeyEvent.ACTION_DOWN && (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER)) {
          cycleAudioTrack();
          return true;
        }
        return false;
      });
    }
    configureSeekButton(videoRewindLongButton, -SEEK_LONG_MS);
    configureSeekButton(videoRewindShortButton, -SEEK_SHORT_MS);
    configureSeekButton(videoForwardShortButton, SEEK_SHORT_MS);
    configureSeekButton(videoForwardLongButton, SEEK_LONG_MS);
    if (audioPrevButton != null) {
      audioPrevButton.setOnClickListener((view) -> skipToPreviousEpisode());
    }
    if (audioPlayButton != null) {
      audioPlayButton.setOnClickListener((view) -> toggleAudioPlayback());
    }
    if (audioNextButton != null) {
      audioNextButton.setOnClickListener((view) -> skipToNextEpisode());
    }
  }

  private void initializePlayer() {
    if (!playerActivityVisible || player != null || playbackPath == null || playbackPath.trim().isEmpty()) {
      return;
    }
    if (needsPlaybackPreparation()) {
      startPlaybackPreparation();
      return;
    }

    DefaultHttpDataSource.Factory httpFactory = new DefaultHttpDataSource.Factory()
      .setAllowCrossProtocolRedirects(true)
      .setUserAgent(BuildConfig.TV_USER_AGENT_SUFFIX);

    TvConnectionConfig config = TvConnectionConfig.load(this);
    Map<String, String> headers = new HashMap<>();
    String virtualHost = config.virtualHostHeader();
    if (!virtualHost.isEmpty()) {
      headers.put("Host", virtualHost);
      headers.put("X-Forwarded-Host", virtualHost);
    }
    headers.put("X-Forwarded-Proto", "https");
    headers.put("Authorization", config.basicAuthHeader());
    httpFactory.setDefaultRequestProperties(headers);

    player = new ExoPlayer.Builder(this)
      .setMediaSourceFactory(new DefaultMediaSourceFactory(httpFactory))
      .build();
    if ("series".equals(playlistMode)) {
      player.setRepeatMode(Player.REPEAT_MODE_ALL);
    }
    playerView.setPlayer(player);
    playerView.setBackgroundColor(Color.BLACK);
    applySurfaceMode();

    player.addListener(new Player.Listener() {
      @Override
      public void onPlayerError(PlaybackException error) {
        showHeaderOverlay();
        showStatus("Playback error:\n" + error.getMessage());
      }

      @Override
      public void onPlaybackStateChanged(int playbackState) {
        refreshNowPlayingOverlay();
        if (playbackState == Player.STATE_READY) {
          hideStatus();
          refreshSubtitleOptions();
          refreshAudioOptions();
          if (player != null && player.isPlaying()) {
            scheduleHeaderHide();
          } else {
            showHeaderOverlay();
          }
        } else if (playbackState == Player.STATE_BUFFERING) {
          showHeaderOverlay();
          showStatus(isCurrentMediaAudio() ? "Buffering audio..." : "Buffering video...");
        } else if (playbackState == Player.STATE_ENDED) {
          showHeaderOverlay();
          showStatus(hasNextEpisode() ? "Loading next item..." : "End of queue.");
        }
      }

      @Override
      public void onIsPlayingChanged(boolean isPlaying) {
        refreshNowPlayingOverlay();
        if (isPlaying) {
          hideStatus();
          scheduleHeaderHide();
          return;
        }
        showHeaderOverlay();
      }

      @Override
      public void onTracksChanged(Tracks tracks) {
        refreshSubtitleOptions();
        refreshAudioOptions();
      }

      @Override
      public void onMediaItemTransition(MediaItem mediaItem, int reason) {
        updateCurrentPlaylistEpisode(mediaItem);
        applySurfaceMode();
        refreshNowPlayingOverlay();
      }
    });

    List<MediaItem> mediaItems = buildMediaItems();
    if (mediaItems.isEmpty()) {
      showStatus("No playable episode available.");
      return;
    }
    currentPlaylistIndex = Math.min(playlistStartIndex, mediaItems.size() - 1);
    player.setMediaItems(mediaItems, currentPlaylistIndex, C.TIME_UNSET);
    player.prepare();
    player.play();
    uiHandler.removeCallbacks(progressRunnable);
    uiHandler.post(progressRunnable);
  }

  private boolean needsPlaybackPreparation() {
    if (playbackPreparationReady || isCurrentMediaAudio()) {
      return false;
    }
    JSONObject payload = parseJsonObject(trackJson);
    if (payload == null) {
      return false;
    }
    JSONObject status = payload.optJSONObject("playback_status");
    if (status == null) {
      return false;
    }
    return !status.optBoolean("cache_ready", true);
  }

  private void startPlaybackPreparation() {
    if (!playerActivityVisible || preparingPlayback) {
      return;
    }
    String trackId = currentTrackId();
    if (trackId.isEmpty()) {
      playbackPreparationReady = true;
      if (playerActivityVisible) {
        initializePlayer();
      }
      return;
    }
    preparingPlayback = true;
    int preparationGeneration = nextPlaybackPreparationGeneration();
    showStatus("Preparing video playback...");
    new Thread(() -> {
      try {
        JSONObject status = requestPlaybackStatus("POST", "/tracks/" + trackId + "/prepare-playback/");
        if (!isPlaybackPreparationCurrent(preparationGeneration)) {
          return;
        }
        publishPlaybackPreparationStatus(status, preparationGeneration);
        int attempts = 0;
        while (!status.optBoolean("cache_ready", false) && attempts < 720) {
          Thread.sleep(1500L);
          if (!isPlaybackPreparationCurrent(preparationGeneration)) {
            return;
          }
          status = requestPlaybackStatus("GET", "/tracks/" + trackId + "/playback-status/");
          if (!isPlaybackPreparationCurrent(preparationGeneration)) {
            return;
          }
          publishPlaybackPreparationStatus(status, preparationGeneration);
          attempts += 1;
        }
        boolean ready = status.optBoolean("cache_ready", false);
        if (ready && isPlaybackPreparationCurrent(preparationGeneration)) {
          mergePlaybackStatus(status);
        }
        runOnUiThread(() -> {
          if (!isPlaybackPreparationCurrent(preparationGeneration)) {
            return;
          }
          preparingPlayback = false;
          playbackPreparationReady = ready;
          if (ready) {
            hideStatus();
            initializePlayer();
          } else {
            showStatus("Video preparation is still running. Try again shortly.");
          }
        });
      } catch (Exception error) {
        String message = error.getMessage() == null ? "Unable to prepare video playback." : error.getMessage();
        runOnUiThread(() -> {
          if (!isPlaybackPreparationCurrent(preparationGeneration)) {
            return;
          }
          preparingPlayback = false;
          showStatus("Unable to prepare video playback:\n" + message);
        });
      }
    }).start();
  }

  private synchronized int nextPlaybackPreparationGeneration() {
    playbackPreparationGeneration += 1;
    return playbackPreparationGeneration;
  }

  private synchronized void cancelPlaybackPreparation() {
    playbackPreparationGeneration += 1;
    preparingPlayback = false;
  }

  private boolean isPlaybackPreparationCurrent(int generation) {
    return playerActivityVisible && generation == playbackPreparationGeneration;
  }

  private String currentTrackId() {
    JSONObject payload = parseJsonObject(trackJson);
    return payload == null ? "" : payload.optString("id", "").trim();
  }

  private void publishPlaybackPreparationStatus(JSONObject status, int generation) {
    if (!isPlaybackPreparationCurrent(generation)) {
      return;
    }
    mergePlaybackStatus(status);
    JSONObject progress = status.optJSONObject("progress");
    int percent = progress == null ? 0 : progress.optInt("percent", 0);
    String message = status.optString("message", "Preparing this video for playback.");
    runOnUiThread(() -> {
      if (isPlaybackPreparationCurrent(generation)) {
        showStatus("Preparing video playback\n" + percent + "%\n" + message);
      }
    });
  }

  private void mergePlaybackStatus(JSONObject status) {
    JSONObject payload = parseJsonObject(trackJson);
    if (payload == null || status == null) {
      return;
    }
    try {
      payload.put("playback_status", status);
      payload.put("playback_cache_ready", status.optBoolean("cache_ready", false));
      trackJson = payload.toString();
    } catch (Exception _error) {
      // Keep the original payload if status merging fails.
    }
  }

  private JSONObject requestPlaybackStatus(String method, String path) throws Exception {
    HttpURLConnection connection = null;
    InputStream inputStream = null;
    try {
      connection = (HttpURLConnection) new URL(endpoint(path)).openConnection();
      connection.setRequestMethod(method);
      connection.setConnectTimeout(10000);
      connection.setReadTimeout(18000);
      connection.setRequestProperty("Accept", "application/json");
      connection.setRequestProperty("User-Agent", BuildConfig.TV_USER_AGENT_SUFFIX);
      if ("POST".equals(method)) {
        connection.setRequestProperty("Content-Length", "0");
        connection.setDoOutput(true);
      }
      TvConnectionConfig.load(this).applyHeaders(connection);
      connection.connect();
      int statusCode = connection.getResponseCode();
      inputStream = statusCode >= 200 && statusCode < 300 ? connection.getInputStream() : connection.getErrorStream();
      String body = inputStream == null ? "" : readFully(inputStream);
      if (statusCode < 200 || statusCode >= 300) {
        throw new IllegalStateException("HTTP " + statusCode + " while preparing playback.");
      }
      return new JSONObject(body);
    } finally {
      if (inputStream != null) {
        inputStream.close();
      }
      if (connection != null) {
        connection.disconnect();
      }
    }
  }

  private String readFully(InputStream inputStream) throws Exception {
    BufferedInputStream buffered = new BufferedInputStream(inputStream);
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    byte[] buffer = new byte[4096];
    int read;
    while ((read = buffered.read(buffer)) != -1) {
      output.write(buffer, 0, read);
    }
    return output.toString(StandardCharsets.UTF_8.name());
  }

  private void parsePlaylist() {
    playlistEpisodes.clear();
    if (playlistJson != null && !playlistJson.trim().isEmpty()) {
      try {
        JSONArray episodes = new JSONArray(playlistJson);
        for (int index = 0; index < episodes.length(); index += 1) {
          JSONObject episode = episodes.optJSONObject(index);
          if (episode == null) {
            continue;
          }
          String episodePlaybackPath = episode.optString("playback_url", episode.optString("stream_url", ""));
          if (episodePlaybackPath == null || episodePlaybackPath.trim().isEmpty()) {
            continue;
          }
          playlistEpisodes.add(new PlaylistEpisode(
            buildEpisodeTitle(episode),
            buildEpisodeSubtitle(episode),
            episodePlaybackPath,
            episode.toString()
          ));
        }
      } catch (Exception _error) {
        playlistEpisodes.clear();
      }
    }

    if (playlistEpisodes.isEmpty() && playbackPath != null && !playbackPath.trim().isEmpty()) {
      playlistEpisodes.add(new PlaylistEpisode(
        getIntent().getStringExtra("title"),
        getIntent().getStringExtra("subtitle"),
        playbackPath,
        trackJson
      ));
      playlistStartIndex = 0;
    }
  }

  private List<MediaItem> buildMediaItems() {
    List<MediaItem> mediaItems = new ArrayList<>();
    for (int index = 0; index < playlistEpisodes.size(); index += 1) {
      PlaylistEpisode episode = playlistEpisodes.get(index);
      MediaItem.Builder mediaItemBuilder = new MediaItem.Builder()
        .setMediaId(String.valueOf(index))
        .setUri(Uri.parse(rewritePlaybackUrl(episode.playbackPath)));
      List<MediaItem.SubtitleConfiguration> subtitleConfigurations = buildSubtitleConfigurations(episode.trackJson);
      if (!subtitleConfigurations.isEmpty()) {
        mediaItemBuilder.setSubtitleConfigurations(subtitleConfigurations);
      }
      mediaItems.add(mediaItemBuilder.build());
    }
    return mediaItems;
  }

  private void updateCurrentPlaylistEpisode(MediaItem mediaItem) {
    if (mediaItem == null || mediaItem.mediaId == null || mediaItem.mediaId.isEmpty()) {
      return;
    }
    try {
      int nextIndex = Integer.parseInt(mediaItem.mediaId);
      if (nextIndex < 0 || nextIndex >= playlistEpisodes.size()) {
        return;
      }
      currentPlaylistIndex = nextIndex;
      PlaylistEpisode episode = playlistEpisodes.get(currentPlaylistIndex);
      playbackPath = episode.playbackPath;
      trackJson = episode.trackJson;
      playerTitle.setText(episode.title);
      playerSubtitle.setText(buildPlaylistSubtitle(episode));
      subtitleOptions.clear();
      audioOptions.clear();
      selectedSubtitleOption = 0;
      selectedAudioOption = 0;
      autoSubtitleSelectionPending = true;
      applySurfaceMode();
      refreshNowPlayingOverlay();
      updateSubtitleOverlay();
      updateAudioOverlay();
    } catch (NumberFormatException _error) {
      // Ignore malformed media ids.
    }
  }

  private boolean hasNextEpisode() {
    return currentPlaylistIndex + 1 < playlistEpisodes.size();
  }

  private void skipToNextEpisode() {
    revealOverlayForInteraction();
    if (player == null || !player.hasNextMediaItem()) {
      showStatus("No next episode.");
      return;
    }
    hideStatus();
    player.seekToNextMediaItem();
    player.play();
  }

  private void skipToPreviousEpisode() {
    revealOverlayForInteraction();
    if (player == null || !player.hasPreviousMediaItem()) {
      showStatus("No previous episode.");
      return;
    }
    hideStatus();
    player.seekToPreviousMediaItem();
    player.play();
  }

  private String buildPlaylistSubtitle(PlaylistEpisode episode) {
    if (playlistEpisodes.size() <= 1) {
      return episode.subtitle == null ? "" : episode.subtitle;
    }
    return "Episode " + (currentPlaylistIndex + 1) + " of " + playlistEpisodes.size()
      + (episode.subtitle == null || episode.subtitle.trim().isEmpty() ? "" : " · " + episode.subtitle);
  }

  private void revealOverlayForInteraction() {
    showHeaderOverlay();
    if (player != null && player.isPlaying() && playerStatus.getVisibility() != View.VISIBLE) {
      scheduleHeaderHide();
    }
  }

  private void toggleAudioPlayback() {
    revealOverlayForInteraction();
    if (player == null) {
      return;
    }
    if (player.isPlaying()) {
      player.pause();
    } else {
      player.play();
    }
    refreshNowPlayingOverlay();
  }

  private void seekBy(long offsetMs) {
    revealOverlayForInteraction();
    if (player == null) {
      return;
    }
    long durationMs = player.getDuration();
    long maxPosition = durationMs > 0 ? durationMs : Long.MAX_VALUE;
    long nextPosition = Math.max(0L, Math.min(player.getCurrentPosition() + offsetMs, maxPosition));
    player.seekTo(nextPosition);
    refreshNowPlayingOverlay();
  }

  private void configureSeekButton(Button button, long offsetMs) {
    if (button == null) {
      return;
    }
    button.setOnClickListener((view) -> seekBy(offsetMs));
    button.setOnKeyListener((view, keyCode, event) -> {
      if (event.getAction() == KeyEvent.ACTION_DOWN && (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER)) {
        seekBy(offsetMs);
        return true;
      }
      return false;
    });
  }

  private boolean isSeekKey(KeyEvent event) {
    int keyCode = event.getKeyCode();
    return keyCode == KeyEvent.KEYCODE_DPAD_RIGHT
      || keyCode == KeyEvent.KEYCODE_DPAD_LEFT
      || keyCode == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD
      || keyCode == KeyEvent.KEYCODE_MEDIA_REWIND;
  }

  private boolean isMediaSeekKey(KeyEvent event) {
    int keyCode = event.getKeyCode();
    return keyCode == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD || keyCode == KeyEvent.KEYCODE_MEDIA_REWIND;
  }

  private boolean handleSeekKey(KeyEvent event) {
    long offsetMs;
    int keyCode = event.getKeyCode();
    if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {
      offsetMs = -SEEK_SHORT_MS;
    } else if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
      offsetMs = SEEK_SHORT_MS;
    } else if (keyCode == KeyEvent.KEYCODE_MEDIA_REWIND) {
      offsetMs = -SEEK_LONG_MS;
    } else {
      offsetMs = SEEK_LONG_MS;
    }
    long now = System.currentTimeMillis();
    if (event.getRepeatCount() > 0
      && keyCode == lastSeekKeyCode
      && offsetMs == lastSeekOffsetMs
      && now - lastSeekAtMs < SEEK_REPEAT_INTERVAL_MS) {
      return true;
    }
    lastSeekKeyCode = keyCode;
    lastSeekOffsetMs = offsetMs;
    lastSeekAtMs = now;
    seekBy(offsetMs);
    return true;
  }

  private boolean isOverlayNavigationFocus() {
    View focus = getCurrentFocus();
    return focus == playerCaptions
      || focus == playerAudioTrack
      || focus == videoRewindLongButton
      || focus == videoRewindShortButton
      || focus == videoForwardShortButton
      || focus == videoForwardLongButton
      || focus == audioPrevButton
      || focus == audioPlayButton
      || focus == audioNextButton;
  }

  private void applySurfaceMode() {
    boolean audioMode = isCurrentMediaAudio();
    if (audioVisualizerView != null) {
      audioVisualizerView.setVisibility(audioMode ? View.VISIBLE : View.GONE);
    }
    if (playerView != null) {
      playerView.setUseController(!audioMode);
      playerView.setVisibility(audioMode ? View.GONE : View.VISIBLE);
    }
    if (playerTransportHint != null) {
      playerTransportHint.setText(audioMode ? "Prev · Play/Pause · Next" : "Left/right 10s · Rew/FF 60s · Up subtitles · Down audio");
    }
    if (videoSeekControlRow != null) {
      videoSeekControlRow.setVisibility(audioMode ? View.GONE : View.VISIBLE);
    }
    if (audioControlRow != null) {
      audioControlRow.setVisibility(audioMode ? View.VISIBLE : View.GONE);
    }
    if (audioMode) {
      showHeaderOverlay();
    }
    updateAudioOverlay();
  }

  private boolean isCurrentMediaAudio() {
    JSONObject payload = parseJsonObject(trackJson);
    if (payload == null) {
      return false;
    }
    String mediaKind = payload.optString("media_kind", "").trim().toLowerCase();
    if ("audio".equals(mediaKind)) {
      return true;
    }
    if ("video".equals(mediaKind)) {
      return false;
    }
    boolean hasVideoShape = payload.has("video_codec")
      || payload.optInt("width", 0) > 0
      || payload.optInt("height", 0) > 0
      || payload.has("subtitle_streams");
    return !hasVideoShape;
  }

  private void refreshNowPlayingOverlay() {
    if (playerProgress == null || playerNextUp == null) {
      return;
    }
    long positionMs = player == null ? 0L : Math.max(player.getCurrentPosition(), 0L);
    long durationMs = player == null ? 0L : player.getDuration();
    if (durationMs < 0) {
      durationMs = 0L;
    }
    playerProgress.setText(formatTime(positionMs) + " / " + formatTime(durationMs));
    playerNextUp.setText(nextUpLabel());
    if (audioPlayButton != null) {
      audioPlayButton.setText(player != null && player.isPlaying() ? "Pause" : "Play");
    }
    if (audioPrevButton != null) {
      audioPrevButton.setEnabled(player != null && player.hasPreviousMediaItem());
    }
    if (audioNextButton != null) {
      audioNextButton.setEnabled(player != null && player.hasNextMediaItem());
    }
    if (audioVisualizerView != null) {
      float progress = durationMs > 0 ? Math.min(1f, Math.max(0f, positionMs / (float) durationMs)) : 0f;
      audioVisualizerView.setPlaybackState(player != null && player.isPlaying(), progress);
    }
  }

  private String nextUpLabel() {
    if (playlistEpisodes.size() <= currentPlaylistIndex + 1) {
      return "Next: end of queue";
    }
    PlaylistEpisode episode = playlistEpisodes.get(currentPlaylistIndex + 1);
    return "Next: " + episode.title;
  }

  private String formatTime(long millis) {
    long totalSeconds = Math.max(0L, millis / 1000L);
    long minutes = totalSeconds / 60L;
    long seconds = totalSeconds % 60L;
    return minutes + ":" + String.format("%02d", seconds);
  }

  private JSONObject parseJsonObject(String raw) {
    if (raw == null || raw.trim().isEmpty()) {
      return null;
    }
    try {
      return new JSONObject(raw);
    } catch (Exception _error) {
      return null;
    }
  }

  private void scheduleHeaderHide() {
    if (playerHeaderOverlay == null) {
      return;
    }
    cancelHeaderHide();
    uiHandler.postDelayed(hideHeaderRunnable, HEADER_HIDE_DELAY_MS);
  }

  private void cancelHeaderHide() {
    uiHandler.removeCallbacks(hideHeaderRunnable);
  }

  private void showHeaderOverlay() {
    cancelHeaderHide();
    if (playerHeaderOverlay != null) {
      playerHeaderOverlay.setVisibility(View.VISIBLE);
      playerHeaderOverlay.animate().alpha(1f).setDuration(140L).start();
    }
  }

  private void hideHeaderOverlay() {
    if (playerHeaderOverlay == null) {
      return;
    }
    if (playerStatus != null && playerStatus.getVisibility() == View.VISIBLE) {
      return;
    }
    playerHeaderOverlay.animate()
      .alpha(0f)
      .setDuration(180L)
      .withEndAction(() -> playerHeaderOverlay.setVisibility(View.GONE))
      .start();
  }

  private String rewritePlaybackUrl(String path) {
    return TvConnectionConfig.load(this).rewriteServerUrl(path);
  }

  private String endpoint(String path) {
    return TvConnectionConfig.load(this).apiBaseUrl() + path;
  }

  private List<MediaItem.SubtitleConfiguration> buildSubtitleConfigurations() {
    return buildSubtitleConfigurations(trackJson);
  }

  private List<MediaItem.SubtitleConfiguration> buildSubtitleConfigurations(String subtitleTrackJson) {
    List<MediaItem.SubtitleConfiguration> configurations = new ArrayList<>();
    if (subtitleTrackJson == null || subtitleTrackJson.trim().isEmpty()) {
      return configurations;
    }

    try {
      JSONObject payload = new JSONObject(subtitleTrackJson);
      JSONArray streams = payload.optJSONArray("subtitle_streams");
      if (streams == null) {
        return configurations;
      }
      for (int index = 0; index < streams.length(); index += 1) {
        JSONObject stream = streams.optJSONObject(index);
        if (stream == null || !stream.optBoolean("extractable", false)) {
          continue;
        }
        String subtitleUrl = rewritePlaybackUrl(stream.optString("url", ""));
        if (subtitleUrl.isEmpty()) {
          continue;
        }
        MediaItem.SubtitleConfiguration.Builder builder =
          new MediaItem.SubtitleConfiguration.Builder(Uri.parse(subtitleUrl))
            .setMimeType(MimeTypes.TEXT_VTT);
        String language = stream.optString("language", "");
        String label = stream.optString("title", language);
        if (!language.isEmpty()) {
          builder.setLanguage(language);
        }
        if (!label.isEmpty()) {
          builder.setLabel(label);
        }
        if (stream.optBoolean("default", false)) {
          builder.setSelectionFlags(C.SELECTION_FLAG_DEFAULT);
        }
        configurations.add(builder.build());
      }
    } catch (Exception _error) {
      // Ignore malformed subtitle payloads and keep playback alive.
    }
    return configurations;
  }

  private void refreshSubtitleOptions() {
    subtitleOptions.clear();
    selectedSubtitleOption = 0;

    if (player == null) {
      updateSubtitleOverlay();
      return;
    }

    Tracks currentTracks = player.getCurrentTracks();
    int optionIndex = 1;
    for (Tracks.Group group : currentTracks.getGroups()) {
      if (group.getType() != C.TRACK_TYPE_TEXT) {
        continue;
      }
      TrackGroup trackGroup = group.getMediaTrackGroup();
      for (int trackIndex = 0; trackIndex < trackGroup.length; trackIndex += 1) {
        if (!group.isTrackSupported(trackIndex)) {
          continue;
        }
        Format format = trackGroup.getFormat(trackIndex);
        subtitleOptions.add(new SubtitleOption(
          optionIndex,
          trackGroup,
          trackIndex,
          buildSubtitleLabel(format, optionIndex)
        ));
        if (group.isTrackSelected(trackIndex)) {
          selectedSubtitleOption = optionIndex;
        }
        optionIndex += 1;
      }
    }

    if (selectedSubtitleOption <= 0 && autoSubtitleSelectionPending && !subtitleOptions.isEmpty()) {
      autoSubtitleSelectionPending = false;
      applySubtitleSelection(subtitleOptions.get(0).optionIndex);
      return;
    }

    updateSubtitleOverlay();
  }

  private String buildSubtitleLabel(Format format, int optionIndex) {
    String language = format.language == null ? "" : format.language.trim();
    String label = format.label == null ? "" : format.label.trim();
    if (!label.isEmpty() && !language.isEmpty() && !label.equalsIgnoreCase(language)) {
      return label + " · " + language;
    }
    if (!label.isEmpty()) {
      return label;
    }
    if (!language.isEmpty()) {
      return language;
    }
    return "Subtitle " + optionIndex;
  }

  private void cycleSubtitleTrack() {
    revealOverlayForInteraction();
    if (player == null) {
      return;
    }
    refreshSubtitleOptions();
    if (subtitleOptions.isEmpty()) {
      showStatus("No subtitles available.");
      return;
    }
    int nextOption = selectedSubtitleOption + 1;
    if (nextOption > subtitleOptions.size()) {
      nextOption = 0;
    }
    applySubtitleSelection(nextOption);
  }

  private void disableSubtitleTrack() {
    revealOverlayForInteraction();
    if (player == null) {
      return;
    }
    refreshSubtitleOptions();
    if (subtitleOptions.isEmpty()) {
      showStatus("No subtitles available.");
      return;
    }
    applySubtitleSelection(0);
    showStatus("Subtitles off.");
  }

  private void applySubtitleSelection(int optionIndex) {
    if (player == null) {
      return;
    }
    androidx.media3.common.TrackSelectionParameters.Builder parametersBuilder =
      player.getTrackSelectionParameters().buildUpon();
    parametersBuilder.clearOverridesOfType(C.TRACK_TYPE_TEXT);

    if (optionIndex <= 0) {
      parametersBuilder.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true);
      selectedSubtitleOption = 0;
      player.setTrackSelectionParameters(parametersBuilder.build());
      hideStatus();
      updateSubtitleOverlay();
      return;
    }

    SubtitleOption selectedOption = null;
    for (SubtitleOption option : subtitleOptions) {
      if (option.optionIndex == optionIndex) {
        selectedOption = option;
        break;
      }
    }
    if (selectedOption == null) {
      return;
    }

    parametersBuilder.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, false);
    parametersBuilder.addOverride(
      new TrackSelectionOverride(selectedOption.trackGroup, Collections.singletonList(selectedOption.trackIndex))
    );
    player.setTrackSelectionParameters(parametersBuilder.build());
    selectedSubtitleOption = optionIndex;
    hideStatus();
    updateSubtitleOverlay();
  }

  private void updateSubtitleOverlay() {
    if (playerCaptions == null) {
      return;
    }
    if (isCurrentMediaAudio()) {
      playerCaptions.setText("Audio visualizer");
      return;
    }
    if (subtitleOptions.isEmpty()) {
      playerCaptions.setText("Subtitles: none");
      return;
    }
    if (selectedSubtitleOption <= 0) {
      playerCaptions.setText("Subtitles: Off");
      return;
    }
    for (SubtitleOption option : subtitleOptions) {
      if (option.optionIndex == selectedSubtitleOption) {
        playerCaptions.setText("Subtitles: " + option.label);
        return;
      }
    }
    playerCaptions.setText("Subtitles: Off");
  }

  private void refreshAudioOptions() {
    audioOptions.clear();
    selectedAudioOption = 0;

    if (player == null) {
      updateAudioOverlay();
      return;
    }

    Tracks currentTracks = player.getCurrentTracks();
    int optionIndex = 1;
    for (Tracks.Group group : currentTracks.getGroups()) {
      if (group.getType() != C.TRACK_TYPE_AUDIO) {
        continue;
      }
      TrackGroup trackGroup = group.getMediaTrackGroup();
      for (int trackIndex = 0; trackIndex < trackGroup.length; trackIndex += 1) {
        if (!group.isTrackSupported(trackIndex)) {
          continue;
        }
        Format format = trackGroup.getFormat(trackIndex);
        audioOptions.add(new TrackChoice(
          optionIndex,
          trackGroup,
          trackIndex,
          buildAudioLabel(format, optionIndex)
        ));
        if (group.isTrackSelected(trackIndex)) {
          selectedAudioOption = optionIndex;
        }
        optionIndex += 1;
      }
    }
    updateAudioOverlay();
  }

  private String buildAudioLabel(Format format, int optionIndex) {
    String language = format.language == null ? "" : format.language.trim();
    String label = format.label == null ? "" : format.label.trim();
    List<String> bits = new ArrayList<>();
    if (!label.isEmpty() && !label.equalsIgnoreCase(language)) {
      bits.add(label);
    }
    if (!language.isEmpty()) {
      bits.add(language);
    }
    if (format.channelCount > 0) {
      bits.add(format.channelCount == 1 ? "mono" : format.channelCount == 2 ? "stereo" : format.channelCount + "ch");
    }
    if (bits.isEmpty()) {
      return "Audio " + optionIndex;
    }
    return joinBits(bits);
  }

  private void cycleAudioTrack() {
    revealOverlayForInteraction();
    if (player == null) {
      return;
    }
    refreshAudioOptions();
    if (audioOptions.isEmpty()) {
      showTransientStatus("No alternate audio sources available.");
      return;
    }
    int nextOption = selectedAudioOption + 1;
    if (nextOption <= 0 || nextOption > audioOptions.size()) {
      nextOption = 1;
    }
    applyAudioSelection(nextOption);
  }

  private void applyAudioSelection(int optionIndex) {
    if (player == null) {
      return;
    }
    TrackChoice selectedOption = null;
    for (TrackChoice option : audioOptions) {
      if (option.optionIndex == optionIndex) {
        selectedOption = option;
        break;
      }
    }
    if (selectedOption == null) {
      return;
    }

    androidx.media3.common.TrackSelectionParameters.Builder parametersBuilder =
      player.getTrackSelectionParameters().buildUpon();
    parametersBuilder.clearOverridesOfType(C.TRACK_TYPE_AUDIO);
    parametersBuilder.setTrackTypeDisabled(C.TRACK_TYPE_AUDIO, false);
    parametersBuilder.addOverride(
      new TrackSelectionOverride(selectedOption.trackGroup, Collections.singletonList(selectedOption.trackIndex))
    );
    player.setTrackSelectionParameters(parametersBuilder.build());
    selectedAudioOption = optionIndex;
    updateAudioOverlay();
    showTransientStatus("Audio: " + selectedOption.label);
  }

  private void updateAudioOverlay() {
    if (playerAudioTrack == null) {
      return;
    }
    if (isCurrentMediaAudio()) {
      playerAudioTrack.setVisibility(View.GONE);
      return;
    }
    playerAudioTrack.setVisibility(View.VISIBLE);
    if (audioOptions.isEmpty()) {
      playerAudioTrack.setText("Audio: default");
      return;
    }
    for (TrackChoice option : audioOptions) {
      if (option.optionIndex == selectedAudioOption) {
        playerAudioTrack.setText("Audio: " + option.label);
        return;
      }
    }
    playerAudioTrack.setText(audioOptions.size() == 1 ? "Audio: " + audioOptions.get(0).label : "Audio: choose");
  }

  private void releasePlayer() {
    if (player != null) {
      player.release();
      player = null;
    }
  }

  private void showStatus(String text) {
    uiHandler.removeCallbacks(hideStatusRunnable);
    showHeaderOverlay();
    playerStatus.setText(text);
    playerStatus.setVisibility(View.VISIBLE);
  }

  private void showTransientStatus(String text) {
    showStatus(text);
    uiHandler.postDelayed(hideStatusRunnable, 1800L);
  }

  private void hideStatus() {
    uiHandler.removeCallbacks(hideStatusRunnable);
    playerStatus.setVisibility(View.GONE);
  }

  private void enterImmersiveMode() {
    Window window = getWindow();
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
      WindowInsetsController controller = window.getInsetsController();
      if (controller != null) {
        controller.hide(WindowInsets.Type.systemBars());
        controller.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
      }
      return;
    }

    View decorView = window.getDecorView();
    decorView.setSystemUiVisibility(
      View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
        | View.SYSTEM_UI_FLAG_FULLSCREEN
        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
    );
  }

  private static final class SubtitleOption {
    final int optionIndex;
    final TrackGroup trackGroup;
    final int trackIndex;
    final String label;

    SubtitleOption(int optionIndex, TrackGroup trackGroup, int trackIndex, String label) {
      this.optionIndex = optionIndex;
      this.trackGroup = trackGroup;
      this.trackIndex = trackIndex;
      this.label = label;
    }
  }

  private static final class TrackChoice {
    final int optionIndex;
    final TrackGroup trackGroup;
    final int trackIndex;
    final String label;

    TrackChoice(int optionIndex, TrackGroup trackGroup, int trackIndex, String label) {
      this.optionIndex = optionIndex;
      this.trackGroup = trackGroup;
      this.trackIndex = trackIndex;
      this.label = label;
    }
  }

  private String buildEpisodeTitle(JSONObject episode) {
    int season = Math.max(episode.optInt("season_number", 1), 1);
    int episodeNumber = episode.optInt("episode_number", 0);
    String episodeTitle = episode.optString("episode_title", "").trim();
    String canonicalTitle = episode.optString("canonical_title", "Untitled Episode");
    String prefix = "";
    if (episodeNumber > 0) {
      prefix = "S" + String.format("%02d", season) + "E" + String.format("%02d", episodeNumber) + " ";
    }
    if (!episodeTitle.isEmpty()) {
      return prefix + episodeTitle;
    }
    return prefix + canonicalTitle;
  }

  private String buildEpisodeSubtitle(JSONObject episode) {
    List<String> bits = new ArrayList<>();
    String canonicalTitle = episode.optString("canonical_title", "").trim();
    String videoCodec = episode.optString("video_codec", "").trim();
    String audioCodec = episode.optString("audio_codec", "").trim();
    if (!canonicalTitle.isEmpty()) {
      bits.add(canonicalTitle);
    }
    if (!videoCodec.isEmpty()) {
      bits.add(videoCodec);
    }
    if (!audioCodec.isEmpty()) {
      bits.add(audioCodec);
    }
    if (bits.isEmpty()) {
      bits.add("Episode");
    }
    return joinBits(bits);
  }

  private String joinBits(List<String> bits) {
    StringBuilder builder = new StringBuilder();
    for (int index = 0; index < bits.size(); index += 1) {
      if (index > 0) {
        builder.append(" · ");
      }
      builder.append(bits.get(index));
    }
    return builder.toString();
  }

  private static final class PlaylistEpisode {
    final String title;
    final String subtitle;
    final String playbackPath;
    final String trackJson;

    PlaylistEpisode(String title, String subtitle, String playbackPath, String trackJson) {
      this.title = title == null ? "Untitled Episode" : title;
      this.subtitle = subtitle == null ? "" : subtitle;
      this.playbackPath = playbackPath == null ? "" : playbackPath;
      this.trackJson = trackJson == null ? "" : trackJson;
    }
  }
}
