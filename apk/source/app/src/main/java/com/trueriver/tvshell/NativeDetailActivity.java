package com.trueriver.tvshell;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;

public class NativeDetailActivity extends Activity {
  private static final String DETAIL_STATE_PREFS = "triver_tv_detail_state";

  private LinearLayout seasonSelector;
  private LinearLayout episodeList;
  private final List<JSONObject> seriesEpisodes = new ArrayList<>();
  private final LinkedHashSet<Integer> seasonNumbers = new LinkedHashSet<>();
  private JSONArray playlistPayload = new JSONArray();
  private int selectedSeasonNumber = 0;
  private int pendingFocusPlaylistIndex = -1;
  private int libraryId = 0;
  private String itemKind = "";
  private String detailStateKey = "";
  private JSONObject sourcePayload = null;
  private View selectedSeasonButton = null;
  private View firstVisibleEpisodeButton = null;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    requestWindowFeature(Window.FEATURE_NO_TITLE);
    setContentView(R.layout.activity_native_detail);
    configureWindow();

    TextView kind = findViewById(R.id.detail_kind);
    TextView title = findViewById(R.id.detail_title);
    TextView subtitle = findViewById(R.id.detail_subtitle);
    TextView note = findViewById(R.id.detail_note);
    seasonSelector = findViewById(R.id.detail_season_selector);
    episodeList = findViewById(R.id.detail_episode_list);

    Intent intent = getIntent();
    String kindValue = intent.getStringExtra("kind");
    itemKind = kindValue == null ? "" : kindValue;
    libraryId = intent.getIntExtra("library_id", 0);
    String titleValue = intent.getStringExtra("title");
    kind.setText(kindValue);
    title.setText(titleValue);
    subtitle.setText(intent.getStringExtra("subtitle"));
    sourcePayload = parseJsonObject(intent.getStringExtra("track_json"));
    detailStateKey = buildDetailStateKey(itemKind, titleValue, sourcePayload);

    if ("series".equals(kindValue)) {
      note.setText("Select an episode to play.");
      renderSeriesEpisodes(intent.getStringExtra("track_json"));
    } else if ("album".equals(kindValue) || "artist".equals(kindValue)) {
      note.setText("Loading tracks...");
      loadAudioTracks(kindValue, sourcePayload);
    } else {
      note.setText("Native detail surface placeholder.");
    }
  }

  private String buildDetailStateKey(String kindValue, String titleValue, JSONObject payload) {
    String kind = kindValue == null ? "" : kindValue.trim();
    if (payload != null) {
      String seriesKey = payload.optString("series_key", "").trim();
      if (!seriesKey.isEmpty()) {
        return "series:" + seriesKey;
      }
      String id = payload.optString("id", "").trim();
      if (!id.isEmpty()) {
        return kind + ":" + id;
      }
    }
    String fallbackTitle = titleValue == null ? "" : titleValue.trim().toLowerCase();
    return kind + ":" + fallbackTitle;
  }

  private SharedPreferences detailStatePrefs() {
    return getSharedPreferences(DETAIL_STATE_PREFS, MODE_PRIVATE);
  }

  private int readSavedSeason() {
    if (detailStateKey.isEmpty()) {
      return 0;
    }
    return detailStatePrefs().getInt(detailStateKey + ".season", 0);
  }

  private int readSavedIndex() {
    if (detailStateKey.isEmpty()) {
      return -1;
    }
    return detailStatePrefs().getInt(detailStateKey + ".index", -1);
  }

  private void saveSelection(int seasonNumber, int playlistIndex) {
    if (detailStateKey.isEmpty()) {
      return;
    }
    SharedPreferences.Editor editor = detailStatePrefs().edit();
    if (seasonNumber > 0) {
      editor.putInt(detailStateKey + ".season", seasonNumber);
    }
    if (playlistIndex >= 0) {
      editor.putInt(detailStateKey + ".index", playlistIndex);
    } else {
      editor.remove(detailStateKey + ".index");
    }
    editor.apply();
  }

  private int firstSeasonNumber() {
    for (Integer seasonNumber : seasonNumbers) {
      return seasonNumber;
    }
    return 1;
  }

  private void requestPreferredFocus(View target) {
    if (target == null) {
      return;
    }
    target.postDelayed(() -> target.requestFocus(), 80L);
  }

  private void renderSeriesEpisodes(String payloadText) {
    seriesEpisodes.clear();
    seasonNumbers.clear();
    playlistPayload = new JSONArray();
    selectedSeasonNumber = 0;
    seasonSelector.removeAllViews();
    episodeList.removeAllViews();
    if (payloadText == null || payloadText.trim().isEmpty()) {
      episodeList.addView(buildInfo("No series payload available."));
      return;
    }

    try {
      JSONObject payload = new JSONObject(payloadText);
      JSONArray episodesArray = payload.optJSONArray("episodes");
      if ((episodesArray == null || episodesArray.length() == 0) && !payload.optString("series_key", "").isEmpty()) {
        loadSeriesTracks(payload.optString("series_key", ""));
        return;
      }
      if (episodesArray == null || episodesArray.length() == 0) {
        episodeList.addView(buildInfo("No episodes available."));
        return;
      }

      for (int index = 0; index < episodesArray.length(); index += 1) {
        JSONObject episode = episodesArray.optJSONObject(index);
        if (episode != null) {
          seriesEpisodes.add(episode);
        }
      }

      seriesEpisodes.sort(Comparator
        .comparingInt(this::episodeSeasonNumber)
        .thenComparingInt((JSONObject episode) -> episode.optInt("episode_number", 0))
        .thenComparing((JSONObject episode) -> episode.optString("canonical_title", "")));

      for (JSONObject episode : seriesEpisodes) {
        playlistPayload.put(episode);
        int seasonNumber = episodeSeasonNumber(episode);
        seasonNumbers.add(seasonNumber);
      }
      int rememberedSeason = readSavedSeason();
      selectedSeasonNumber = seasonNumbers.contains(rememberedSeason)
        ? rememberedSeason
        : firstSeasonNumber();
      pendingFocusPlaylistIndex = readSavedIndex();
      renderSeasonSelector();
      renderSelectedSeasonEpisodes();
    } catch (Exception error) {
      episodeList.addView(buildInfo(error.getMessage() == null ? "Series detail unavailable." : error.getMessage()));
    }
  }

  private void loadSeriesTracks(String seriesKey) {
    episodeList.addView(buildInfo("Loading episodes..."));
    new Thread(() -> {
      try {
        JSONArray tracks = readResultsArray(endpoint("/videos/series-tracks/?library=" + libraryId + "&series_key=" + urlEncode(seriesKey)));
        JSONObject payload = new JSONObject();
        payload.put("episodes", tracks);
        runOnUiThread(() -> renderSeriesEpisodes(payload.toString()));
      } catch (Exception error) {
        String message = error.getMessage() == null ? "Series detail unavailable." : error.getMessage();
        runOnUiThread(() -> {
          episodeList.removeAllViews();
          episodeList.addView(buildInfo(message));
        });
      }
    }).start();
  }

  private void loadAudioTracks(String kind, JSONObject item) {
    seasonSelector.setVisibility(View.GONE);
    seasonSelector.removeAllViews();
    episodeList.removeAllViews();
    episodeList.addView(buildInfo("Loading tracks..."));
    String itemId = item == null ? "" : item.optString("id", "");
    if (libraryId <= 0 || itemId.isEmpty()) {
      episodeList.removeAllViews();
      episodeList.addView(buildInfo("Missing library or item id."));
      return;
    }

    new Thread(() -> {
      try {
        String path = "/tracks/?library=" + libraryId + "&media_kind=audio&page_size=500";
        if ("album".equals(kind)) {
          path += "&album=" + urlEncode(itemId) + "&ordering=disc_number,track_number";
        } else {
          path += "&artist=" + urlEncode(itemId) + "&ordering=canonical_title";
        }
        JSONArray tracks = readResultsArray(endpoint(path));
        runOnUiThread(() -> renderAudioTracks(tracks));
      } catch (Exception error) {
        String message = error.getMessage() == null ? "Tracks unavailable." : error.getMessage();
        runOnUiThread(() -> {
          episodeList.removeAllViews();
          episodeList.addView(buildInfo(message));
        });
      }
    }).start();
  }

  private void renderAudioTracks(JSONArray tracks) {
    episodeList.removeAllViews();
    playlistPayload = new JSONArray();
    pendingFocusPlaylistIndex = readSavedIndex();
    if (tracks == null || tracks.length() == 0) {
      episodeList.addView(buildInfo("No tracks available."));
      return;
    }

    TextView header = new TextView(this);
    header.setText("Tracks");
    header.setTextColor(Color.parseColor("#F3F6F2"));
    header.setTextSize(24f);
    header.setTypeface(Typeface.DEFAULT_BOLD);
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.bottomMargin = dp(10);
    header.setLayoutParams(params);
    episodeList.addView(header);

    View firstTrackButton = null;
    View rememberedTrackButton = null;
    for (int index = 0; index < tracks.length(); index += 1) {
      JSONObject track = tracks.optJSONObject(index);
      if (track == null) {
        continue;
      }
      playlistPayload.put(track);
      View trackButton = buildTrackButton(track, index);
      if (firstTrackButton == null) {
        firstTrackButton = trackButton;
      }
      if (index == pendingFocusPlaylistIndex) {
        rememberedTrackButton = trackButton;
      }
      episodeList.addView(trackButton);
    }
    requestPreferredFocus(rememberedTrackButton != null ? rememberedTrackButton : firstTrackButton);
  }

  private void renderSeasonSelector() {
    seasonSelector.setVisibility(View.VISIBLE);
    seasonSelector.removeAllViews();
    selectedSeasonButton = null;
    for (Integer seasonNumber : seasonNumbers) {
      Button button = new Button(this);
      button.setText(seasonLabel(seasonNumber));
      button.setAllCaps(false);
      button.setTextColor(Color.parseColor("#F3F6F2"));
      button.setTextSize(15f);
      button.setFocusable(true);
      button.setBackground(buildSeasonBackground(seasonNumber == selectedSeasonNumber));
      button.setOnFocusChangeListener((view, hasFocus) -> {
        view.setBackground(buildSeasonBackground(seasonNumber == selectedSeasonNumber || hasFocus));
      });
      button.setOnClickListener((view) -> {
        selectedSeasonNumber = seasonNumber;
        pendingFocusPlaylistIndex = -1;
        saveSelection(selectedSeasonNumber, -1);
        renderSeasonSelector();
        renderSelectedSeasonEpisodes();
      });
      button.setOnKeyListener((view, keyCode, event) -> {
        if (event.getAction() == KeyEvent.ACTION_DOWN && keyCode == KeyEvent.KEYCODE_DPAD_RIGHT && firstVisibleEpisodeButton != null) {
          firstVisibleEpisodeButton.requestFocus();
          return true;
        }
        return false;
      });
      LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.WRAP_CONTENT,
        dp(46)
    );
      params.bottomMargin = dp(10);
      button.setLayoutParams(params);
      seasonSelector.addView(button);
      if (seasonNumber == selectedSeasonNumber) {
        selectedSeasonButton = button;
      }
    }
  }

  private void renderSelectedSeasonEpisodes() {
    episodeList.removeAllViews();
    TextView header = new TextView(this);
    header.setText(seasonLabel(selectedSeasonNumber));
    header.setTextColor(Color.parseColor("#F3F6F2"));
    header.setTextSize(24f);
    header.setTypeface(Typeface.DEFAULT_BOLD);
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.bottomMargin = dp(10);
    header.setLayoutParams(params);
    episodeList.addView(header);

    View firstEpisodeButton = null;
    View rememberedEpisodeButton = null;
    firstVisibleEpisodeButton = null;
    for (int index = 0; index < seriesEpisodes.size(); index += 1) {
      JSONObject episode = seriesEpisodes.get(index);
      if (episodeSeasonNumber(episode) == selectedSeasonNumber) {
        View episodeButton = buildEpisodeButton(episode, index);
        if (firstEpisodeButton == null) {
          firstEpisodeButton = episodeButton;
        }
        if (index == pendingFocusPlaylistIndex) {
          rememberedEpisodeButton = episodeButton;
        }
        episodeList.addView(episodeButton);
      }
    }
    firstVisibleEpisodeButton = firstEpisodeButton;
    requestPreferredFocus(rememberedEpisodeButton != null ? rememberedEpisodeButton : firstEpisodeButton);
  }

  private View buildEpisodeButton(JSONObject episode, int playlistIndex) {
    LinearLayout button = new LinearLayout(this);
    button.setOrientation(LinearLayout.VERTICAL);
    button.setFocusable(true);
    button.setClickable(true);
    button.setPadding(dp(18), dp(18), dp(18), dp(18));
    button.setBackground(buildCardBackground(false));
    button.setOnFocusChangeListener((view, hasFocus) -> {
      view.setBackground(buildCardBackground(hasFocus));
      view.animate()
        .scaleX(hasFocus ? 1.02f : 1.0f)
        .scaleY(hasFocus ? 1.02f : 1.0f)
        .setDuration(120L)
        .start();
      if (hasFocus) {
        saveSelection(selectedSeasonNumber, playlistIndex);
      }
    });
    button.setOnClickListener((view) -> {
      saveSelection(selectedSeasonNumber, playlistIndex);
      openEpisode(episode, playlistIndex);
    });
    button.setOnKeyListener((view, keyCode, event) -> {
      if (event.getAction() == KeyEvent.ACTION_DOWN && keyCode == KeyEvent.KEYCODE_DPAD_LEFT && selectedSeasonButton != null) {
        selectedSeasonButton.requestFocus();
        return true;
      }
      return false;
    });

    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.bottomMargin = dp(12);
    button.setLayoutParams(params);

    TextView title = new TextView(this);
    title.setText(buildEpisodeTitle(episode));
    title.setTextColor(Color.parseColor("#F3F6F2"));
    title.setTextSize(19f);
    title.setTypeface(Typeface.DEFAULT_BOLD);
    button.addView(title);

    TextView subtitle = new TextView(this);
    subtitle.setText(buildEpisodeSubtitle(episode));
    subtitle.setTextColor(Color.parseColor("#A6B4AE"));
    subtitle.setTextSize(14f);
    LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    subtitleParams.topMargin = dp(10);
    subtitle.setLayoutParams(subtitleParams);
    button.addView(subtitle);

    return button;
  }

  private View buildTrackButton(JSONObject track, int playlistIndex) {
    LinearLayout button = new LinearLayout(this);
    button.setOrientation(LinearLayout.VERTICAL);
    button.setFocusable(true);
    button.setClickable(true);
    button.setPadding(dp(18), dp(18), dp(18), dp(18));
    button.setBackground(buildCardBackground(false));
    button.setOnFocusChangeListener((view, hasFocus) -> {
      view.setBackground(buildCardBackground(hasFocus));
      view.animate()
        .scaleX(hasFocus ? 1.02f : 1.0f)
        .scaleY(hasFocus ? 1.02f : 1.0f)
        .setDuration(120L)
        .start();
      if (hasFocus) {
        saveSelection(0, playlistIndex);
      }
    });
    button.setOnClickListener((view) -> {
      saveSelection(0, playlistIndex);
      openTrack(track, playlistIndex);
    });

    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.bottomMargin = dp(12);
    button.setLayoutParams(params);

    TextView title = new TextView(this);
    title.setText(buildTrackTitle(track));
    title.setTextColor(Color.parseColor("#F3F6F2"));
    title.setTextSize(19f);
    title.setTypeface(Typeface.DEFAULT_BOLD);
    button.addView(title);

    TextView subtitle = new TextView(this);
    subtitle.setText(buildTrackSubtitle(track));
    subtitle.setTextColor(Color.parseColor("#A6B4AE"));
    subtitle.setTextSize(14f);
    LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    subtitleParams.topMargin = dp(10);
    subtitle.setLayoutParams(subtitleParams);
    button.addView(subtitle);

    return button;
  }

  private void openEpisode(JSONObject episode, int playlistIndex) {
    String playbackPath = episode.optString("playback_url", episode.optString("stream_url", ""));
    if (playbackPath == null || playbackPath.isEmpty()) {
      return;
    }
    Intent playerIntent = new Intent(this, NativePlayerActivity.class);
    playerIntent.putExtra("title", buildEpisodeTitle(episode));
    playerIntent.putExtra("subtitle", buildEpisodeSubtitle(episode));
    playerIntent.putExtra("playback_path", playbackPath);
    playerIntent.putExtra("track_json", episode.toString());
    playerIntent.putExtra("playlist_json", playlistPayload.toString());
    playerIntent.putExtra("playlist_index", playlistIndex);
    playerIntent.putExtra("playlist_mode", "series");
    startActivity(playerIntent);
  }

  private void openTrack(JSONObject track, int playlistIndex) {
    String playbackPath = track.optString("playback_url", track.optString("stream_url", ""));
    if (playbackPath == null || playbackPath.isEmpty()) {
      return;
    }
    Intent playerIntent = new Intent(this, NativePlayerActivity.class);
    playerIntent.putExtra("title", buildTrackTitle(track));
    playerIntent.putExtra("subtitle", buildTrackSubtitle(track));
    playerIntent.putExtra("playback_path", playbackPath);
    playerIntent.putExtra("track_json", track.toString());
    playerIntent.putExtra("playlist_json", playlistPayload.toString());
    playerIntent.putExtra("playlist_index", playlistIndex);
    playerIntent.putExtra("playlist_mode", "audio");
    startActivity(playerIntent);
  }

  private String seasonLabel(int seasonNumber) {
    return "Season " + Math.max(seasonNumber, 1);
  }

  private int episodeSeasonNumber(JSONObject episode) {
    return Math.max(episode.optInt("season_number", 1), 1);
  }

  private GradientDrawable buildSeasonBackground(boolean selected) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(selected ? "#1C3228" : "#101916"));
    drawable.setCornerRadius(dp(6));
    drawable.setStroke(dp(2), Color.parseColor(selected ? "#9FD4B7" : "#22332B"));
    return drawable;
  }

  private String buildEpisodeTitle(JSONObject episode) {
    int season = episodeSeasonNumber(episode);
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

  private String buildTrackTitle(JSONObject track) {
    int discNumber = track.optInt("disc_number", 0);
    int trackNumber = track.optInt("track_number", 0);
    String title = track.optString("canonical_title", track.optString("title", "Untitled Track")).trim();
    if (trackNumber <= 0) {
      return title.isEmpty() ? "Untitled Track" : title;
    }
    String prefix = discNumber > 0
      ? discNumber + "." + String.format("%02d", trackNumber) + " "
      : String.format("%02d", trackNumber) + " ";
    return prefix + (title.isEmpty() ? "Untitled Track" : title);
  }

  private String buildTrackSubtitle(JSONObject track) {
    List<String> bits = new ArrayList<>();
    String albumTitle = track.optString("album_title", "").trim();
    String mediaKind = track.optString("media_kind", "").trim();
    if (!albumTitle.isEmpty()) {
      bits.add(albumTitle);
    }
    if (!mediaKind.isEmpty()) {
      bits.add(mediaKind);
    }
    if (bits.isEmpty()) {
      bits.add("Track");
    }
    return joinBits(bits);
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

  private JSONArray readResultsArray(String url) throws Exception {
    JSONObject payload = readJsonObject(url);
    JSONArray results = payload.optJSONArray("results");
    if (results != null) {
      return results;
    }
    JSONArray direct = new JSONArray();
    if (payload.has("id")) {
      direct.put(payload);
    }
    return direct;
  }

  private JSONObject readJsonObject(String url) throws Exception {
    HttpURLConnection connection = null;
    InputStream inputStream = null;
    try {
      connection = (HttpURLConnection) new URL(url).openConnection();
      connection.setRequestMethod("GET");
      connection.setConnectTimeout(10000);
      connection.setReadTimeout(18000);
      connection.setRequestProperty("Accept", "application/json");
      connection.setRequestProperty("User-Agent", BuildConfig.TV_USER_AGENT_SUFFIX);
      TvConnectionConfig.load(this).applyHeaders(connection);
      connection.connect();

      int status = connection.getResponseCode();
      inputStream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
      if (inputStream == null) {
        throw new IllegalStateException("No response body from " + url);
      }
      String body = readFully(inputStream);
      if (status < 200 || status >= 300) {
        throw new IllegalStateException("HTTP " + status + " from " + url);
      }
      String trimmed = body.trim();
      if (trimmed.startsWith("[")) {
        JSONObject wrapper = new JSONObject();
        wrapper.put("results", new JSONArray(trimmed));
        return wrapper;
      }
      return new JSONObject(trimmed);
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

  private String endpoint(String path) {
    return TvConnectionConfig.load(this).apiBaseUrl() + path;
  }

  private String urlEncode(String value) throws Exception {
    return URLEncoder.encode(value, StandardCharsets.UTF_8.name());
  }

  private View buildInfo(String message) {
    TextView info = new TextView(this);
    info.setText(message);
    info.setTextColor(Color.parseColor("#D2DAD5"));
    info.setTextSize(18f);
    return info;
  }

  @Override
  protected void onResume() {
    super.onResume();
    enterImmersiveMode();
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
    return super.dispatchKeyEvent(event);
  }

  private void configureWindow() {
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    enterImmersiveMode();
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

  private GradientDrawable buildCardBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(focused ? "#1C3228" : "#101916"));
    drawable.setCornerRadius(dp(14));
    drawable.setStroke(dp(2), Color.parseColor(focused ? "#9FD4B7" : "#22332B"));
    return drawable;
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

  private int dp(int value) {
    return Math.round(value * getResources().getDisplayMetrics().density);
  }
}
