package com.trueriver.tvshell;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.LruCache;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
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
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class NativeHomeActivity extends Activity {
  private static final int VIDEO_SECTION_PAGE_SIZE = 18;
  private static final String ROW_END_CARD_TAG = "triver-row-end-card";
  private static final ExecutorService IMAGE_EXECUTOR = Executors.newFixedThreadPool(3);
  private static final LruCache<String, Bitmap> IMAGE_CACHE = new LruCache<String, Bitmap>(12 * 1024) {
    @Override
    protected int sizeOf(String key, Bitmap value) {
      return Math.max(1, value.getByteCount() / 1024);
    }
  };

  private enum Mode {
    VIDEO,
    AUDIO,
    SETTINGS
  }

  private enum AudioBrowse {
    ARTISTS,
    ALBUMS,
    TRACKS
  }

  private TextView contentTitle;
  private TextView contentStatus;
  private LinearLayout sidebar;
  private TextView sidebarTab;
  private LinearLayout rowsContainer;
  private FrameLayout contentFrame;
  private FrameLayout heroHost;
  private ScrollView contentScroll;
  private ProgressBar loadingSpinner;
  private ImageButton navVideo;
  private ImageButton navAudio;
  private ImageButton navSearch;
  private ImageButton navSettings;
  private ImageView heroImage;
  private TextView heroEyebrow;
  private TextView heroTitle;
  private TextView heroDescription;
  private TextView heroMeta;
  private TvScreensaverView screensaverView;
  private Mode currentMode = Mode.VIDEO;
  private AudioBrowse activeAudioBrowse = AudioBrowse.ARTISTS;
  private boolean sidebarVisible = true;
  private String activeSearchTerm = "";
  private String activeJumpKey = "";
  private int currentLibraryId = 0;
  private boolean screensaverVisible = false;
  private final Handler uiHandler = new Handler(Looper.getMainLooper());
  private final Runnable screensaverRunnable = this::showScreensaver;
  private List<CardSection> currentVideoSections = new ArrayList<>();

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    requestWindowFeature(Window.FEATURE_NO_TITLE);
    setContentView(R.layout.activity_native_home);
    bindViews();
    configureWindow();
    configureNavigation();
    switchMode(Mode.VIDEO);
  }

  @Override
  protected void onResume() {
    super.onResume();
    enterImmersiveMode();
    resetScreensaverTimer();
  }

  @Override
  protected void onPause() {
    uiHandler.removeCallbacks(screensaverRunnable);
    hideScreensaver(false);
    super.onPause();
  }

  @Override
  public void onUserInteraction() {
    super.onUserInteraction();
    resetScreensaverTimer();
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
    if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT && isCurrentFocusAtRowEnd()) {
      return true;
    }
    if (event.getAction() == KeyEvent.ACTION_DOWN) {
      if (screensaverVisible) {
        hideScreensaver(true);
        return true;
      }
      resetScreensaverTimer();
    }
    if (event.getKeyCode() == KeyEvent.KEYCODE_BACK && event.getAction() == KeyEvent.ACTION_DOWN) {
      if (!sidebarVisible) {
        showSidebarAndFocusActiveButton();
        return true;
      }
      finishAffinity();
      return true;
    }
    return super.dispatchKeyEvent(event);
  }

  private boolean isCurrentFocusAtRowEnd() {
    View focus = getCurrentFocus();
    return focus != null && ROW_END_CARD_TAG.equals(focus.getTag());
  }

  private void bindViews() {
    contentTitle = findViewById(R.id.content_title);
    contentStatus = findViewById(R.id.content_status);
    sidebar = findViewById(R.id.sidebar);
    sidebarTab = findViewById(R.id.sidebar_tab);
    rowsContainer = findViewById(R.id.rows_container);
    contentFrame = findViewById(R.id.content_frame);
    heroHost = findViewById(R.id.hero_host);
    contentScroll = findViewById(R.id.content_scroll);
    loadingSpinner = findViewById(R.id.loading_spinner);
    navVideo = findViewById(R.id.nav_video);
    navAudio = findViewById(R.id.nav_audio);
    navSearch = null;
    navSettings = findViewById(R.id.nav_settings);
  }

  private void configureWindow() {
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    disableClipping(contentFrame);
    disableClipping(contentScroll);
    disableClipping(rowsContainer);
    enterImmersiveMode();
  }

  private void disableClipping(View view) {
    if (view instanceof ViewGroup) {
      ViewGroup group = (ViewGroup) view;
      group.setClipChildren(false);
      group.setClipToPadding(false);
    }
  }

  private void configureNavigation() {
    if (sidebar != null) {
      sidebar.setBackground(buildSidebarBackground());
    }
    if (sidebarTab != null) {
      sidebarTab.setBackground(buildSidebarTabBackground(false));
      sidebarTab.setVisibility(View.GONE);
      sidebarTab.setOnClickListener((view) -> showSidebarAndFocusActiveButton());
      sidebarTab.setOnFocusChangeListener((view, hasFocus) -> sidebarTab.setBackground(buildSidebarTabBackground(hasFocus)));
      sidebarTab.setOnKeyListener((view, keyCode, event) -> {
        if (event.getAction() != KeyEvent.ACTION_DOWN) {
          return false;
        }
        if (
          keyCode == KeyEvent.KEYCODE_DPAD_RIGHT
            || keyCode == KeyEvent.KEYCODE_ENTER
            || keyCode == KeyEvent.KEYCODE_DPAD_CENTER
        ) {
          showSidebarAndFocusActiveButton();
          return true;
        }
        return false;
      });
    }
    updateNavStyles();
    if (navSearch != null) {
      navSearch.setVisibility(View.GONE);
    }

    navVideo.setOnClickListener((view) -> switchMode(Mode.VIDEO));
    navAudio.setOnClickListener((view) -> switchMode(Mode.AUDIO));
    if (navSettings != null) {
      navSettings.setOnClickListener((view) -> switchMode(Mode.SETTINGS));
    }
    configureSidebarExit(navVideo);
    configureSidebarExit(navAudio);
    configureSidebarExit(navSettings);
  }

  private void configureSidebarExit(View button) {
    if (button == null) {
      return;
    }
    button.setOnKeyListener((view, keyCode, event) -> {
      if (event.getAction() != KeyEvent.ACTION_DOWN || keyCode != KeyEvent.KEYCODE_DPAD_RIGHT) {
        return false;
      }
      focusFirstContentItem();
      return true;
    });
  }

  private boolean focusFirstContentItem() {
    View target = firstFocusableDescendant(rowsContainer);
    if (target == null) {
      return false;
    }
    if (sidebarVisible) {
      hideSidebar();
    }
    target.requestFocus();
    return true;
  }

  private View firstFocusableDescendant(View view) {
    if (view == null || view.getVisibility() != View.VISIBLE) {
      return null;
    }
    if (view.isFocusable() && view.isEnabled()) {
      return view;
    }
    if (!(view instanceof ViewGroup)) {
      return null;
    }
    ViewGroup group = (ViewGroup) view;
    for (int index = 0; index < group.getChildCount(); index += 1) {
      View match = firstFocusableDescendant(group.getChildAt(index));
      if (match != null) {
        return match;
      }
    }
    return null;
  }

  private void switchMode(Mode mode) {
    currentMode = mode;
    activeSearchTerm = "";
    activeJumpKey = "";
    resetVideoPaging();
    updateNavStyles();
    if (mode == Mode.SETTINGS) {
      renderSettings();
      return;
    }
    loadCurrentSurface();
  }

  private void loadCurrentSurface() {
    updateNavStyles();

    if (!TvConnectionConfig.isConfigured(this)) {
      renderConnectionConfig("", true);
      return;
    }

    rowsContainer.removeAllViews();
    loadingSpinner.setVisibility(View.VISIBLE);

    new Thread(() -> {
      try {
        currentLibraryId = resolveLibraryId();
        if (currentMode == Mode.VIDEO) {
          List<CardSection> sections = buildVideoSections(currentLibraryId);
          runOnUiThread(() -> renderVideoBrowser(sections));
          return;
        }
        List<CardItem> items = buildAudioItems(currentLibraryId);
        runOnUiThread(() -> renderBrowser(items));
      } catch (Exception error) {
        String message = error.getMessage() == null ? "Unable to load library." : error.getMessage();
        runOnUiThread(() -> renderConnectionConfig(message, false));
      }
    }).start();
  }

  private void renderBrowser(List<CardItem> items) {
    loadingSpinner.setVisibility(View.GONE);
    rowsContainer.removeAllViews();
    setStickyHero(buildPreviewHeader(items.isEmpty() ? null : items.get(0)));
    if (currentMode == Mode.AUDIO) {
      rowsContainer.addView(buildBrowseSelector());
    }
    rowsContainer.addView(buildCardRow(items));
  }

  private void renderVideoBrowser(List<CardSection> sections) {
    loadingSpinner.setVisibility(View.GONE);
    currentVideoSections = sections == null ? new ArrayList<>() : sections;
    rowsContainer.removeAllViews();
    setStickyHero(buildPreviewHeader(firstSectionItem(currentVideoSections)));
    if (currentVideoSections.isEmpty()) {
      rowsContainer.addView(buildCardRow(new ArrayList<>()));
      return;
    }
    for (CardSection section : currentVideoSections) {
      rowsContainer.addView(buildSectionTitle(section.title));
      for (List<CardItem> rowItems : section.rows) {
        rowsContainer.addView(buildCardRow(rowItems));
      }
      if (section.loading) {
        rowsContainer.addView(buildLoadingPlaceholderRow());
      } else if (section.errorMessage != null && !section.errorMessage.trim().isEmpty()) {
        rowsContainer.addView(buildSectionStatusRow("Load failed", section.errorMessage));
      }
      if (!section.loading && section.hasMore()) {
        rowsContainer.addView(buildSectionLoadMoreAction(section));
      }
    }
  }

  private void setStickyHero(View hero) {
    if (heroHost == null || contentScroll == null) {
      return;
    }
    heroHost.removeAllViews();
    heroHost.addView(hero);
    heroHost.setVisibility(View.VISIBLE);
    ViewGroup.LayoutParams hostParams = heroHost.getLayoutParams();
    hostParams.height = dp(244);
    heroHost.setLayoutParams(hostParams);
    FrameLayout.LayoutParams scrollParams = (FrameLayout.LayoutParams) contentScroll.getLayoutParams();
    scrollParams.topMargin = dp(244);
    contentScroll.setLayoutParams(scrollParams);
    rowsContainer.setPadding(0, dp(10), 0, dp(44));
  }

  private void clearStickyHero() {
    if (heroHost != null) {
      heroHost.removeAllViews();
      heroHost.setVisibility(View.GONE);
    }
    if (contentScroll != null) {
      FrameLayout.LayoutParams scrollParams = (FrameLayout.LayoutParams) contentScroll.getLayoutParams();
      scrollParams.topMargin = 0;
      contentScroll.setLayoutParams(scrollParams);
    }
    if (rowsContainer != null) {
      rowsContainer.setPadding(0, 0, 0, 0);
    }
  }

  private CardItem firstSectionItem(List<CardSection> sections) {
    for (CardSection section : sections) {
      for (List<CardItem> row : section.rows) {
        if (!row.isEmpty()) {
          return row.get(0);
        }
      }
    }
    return null;
  }

  private String statusLabel(int count) {
    String label = activeSectionTitle();
    StringBuilder builder = new StringBuilder();
    builder.append(label).append(" · ").append(count).append(count == 1 ? " item" : " items");
    if (!activeSearchTerm.trim().isEmpty()) {
      builder.append(" · search: ").append(activeSearchTerm.trim());
    }
    if (!activeJumpKey.isEmpty()) {
      builder.append(" · jump: ").append(activeJumpKey);
    }
    return builder.toString();
  }

  private String activeSectionTitle() {
    if (currentMode == Mode.AUDIO) {
      if (activeAudioBrowse == AudioBrowse.ALBUMS) {
        return "Albums";
      }
      if (activeAudioBrowse == AudioBrowse.TRACKS) {
        return "Tracks";
      }
      return "Artists";
    }
    return "Videos";
  }

  private View buildSearchControls() {
    LinearLayout controls = new LinearLayout(this);
    controls.setOrientation(LinearLayout.HORIZONTAL);
    controls.setPadding(0, 0, 0, dp(18));

    EditText searchInput = new EditText(this);
    searchInput.setHint(currentMode == Mode.VIDEO ? "Search video" : "Search audio");
    searchInput.setText(activeSearchTerm);
    searchInput.setSingleLine(true);
    searchInput.setTextColor(Color.parseColor("#F3F6F2"));
    searchInput.setHintTextColor(Color.parseColor("#77887F"));
    searchInput.setTextSize(18f);
    searchInput.setSelectAllOnFocus(true);
    searchInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_NORMAL);
    searchInput.setPadding(dp(14), dp(8), dp(14), dp(8));
    searchInput.setBackground(buildInputBackground(false));
    searchInput.setOnFocusChangeListener((view, hasFocus) -> searchInput.setBackground(buildInputBackground(hasFocus)));
    searchInput.setOnEditorActionListener((view, actionId, event) -> {
      if (event != null && event.getAction() != KeyEvent.ACTION_DOWN) {
        return false;
      }
      activeSearchTerm = searchInput.getText().toString();
      resetVideoPaging();
      loadCurrentSurface();
      return true;
    });
    LinearLayout.LayoutParams inputParams = new LinearLayout.LayoutParams(dp(420), dp(52));
    inputParams.rightMargin = dp(12);
    searchInput.setLayoutParams(inputParams);
    controls.addView(searchInput);

    Button searchButton = buildActionButton("Search");
    searchButton.setOnClickListener((view) -> {
      activeSearchTerm = searchInput.getText().toString();
      resetVideoPaging();
      loadCurrentSurface();
    });
    controls.addView(searchButton);

    Button clearButton = buildActionButton("Clear");
    clearButton.setOnClickListener((view) -> {
      activeSearchTerm = "";
      activeJumpKey = "";
      resetVideoPaging();
      loadCurrentSurface();
    });
    controls.addView(clearButton);

    Button configButton = buildActionButton("Connection");
    configButton.setOnClickListener((view) -> renderConnectionConfig("", false));
    controls.addView(configButton);

    return controls;
  }

  private View buildBrowseSelector() {
    LinearLayout selector = new LinearLayout(this);
    selector.setOrientation(LinearLayout.HORIZONTAL);
    selector.setPadding(dp(104), 0, dp(28), dp(16));
    LinearLayout.LayoutParams selectorParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    selectorParams.topMargin = dp(2);
    selector.setLayoutParams(selectorParams);

    selector.addView(buildSelectorButton("Artists", activeAudioBrowse == AudioBrowse.ARTISTS, () -> {
      activeAudioBrowse = AudioBrowse.ARTISTS;
      activeJumpKey = "";
      resetVideoPaging();
      loadCurrentSurface();
    }));
    selector.addView(buildSelectorButton("Albums", activeAudioBrowse == AudioBrowse.ALBUMS, () -> {
      activeAudioBrowse = AudioBrowse.ALBUMS;
      activeJumpKey = "";
      resetVideoPaging();
      loadCurrentSurface();
    }));
    selector.addView(buildSelectorButton("Tracks", activeAudioBrowse == AudioBrowse.TRACKS, () -> {
      activeAudioBrowse = AudioBrowse.TRACKS;
      activeJumpKey = "";
      resetVideoPaging();
      loadCurrentSurface();
    }));
    return selector;
  }

  private Button buildSelectorButton(String label, boolean selected, Runnable action) {
    Button button = buildActionButton(label);
    button.setBackground(buildSelectorBackground(selected, false));
    button.setOnFocusChangeListener((view, hasFocus) -> button.setBackground(buildSelectorBackground(selected, hasFocus)));
    button.setOnClickListener((view) -> action.run());
    return button;
  }

  private View buildJumpRow() {
    HorizontalScrollView scrollView = new HorizontalScrollView(this);
    scrollView.setHorizontalScrollBarEnabled(false);
    LinearLayout row = new LinearLayout(this);
    row.setOrientation(LinearLayout.HORIZONTAL);

    String[] keys = new String[]{"All", "#", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"};
    for (String key : keys) {
      boolean selected = ("All".equals(key) && activeJumpKey.isEmpty()) || key.equals(activeJumpKey);
      Button button = buildSelectorButton(key, selected, () -> {
        activeJumpKey = "All".equals(key) ? "" : key;
        resetVideoPaging();
        loadCurrentSurface();
      });
      LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp("All".equals(key) ? 70 : 48), dp(44));
      params.rightMargin = dp(8);
      button.setLayoutParams(params);
      row.addView(button);
    }
    scrollView.addView(row);
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.bottomMargin = dp(18);
    scrollView.setLayoutParams(params);
    return scrollView;
  }

  private TextView buildSectionTitle(String title) {
    TextView view = new TextView(this);
    view.setText(title);
    view.setTextColor(Color.parseColor("#F3F6F2"));
    view.setTextSize(currentMode == Mode.VIDEO ? 19f : 22f);
    view.setTypeface(Typeface.DEFAULT_BOLD);
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.leftMargin = contentStartMargin();
    params.topMargin = currentMode == Mode.VIDEO ? dp(8) : dp(16);
    params.bottomMargin = currentMode == Mode.VIDEO ? dp(3) : dp(10);
    view.setLayoutParams(params);
    return view;
  }

  private View buildCardRow(List<CardItem> items) {
    HorizontalScrollView scrollView = new HorizontalScrollView(this);
    scrollView.setHorizontalScrollBarEnabled(false);
    scrollView.setFillViewport(false);
    scrollView.setFocusable(false);
    scrollView.setClipChildren(false);
    scrollView.setClipToPadding(false);

    LinearLayout row = new LinearLayout(this);
    row.setOrientation(LinearLayout.HORIZONTAL);
    row.setFocusable(false);
    row.setClipChildren(false);
    row.setClipToPadding(false);
    row.setPadding(contentStartMargin(), dp(16), dp(28), dp(16));
    if (items.isEmpty()) {
      row.addView(buildInfoBlock("No items", "Try another search or jump key."));
    } else {
      for (int index = 0; index < items.size(); index += 1) {
        row.addView(buildCard(items.get(index), index == 0, index == items.size() - 1));
      }
    }
    scrollView.addView(row);

    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.bottomMargin = currentMode == Mode.VIDEO ? dp(2) : dp(16);
    scrollView.setLayoutParams(params);
    return scrollView;
  }

  private View buildSectionLoadMoreAction(CardSection section) {
    LinearLayout wrapper = new LinearLayout(this);
    wrapper.setOrientation(LinearLayout.HORIZONTAL);
    wrapper.setPadding(contentStartMargin(), 0, dp(28), dp(18));

    Button button = buildActionButton("Load more");
    button.setId(View.generateViewId());
    button.setNextFocusRightId(button.getId());
    button.setText("Load more · next " + VIDEO_SECTION_PAGE_SIZE);
    button.setOnClickListener((view) -> loadMoreVideoSection(section));
    button.setOnFocusChangeListener((view, hasFocus) -> {
      button.setBackground(buildButtonBackground(hasFocus));
      if (hasFocus) {
        if (sidebarVisible) {
          hideSidebar();
        }
        updatePreviewHeader(new CardItem("action", "Load more", "Show the next row for " + section.title + ".", "Show the next row for " + section.title + ".", "", "", ""), true);
      }
    });
    button.setOnKeyListener((view, keyCode, event) -> {
      if (event.getAction() != KeyEvent.ACTION_DOWN) {
        return false;
      }
      if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
        return true;
      }
      if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT && !sidebarVisible) {
        showSidebarAndFocusActiveButton();
        return true;
      }
      if (keyCode == KeyEvent.KEYCODE_BACK && !sidebarVisible) {
        showSidebarAndFocusActiveButton();
        return true;
      }
      return false;
    });
    wrapper.addView(button);
    return wrapper;
  }

  private View buildLoadingPlaceholderRow() {
    LinearLayout row = new LinearLayout(this);
    row.setOrientation(LinearLayout.HORIZONTAL);
    row.setGravity(android.view.Gravity.CENTER_VERTICAL);
    row.setPadding(contentStartMargin(), dp(14), dp(28), dp(18));

    ProgressBar spinner = new ProgressBar(this);
    LinearLayout.LayoutParams spinnerParams = new LinearLayout.LayoutParams(dp(38), dp(38));
    spinnerParams.rightMargin = dp(14);
    spinner.setLayoutParams(spinnerParams);
    row.addView(spinner);

    TextView label = new TextView(this);
    label.setText("Loading next row");
    label.setTextColor(Color.parseColor("#D8E1DC"));
    label.setTextSize(15f);
    label.setTypeface(Typeface.DEFAULT_BOLD);
    row.addView(label);
    return row;
  }

  private View buildSectionStatusRow(String title, String message) {
    LinearLayout row = new LinearLayout(this);
    row.setOrientation(LinearLayout.VERTICAL);
    row.setPadding(contentStartMargin(), dp(8), dp(28), dp(18));

    TextView titleView = new TextView(this);
    titleView.setText(title);
    titleView.setTextColor(Color.parseColor("#F3F6F2"));
    titleView.setTextSize(15f);
    titleView.setTypeface(Typeface.DEFAULT_BOLD);
    row.addView(titleView);

    TextView messageView = new TextView(this);
    messageView.setText(message);
    messageView.setTextColor(Color.parseColor("#A6B4AE"));
    messageView.setTextSize(13f);
    messageView.setMaxLines(2);
    row.addView(messageView);
    return row;
  }

  private void animateRowsForFocusedCard(View focusedCard) {
    if (rowsContainer == null) {
      return;
    }
    View rowView = focusedCard;
    while (rowView != null && !(rowView instanceof HorizontalScrollView)) {
      Object parent = rowView.getParent();
      rowView = parent instanceof View ? (View) parent : null;
    }
    if (rowView == null) {
      return;
    }
    int focusedIndex = rowsContainer.indexOfChild(rowView);
    if (focusedIndex < 0) {
      return;
    }
    int titleIndex = Math.max(0, focusedIndex - 1);
    for (int index = 0; index < rowsContainer.getChildCount(); index += 1) {
      View child = rowsContainer.getChildAt(index);
      boolean current = index == focusedIndex || index == titleIndex;
      boolean before = index < titleIndex;
      float targetAlpha = current ? 1f : before ? 0.14f : 0.72f;
      float targetTranslation = current ? 0f : before ? -dp(22) : dp(6);
      child.animate()
        .alpha(targetAlpha)
        .translationY(targetTranslation)
        .setDuration(180L)
        .start();
    }
  }

  private int contentStartMargin() {
    return currentMode == Mode.VIDEO ? dp(72) : dp(104);
  }

  private View buildCard(CardItem item, boolean isRowStart, boolean isRowEnd) {
    LinearLayout card = new LinearLayout(this);
    card.setId(View.generateViewId());
    card.setOrientation(LinearLayout.VERTICAL);
    card.setFocusable(true);
    card.setClickable(true);
    card.setTag(isRowEnd ? ROW_END_CARD_TAG : "");
    if (isRowEnd) {
      card.setNextFocusRightId(card.getId());
    }
    boolean videoCard = currentMode == Mode.VIDEO;
    card.setPadding(videoCard ? dp(3) : 0, videoCard ? dp(3) : 0, videoCard ? dp(3) : 0, videoCard ? dp(3) : dp(12));
    card.setBackground(videoCard ? buildVideoCardBackground(false) : buildCardBackground(false));
    card.setOnFocusChangeListener((view, hasFocus) -> {
      view.setBackground(videoCard ? buildVideoCardBackground(hasFocus) : buildCardBackground(hasFocus));
      view.setTranslationZ(hasFocus ? dp(18) : 0);
      float focusedScale = videoCard ? 1.18f : 1.08f;
      view.animate()
        .scaleX(hasFocus ? focusedScale : 1.0f)
        .scaleY(hasFocus ? focusedScale : 1.0f)
        .setDuration(120L)
        .start();
      if (hasFocus) {
        if (sidebarVisible) {
          hideSidebar();
        }
        animateRowsForFocusedCard(view);
        updatePreviewHeader(item, true);
      }
    });
    card.setOnClickListener((view) -> openDetails(item));
    card.setOnKeyListener((view, keyCode, event) -> {
      if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT && isRowEnd) {
        return true;
      }
      if (event.getAction() != KeyEvent.ACTION_DOWN) {
        return false;
      }
      if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT && isRowStart && !sidebarVisible) {
        showSidebarAndFocusActiveButton();
        return true;
      }
      if (keyCode == KeyEvent.KEYCODE_BACK && !sidebarVisible) {
        showSidebarAndFocusActiveButton();
        return true;
      }
      return false;
    });

    int cardWidth = videoCard ? dp(210) : dp(236);
    int cardHeight = videoCard ? dp(118) : dp(236);
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(cardWidth, cardHeight);
    params.rightMargin = dp(16);
    card.setLayoutParams(params);

    FrameLayout posterShell = new FrameLayout(this);
    posterShell.setBackground(videoCard ? buildVideoPosterBackground() : buildPosterBackground());
    LinearLayout.LayoutParams posterParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      videoCard ? ViewGroup.LayoutParams.MATCH_PARENT : dp(142)
    );
    posterShell.setLayoutParams(posterParams);

    ImageView poster = new ImageView(this);
    poster.setScaleType(ImageView.ScaleType.CENTER_CROP);
    poster.setAlpha(videoCard && !item.playbackCacheReady ? 0.36f : 1f);
    poster.setBackgroundColor(Color.parseColor("#050807"));
    poster.setLayoutParams(new FrameLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.MATCH_PARENT
    ));
    posterShell.addView(poster);
    if (item.coverUrl != null && !item.coverUrl.trim().isEmpty()) {
      loadImageInto(poster, item.coverUrl);
    }

    TextView badge = buildMediaBadge(item.kind);
    FrameLayout.LayoutParams badgeParams = new FrameLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    if (videoCard) {
      badgeParams.gravity = android.view.Gravity.BOTTOM | android.view.Gravity.RIGHT;
      badgeParams.rightMargin = dp(10);
      badgeParams.bottomMargin = dp(10);
    } else {
      badgeParams.leftMargin = dp(12);
      badgeParams.topMargin = dp(12);
    }
    posterShell.addView(badge, badgeParams);
    card.addView(posterShell);

    if (videoCard) {
      TextView videoTitle = new TextView(this);
      videoTitle.setText(item.title);
      videoTitle.setTextColor(Color.parseColor("#F3F6F2"));
      videoTitle.setTextSize(14f);
      videoTitle.setTypeface(Typeface.DEFAULT_BOLD);
      videoTitle.setMaxLines(2);
      videoTitle.setPadding(dp(10), dp(7), dp(10), dp(7));
      videoTitle.setBackground(buildVideoTitleOverlayBackground());
      FrameLayout.LayoutParams videoTitleParams = new FrameLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT
      );
      videoTitleParams.gravity = android.view.Gravity.TOP | android.view.Gravity.LEFT;
      posterShell.addView(videoTitle, videoTitleParams);
      if (!item.playbackCacheReady) {
        TextView preparing = new TextView(this);
        String label = item.playbackProgressPercent > 0
          ? "Preparing " + item.playbackProgressPercent + "%"
          : "Preparing";
        preparing.setText(label);
        preparing.setTextColor(Color.parseColor("#F3F6F2"));
        preparing.setTextSize(13f);
        preparing.setTypeface(Typeface.DEFAULT_BOLD);
        preparing.setPadding(dp(10), dp(5), dp(10), dp(5));
        preparing.setBackground(buildPreparingOverlayBackground());
        FrameLayout.LayoutParams preparingParams = new FrameLayout.LayoutParams(
          ViewGroup.LayoutParams.WRAP_CONTENT,
          ViewGroup.LayoutParams.WRAP_CONTENT
        );
        preparingParams.gravity = android.view.Gravity.CENTER;
        posterShell.addView(preparing, preparingParams);
      }
      return card;
    }

    TextView title = new TextView(this);
    title.setText(item.title);
    title.setTextColor(Color.parseColor("#F3F6F2"));
    title.setTextSize(currentMode == Mode.VIDEO ? 18f : 17f);
    title.setTypeface(Typeface.DEFAULT_BOLD);
    title.setMaxLines(2);
    title.setPadding(dp(14), dp(12), dp(14), 0);
    card.addView(title);

    TextView subtitle = new TextView(this);
    subtitle.setText(item.subtitle);
    subtitle.setTextColor(Color.parseColor("#A6B4AE"));
    subtitle.setTextSize(13f);
    subtitle.setMaxLines(2);
    subtitle.setPadding(dp(14), 0, dp(14), 0);
    LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    subtitleParams.topMargin = dp(5);
    subtitle.setLayoutParams(subtitleParams);
    card.addView(subtitle);

    return card;
  }

  private View buildPreviewHeader(CardItem item) {
    FrameLayout hero = new FrameLayout(this);
    hero.setBackground(buildHeroBackground());
    hero.setClipToOutline(false);
    FrameLayout.LayoutParams heroParams = new FrameLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      dp(244)
    );
    hero.setLayoutParams(heroParams);

    heroImage = new ImageView(this);
    heroImage.setScaleType(ImageView.ScaleType.CENTER_CROP);
    heroImage.setAlpha(0.54f);
    heroImage.setBackgroundColor(Color.parseColor("#050807"));
    heroImage.setLayoutParams(new FrameLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.MATCH_PARENT
    ));
    hero.addView(heroImage);

    View shade = new View(this);
    shade.setBackground(buildHeroShade());
    shade.setLayoutParams(new FrameLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.MATCH_PARENT
    ));
    hero.addView(shade);

    LinearLayout copy = new LinearLayout(this);
    copy.setOrientation(LinearLayout.VERTICAL);
    copy.setPadding(dp(30), dp(18), dp(30), dp(18));
    FrameLayout.LayoutParams copyParams = new FrameLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    copyParams.gravity = android.view.Gravity.BOTTOM | android.view.Gravity.LEFT;
    copy.setLayoutParams(copyParams);

    heroEyebrow = new TextView(this);
    heroEyebrow.setTextColor(Color.parseColor("#B7E1C7"));
    heroEyebrow.setTextSize(12f);
    heroEyebrow.setTypeface(Typeface.DEFAULT_BOLD);
    copy.addView(heroEyebrow);

    heroTitle = new TextView(this);
    heroTitle.setTextColor(Color.parseColor("#F3F6F2"));
    heroTitle.setTextSize(30f);
    heroTitle.setTypeface(Typeface.DEFAULT_BOLD);
    heroTitle.setMaxLines(2);
    LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    titleParams.topMargin = dp(5);
    heroTitle.setLayoutParams(titleParams);
    copy.addView(heroTitle);

    heroDescription = new TextView(this);
    heroDescription.setTextColor(Color.parseColor("#D8E1DC"));
    heroDescription.setTextSize(14f);
    heroDescription.setMaxLines(2);
    heroDescription.setMaxWidth(dp(680));
    LinearLayout.LayoutParams descriptionParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    descriptionParams.topMargin = dp(6);
    heroDescription.setLayoutParams(descriptionParams);
    copy.addView(heroDescription);

    heroMeta = new TextView(this);
    heroMeta.setTextColor(Color.parseColor("#A5B6AD"));
    heroMeta.setTextSize(12f);
    LinearLayout.LayoutParams metaParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    metaParams.topMargin = dp(7);
    heroMeta.setLayoutParams(metaParams);
    copy.addView(heroMeta);

    hero.addView(copy);
    updatePreviewHeader(item, false);
    return hero;
  }

  private void updatePreviewHeader(CardItem item, boolean animated) {
    if (heroTitle == null || heroDescription == null || heroMeta == null || heroEyebrow == null || heroImage == null) {
      return;
    }
    CardItem preview = item == null
      ? new CardItem("", currentMode == Mode.VIDEO ? "Video" : "Audio", "No items available.", "", "", "", "")
      : item;
    Runnable updateCopy = () -> {
      heroEyebrow.setText(activeSectionTitle());
      heroTitle.setText(preview.title);
      heroDescription.setText(preview.description == null || preview.description.trim().isEmpty() ? preview.subtitle : preview.description);
      heroMeta.setText(preview.subtitle);
    };
    if (animated) {
      heroTitle.animate().cancel();
      heroDescription.animate().cancel();
      heroMeta.animate().cancel();
      heroTitle.animate().alpha(0f).setDuration(90L).withEndAction(() -> {
        updateCopy.run();
        heroTitle.animate().alpha(1f).setDuration(180L).start();
        heroDescription.animate().alpha(1f).setDuration(180L).start();
        heroMeta.animate().alpha(1f).setDuration(180L).start();
      }).start();
      heroDescription.animate().alpha(0f).setDuration(90L).start();
      heroMeta.animate().alpha(0f).setDuration(90L).start();
    } else {
      updateCopy.run();
    }

    String imageUrl = preview.coverUrl == null ? "" : preview.coverUrl.trim();
    heroImage.animate().cancel();
    heroImage.setTag(imageUrl);
    if (imageUrl.isEmpty()) {
      heroImage.setImageDrawable(null);
      heroImage.setAlpha(0.28f);
      return;
    }
    if (animated) {
      heroImage.animate().alpha(0.22f).setDuration(140L).withEndAction(() -> {
        loadImageInto(heroImage, imageUrl);
        heroImage.animate().alpha(0.54f).setDuration(240L).start();
      }).start();
      return;
    }
    loadImageInto(heroImage, imageUrl);
    heroImage.setAlpha(0.54f);
  }

  private View buildInfoBlock(String titleText, String bodyText) {
    LinearLayout block = new LinearLayout(this);
    block.setOrientation(LinearLayout.VERTICAL);
    block.setPadding(dp(22), dp(22), dp(22), dp(22));
    block.setBackground(buildCardBackground(false));

    TextView title = new TextView(this);
    title.setText(titleText);
    title.setTextColor(Color.parseColor("#F3F6F2"));
    title.setTextSize(24f);
    title.setTypeface(Typeface.DEFAULT_BOLD);
    block.addView(title);

    TextView body = new TextView(this);
    body.setText(bodyText);
    body.setTextColor(Color.parseColor("#D3DBD6"));
    body.setTextSize(18f);
    body.setMaxWidth(dp(900));
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    params.topMargin = dp(16);
    body.setLayoutParams(params);
    block.addView(body);

    return block;
  }

  private void openDetails(CardItem item) {
    if (("video".equals(item.kind) || "track".equals(item.kind)) && item.playbackPath != null && !item.playbackPath.isEmpty()) {
      Intent playerIntent = new Intent(this, NativePlayerActivity.class);
      playerIntent.putExtra("title", item.title);
      playerIntent.putExtra("subtitle", item.subtitle);
      playerIntent.putExtra("playback_path", item.playbackPath);
      playerIntent.putExtra("track_json", item.trackJson);
      startActivity(playerIntent);
      return;
    }
    Intent intent = new Intent(this, NativeDetailActivity.class);
    intent.putExtra("kind", item.kind);
    intent.putExtra("title", item.title);
    intent.putExtra("subtitle", item.subtitle);
    intent.putExtra("track_json", item.trackJson);
    intent.putExtra("library_id", currentLibraryId);
    startActivity(intent);
  }

  private List<CardSection> buildVideoSections(int libraryId) throws Exception {
    List<CardSection> sections = new ArrayList<>();
    JSONObject curation = readJsonObject(endpoint("/video-curation/current/"));
    JSONArray rows = curation.optJSONArray("rows");
    if (rows != null && rows.length() > 0) {
      for (int index = 0; index < rows.length(); index += 1) {
        JSONObject row = rows.optJSONObject(index);
        if (row == null) {
          continue;
        }
        String rowId = row.optString("id", "row-" + index);
        String label = row.optString("label", rowId);
        addVideoSection(sections, rowId, label, fetchVideoGroupCardsFromUrl(endpoint(videoCurationPath(libraryId, row.optJSONObject("query"))), ""));
      }
      return sections;
    }
    addVideoSection(sections, "recently", "Recently Added", fetchVideoGroupCardsFromUrl(endpoint(videoCurationPath(libraryId, systemCurationQuery("recently"))), ""));
    addVideoSection(sections, "all", "All Videos", fetchVideoGroupCardsFromUrl(endpoint(videoCurationPath(libraryId, systemCurationQuery("all"))), ""));
    return sections;
  }

  private JSONObject systemCurationQuery(String key) throws Exception {
    JSONObject query = new JSONObject();
    query.put("curation_system", key);
    return query;
  }

  private void addVideoSection(List<CardSection> sections, String sectionKey, String title, VideoGroupPage page) {
    if (!page.items.isEmpty()) {
      sections.add(new CardSection(sectionKey, title, page.items, page.nextUrl));
    }
  }

  private VideoGroupPage fetchVideoGroupCards(int libraryId, String section) throws Exception {
    return fetchVideoGroupCardsFromUrl(endpoint(videoSeriesPath(libraryId, section)), section);
  }

  private VideoGroupPage fetchVideoGroupCardsFromUrl(String url, String section) throws Exception {
    List<CardItem> items = new ArrayList<>();
    JSONObject payload = readJsonObject(url);
    JSONArray results = payload.optJSONArray("results");
    if (results == null) {
      return new VideoGroupPage(items, "");
    }
    for (int index = 0; index < results.length(); index += 1) {
      JSONObject item = results.optJSONObject(index);
      if (item == null) {
        continue;
      }
      if (section != null && !section.isEmpty() && !section.equals(item.optString("section", ""))) {
        continue;
      }
      if ("series".equals(item.optString("group_kind", ""))) {
        items.add(cardFromJson(item, "series"));
      } else {
        items.add(cardFromVideoGroup(item));
      }
    }
    return new VideoGroupPage(items, normalizeNextUrl(payload.optString("next", "")));
  }

  private void resetVideoPaging() {
    currentVideoSections = new ArrayList<>();
  }

  private void loadMoreVideoSection(CardSection section) {
    if (section == null || section.loading || !section.hasMore()) {
      return;
    }
    String nextUrl = section.nextUrl;
    int targetRowIndex = section.rows.size();
    int scrollY = contentScroll == null ? 0 : contentScroll.getScrollY();
    section.loading = true;
    section.errorMessage = "";
    renderVideoBrowser(currentVideoSections);
    if (contentScroll != null) {
      contentScroll.post(() -> contentScroll.scrollTo(0, scrollY));
    }

    new Thread(() -> {
      try {
        VideoGroupPage page = fetchVideoGroupCardsFromUrl(nextUrl, "");
        runOnUiThread(() -> {
          if (currentMode != Mode.VIDEO || !currentVideoSections.contains(section)) {
            return;
          }
          section.loading = false;
          section.nextUrl = page.nextUrl;
          section.errorMessage = "";
          if (!page.items.isEmpty()) {
            section.rows.add(page.items);
          }
          renderVideoBrowser(currentVideoSections);
          focusSectionRow(section, targetRowIndex);
        });
      } catch (Exception error) {
        String message = error.getMessage() == null ? "Unable to load more items." : error.getMessage();
        runOnUiThread(() -> {
          if (currentMode != Mode.VIDEO || !currentVideoSections.contains(section)) {
            return;
          }
          section.loading = false;
          section.errorMessage = message;
          renderVideoBrowser(currentVideoSections);
        });
      }
    }).start();
  }

  private void focusSectionRow(CardSection section, int rowIndex) {
    if (rowsContainer == null || section == null || rowIndex < 0) {
      return;
    }
    int currentSectionIndex = -1;
    for (int index = 0; index < rowsContainer.getChildCount(); index += 1) {
      View child = rowsContainer.getChildAt(index);
      if (child instanceof TextView && section.title.contentEquals(((TextView) child).getText())) {
        currentSectionIndex += 1;
        if (currentSectionIndex == currentVideoSections.indexOf(section)) {
          int rowViewIndex = index + 1 + rowIndex;
          if (rowViewIndex < rowsContainer.getChildCount()) {
            View target = firstFocusableDescendant(rowsContainer.getChildAt(rowViewIndex));
            if (target != null) {
              target.requestFocus();
            }
          }
          return;
        }
      }
    }
  }

  private List<CardItem> buildAudioItems(int libraryId) throws Exception {
    if (activeAudioBrowse == AudioBrowse.ALBUMS) {
      return fetchAllCards(audioAlbumsPath(libraryId), "album");
    }
    if (activeAudioBrowse == AudioBrowse.TRACKS) {
      return fetchAllCards(audioTracksPath(libraryId), "track");
    }
    return fetchAllCards(audioArtistsPath(libraryId), "artist");
  }

  private String videoSeriesPath(int libraryId) throws Exception {
    return videoSeriesPath(libraryId, "");
  }

  private String videoSeriesPath(int libraryId, String section) throws Exception {
    return videoSeriesPath(libraryId, section, VIDEO_SECTION_PAGE_SIZE);
  }

  private String videoSeriesPath(int libraryId, String section, int pageSize) throws Exception {
    StringBuilder builder = new StringBuilder("/videos/series-groups/?library=");
    builder.append(libraryId).append("&view=card&page_size=").append(Math.max(1, pageSize));
    if (section != null && !section.trim().isEmpty()) {
      builder.append("&section=").append(urlEncode(section.trim()));
    }
    return appendCommonFilters(builder.toString());
  }

  private String videoCurationPath(int libraryId, JSONObject query) throws Exception {
    StringBuilder builder = new StringBuilder("/videos/series-groups/?library=");
    builder.append(libraryId).append("&view=card&page_size=").append(VIDEO_SECTION_PAGE_SIZE);
    if (query != null) {
      String curationSystem = query.optString("curation_system", "").trim();
      String tagValue = query.optString("tag_value", "").trim();
      if (!curationSystem.isEmpty()) {
        builder.append("&curation_system=").append(urlEncode(curationSystem));
      }
      if (!tagValue.isEmpty()) {
        builder.append("&tag_value=").append(urlEncode(tagValue));
      }
    }
    return appendCommonFilters(builder.toString());
  }

  private String audioArtistsPath(int libraryId) throws Exception {
    return appendCommonFilters("/artists/?library=" + libraryId + "&media_kind=audio&ordering=name&view=card&page_size=100");
  }

  private String audioAlbumsPath(int libraryId) throws Exception {
    return appendCommonFilters("/albums/?library=" + libraryId + "&media_kind=audio&ordering=title&view=card&page_size=100");
  }

  private String audioTracksPath(int libraryId) throws Exception {
    return appendCommonFilters("/tracks/?library=" + libraryId + "&media_kind=audio&ordering=canonical_title&view=card&page_size=100");
  }

  private String appendCommonFilters(String path) throws Exception {
    StringBuilder builder = new StringBuilder(path);
    if (!activeSearchTerm.trim().isEmpty()) {
      builder.append("&search=").append(urlEncode(activeSearchTerm.trim()));
    }
    if (!activeJumpKey.isEmpty()) {
      builder.append("&starts_with=").append(urlEncode(activeJumpKey));
    }
    return builder.toString();
  }

  private int resolveLibraryId() throws Exception {
    JSONObject latestJob = readJsonObject(endpoint("/scan-jobs/latest/"));
    int libraryId = latestJob.optInt("library", 0);
    if (libraryId <= 0) {
      throw new IllegalStateException("No library id available from /scan-jobs/latest/.");
    }
    return libraryId;
  }

  private List<CardItem> fetchAllCards(String path, String kind) throws Exception {
    List<CardItem> items = new ArrayList<>();
    for (JSONObject item : fetchAllJson(path)) {
      items.add(cardFromJson(item, kind));
    }
    return items;
  }

  private List<JSONObject> fetchPageJson(String path) throws Exception {
    List<JSONObject> items = new ArrayList<>();
    JSONObject payload = readJsonObject(endpoint(path));
    JSONArray results = payload.optJSONArray("results");
    if (results == null) {
      return items;
    }
    for (int index = 0; index < results.length(); index += 1) {
      JSONObject item = results.optJSONObject(index);
      if (item != null) {
        items.add(item);
      }
    }
    return items;
  }

  private List<JSONObject> fetchAllJson(String path) throws Exception {
    List<JSONObject> items = new ArrayList<>();
    String nextUrl = endpoint(path);
    while (nextUrl != null && !nextUrl.isEmpty()) {
      JSONObject payload = readJsonObject(nextUrl);
      JSONArray results = payload.optJSONArray("results");
      if (results == null) {
        break;
      }
      for (int index = 0; index < results.length(); index += 1) {
        JSONObject item = results.optJSONObject(index);
        if (item != null) {
          items.add(item);
        }
      }
      nextUrl = normalizeNextUrl(payload.optString("next", ""));
    }
    return items;
  }

  private String normalizeNextUrl(String rawNext) {
    if (rawNext == null || rawNext.trim().isEmpty() || "null".equals(rawNext)) {
      return "";
    }
    try {
      URL parsed = new URL(rawNext);
      StringBuilder path = new StringBuilder(parsed.getPath());
      if (parsed.getQuery() != null && !parsed.getQuery().isEmpty()) {
        path.append('?').append(parsed.getQuery());
      }
      return TvConnectionConfig.load(this).rewriteServerUrl(path.toString());
    } catch (Exception _error) {
      return rawNext.startsWith("/api/")
        ? TvConnectionConfig.load(this).rewriteServerUrl(rawNext)
        : endpoint(rawNext);
    }
  }

  private CardItem cardFromJson(JSONObject item, String kind) {
    if ("series".equals(kind)) {
      String title = item.optString("title", "TV Series");
      List<String> bits = new ArrayList<>();
      int seasonCount = item.optInt("season_count", 0);
      int trackCount = item.optInt("track_count", item.optInt("episode_count", 0));
      if (seasonCount > 0) {
        bits.add(seasonCount == 1 ? "1 season" : seasonCount + " seasons");
      }
      bits.add(trackCount == 1 ? "1 episode" : trackCount + " episodes");
      return cardItemFromPayload("series", title, joinBits(bits), heroDescriptionFromJson(item, joinBits(bits)), "", item.toString(), coverUrlFromJson(item), item);
    }
    if ("artist".equals(kind)) {
      String title = item.optString("name", "Unknown Artist");
      String subtitle = item.optString("sort_name", title);
      return new CardItem(kind, title, subtitle, heroDescriptionFromJson(item, subtitle), "", item.toString(), coverUrlFromJson(item));
    }
    if ("album".equals(kind)) {
      String title = item.optString("title", "Untitled Album");
      String subtitle = jsonArraySummary(item.optJSONArray("lead_artist_names"), item.optString("sort_title", title));
      return new CardItem(kind, title, subtitle, heroDescriptionFromJson(item, subtitle), "", item.toString(), coverUrlFromJson(item));
    }
    if ("track".equals(kind)) {
      String title = item.optString("canonical_title", item.optString("title", "Untitled Track"));
      String subtitle = item.optString("album_title", item.optString("media_kind", "track"));
      String playbackPath = item.optString("playback_url", item.optString("stream_url", ""));
      return cardItemFromPayload(kind, title, subtitle, heroDescriptionFromJson(item, subtitle), playbackPath, item.toString(), coverUrlFromJson(item), item);
    }
    String title = item.optString("canonical_title", item.optString("title", "Untitled Video"));
    String subtitle = buildVideoSubtitle(item);
    return cardItemFromPayload(kind, title, subtitle, heroDescriptionFromJson(item, subtitle), item.optString("playback_url", item.optString("stream_url", "")), item.toString(), coverUrlFromJson(item), item);
  }

  private CardItem cardFromVideoGroup(JSONObject item) {
    JSONObject representative = item.optJSONObject("representative_track");
    JSONObject trackPayload = representative != null ? representative : item;
    if (representative != null && item.optJSONObject("playback_status") != null && trackPayload.optJSONObject("playback_status") == null) {
      try {
        trackPayload = new JSONObject(trackPayload.toString());
        trackPayload.put("playback_status", item.optJSONObject("playback_status"));
        trackPayload.put("playback_cache_ready", item.optBoolean("playback_cache_ready", true));
      } catch (Exception _error) {
        trackPayload = representative;
      }
    }
    String title = item.optString("title", trackPayload.optString("canonical_title", trackPayload.optString("title", "Untitled Video")));
    String subtitle = buildVideoSubtitle(trackPayload);
    String playbackPath = trackPayload.optString("playback_url", trackPayload.optString("stream_url", ""));
    return cardItemFromPayload("video", title, subtitle, heroDescriptionFromJson(item, subtitle), playbackPath, trackPayload.toString(), coverUrlFromJson(item), item);
  }

  private CardItem cardItemFromPayload(String kind, String title, String subtitle, String description, String playbackPath, String trackJson, String coverUrl, JSONObject payload) {
    JSONObject playbackStatus = payload == null ? null : payload.optJSONObject("playback_status");
    boolean ready = payload == null || payload.optBoolean("playback_cache_ready", true);
    String message = "";
    int percent = ready ? 100 : 0;
    if (playbackStatus != null) {
      ready = playbackStatus.optBoolean("cache_ready", ready);
      message = playbackStatus.optString("message", "");
      JSONObject progress = playbackStatus.optJSONObject("progress");
      percent = progress == null ? (ready ? 100 : 0) : progress.optInt("percent", ready ? 100 : 0);
    }
    return new CardItem(kind, title, subtitle, description, playbackPath, trackJson, coverUrl, ready, message, percent);
  }

  private String heroDescriptionFromJson(JSONObject item, String fallback) {
    String[] keys = new String[]{
      "description",
      "overview",
      "summary",
      "bio",
      "biography",
      "artist_bio",
      "first_episode_title"
    };
    for (String key : keys) {
      String value = item.optString(key, "").trim();
      if (!value.isEmpty()) {
        return value;
      }
    }
    JSONObject representative = item.optJSONObject("representative_track");
    if (representative != null) {
      String representativeDescription = heroDescriptionFromJson(representative, "");
      if (!representativeDescription.isEmpty()) {
        return representativeDescription;
      }
    }
    return fallback == null ? "" : fallback;
  }

  private String coverUrlFromJson(JSONObject item) {
    String directUrl = item.optString("poster_url", item.optString("cover_url", item.optString("image_url", "")));
    if (directUrl != null && !directUrl.trim().isEmpty()) {
      return directUrl;
    }
    JSONObject representative = item.optJSONObject("representative_track");
    if (representative != null) {
      return representative.optString("poster_url", representative.optString("cover_url", representative.optString("image_url", "")));
    }
    return "";
  }

  private String buildVideoSubtitle(JSONObject item) {
    List<String> bits = new ArrayList<>();
    String seriesTitle = item.optString("series_title", "").trim();
    String videoCodec = item.optString("video_codec", "");
    String audioCodec = item.optString("audio_codec", "");
    int width = item.optInt("width", 0);
    int height = item.optInt("height", 0);
    if (!seriesTitle.isEmpty()) {
      bits.add(seriesTitle);
    }
    if (!videoCodec.isEmpty()) {
      bits.add(videoCodec);
    }
    if (!audioCodec.isEmpty()) {
      bits.add(audioCodec);
    }
    if (width > 0 && height > 0) {
      bits.add(width + "x" + height);
    }
    if (bits.isEmpty()) {
      bits.add("video");
    }
    return joinBits(bits);
  }

  private String jsonArraySummary(JSONArray values, String fallback) {
    if (values == null || values.length() == 0) {
      return fallback;
    }
    List<String> bits = new ArrayList<>();
    for (int index = 0; index < values.length(); index += 1) {
      String value = values.optString(index, "").trim();
      if (!value.isEmpty()) {
        bits.add(value);
      }
    }
    return bits.isEmpty() ? fallback : joinBits(bits);
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

  private JSONObject readJsonObject(String url) throws Exception {
    Exception lastError = null;
    for (int attempt = 0; attempt < 2; attempt += 1) {
      try {
        return readJsonObjectOnce(url);
      } catch (Exception error) {
        lastError = error;
        if (attempt == 0) {
          try {
            Thread.sleep(350L);
          } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
          }
        }
      }
    }
    throw lastError;
  }

  private JSONObject readJsonObjectOnce(String url) throws Exception {
    HttpURLConnection connection = null;
    InputStream inputStream = null;
    try {
      connection = (HttpURLConnection) new URL(url).openConnection();
      connection.setRequestMethod("GET");
      connection.setConnectTimeout(10000);
      connection.setReadTimeout(30000);
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

  private void loadImageInto(ImageView imageView, String path) {
    String rawPath = path == null ? "" : path.trim();
    if (rawPath.isEmpty()) {
      return;
    }
    imageView.setTag(rawPath);
    synchronized (IMAGE_CACHE) {
      Bitmap cachedBitmap = IMAGE_CACHE.get(rawPath);
      if (cachedBitmap != null) {
        imageView.setImageBitmap(cachedBitmap);
        return;
      }
    }
    IMAGE_EXECUTOR.execute(() -> {
      HttpURLConnection connection = null;
      InputStream inputStream = null;
      try {
        String imageUrl = TvConnectionConfig.load(this).rewriteServerUrl(rawPath);
        connection = (HttpURLConnection) new URL(imageUrl).openConnection();
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(8000);
        connection.setReadTimeout(15000);
        connection.setRequestProperty("Accept", "*/*");
        connection.setRequestProperty("User-Agent", BuildConfig.TV_USER_AGENT_SUFFIX);
        TvConnectionConfig.load(this).applyHeaders(connection);
        connection.connect();
        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) {
          return;
        }
        inputStream = connection.getInputStream();
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inPreferredConfig = Bitmap.Config.RGB_565;
        Bitmap bitmap = BitmapFactory.decodeStream(inputStream, null, options);
        if (bitmap == null) {
          return;
        }
        synchronized (IMAGE_CACHE) {
          IMAGE_CACHE.put(rawPath, bitmap);
        }
        runOnUiThread(() -> {
          Object tag = imageView.getTag();
          if (rawPath.equals(tag)) {
            imageView.setImageBitmap(bitmap);
          }
        });
      } catch (Exception _error) {
        // Keep placeholder art when the server cannot provide a poster.
      } finally {
        try {
          if (inputStream != null) {
            inputStream.close();
          }
        } catch (Exception _ignored) {
          // Ignore close failures.
        }
        if (connection != null) {
          connection.disconnect();
        }
      }
    });
  }

  private String endpoint(String path) {
    return TvConnectionConfig.load(this).apiBaseUrl() + path;
  }

  private String urlEncode(String value) throws Exception {
    return URLEncoder.encode(value, StandardCharsets.UTF_8.name());
  }

  private void renderConnectionConfig(String errorMessage, boolean initial) {
    loadingSpinner.setVisibility(View.GONE);
    clearStickyHero();
    rowsContainer.removeAllViews();
    contentTitle.setText("Connection");
    contentStatus.setText(initial ? "Configure trueRiver API access." : "Update connection settings and retry.");
    TvConnectionConfig config = TvConnectionConfig.load(this);

    if (errorMessage != null && !errorMessage.trim().isEmpty()) {
      rowsContainer.addView(buildInfoBlock("Connection failed", errorMessage));
    }

    LinearLayout form = new LinearLayout(this);
    form.setOrientation(LinearLayout.VERTICAL);
    form.setPadding(dp(24), dp(24), dp(24), dp(24));
    form.setBackground(buildCardBackground(false));
    LinearLayout.LayoutParams formParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    formParams.leftMargin = dp(104);
    formParams.rightMargin = dp(28);
    formParams.topMargin = dp(28);
    formParams.bottomMargin = dp(18);
    form.setLayoutParams(formParams);

    TextView title = new TextView(this);
    title.setText("trueRiver server");
    title.setTextColor(Color.parseColor("#F3F6F2"));
    title.setTextSize(24f);
    title.setTypeface(Typeface.DEFAULT_BOLD);
    form.addView(title);

    EditText hostInput = buildConfigInput("Address", config.host.isEmpty() ? BuildConfig.TV_API_DEFAULT_HOST : config.host, false);
    EditText portInput = buildConfigInput("Port", config.port.isEmpty() ? BuildConfig.TV_API_DEFAULT_PORT : config.port, false);
    portInput.setInputType(InputType.TYPE_CLASS_NUMBER);
    EditText hostHeaderInput = buildConfigInput("Host header (optional)", config.hostHeader, false);
    EditText userInput = buildConfigInput("User", config.username, false);
    EditText passwordInput = buildConfigInput("Password", config.password, true);

    form.addView(hostInput);
    form.addView(portInput);
    form.addView(hostHeaderInput);
    form.addView(userInput);
    form.addView(passwordInput);

    Button saveButton = buildActionButton("Save and connect");
    saveButton.setOnClickListener((view) -> {
      TvConnectionConfig.save(
        this,
        hostInput.getText().toString(),
        portInput.getText().toString(),
        hostHeaderInput.getText().toString(),
        userInput.getText().toString(),
        passwordInput.getText().toString()
      );
      loadCurrentSurface();
    });
    LinearLayout.LayoutParams saveParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    saveParams.topMargin = dp(18);
    saveButton.setLayoutParams(saveParams);
    form.addView(saveButton);
    rowsContainer.addView(form);
    hostInput.requestFocus();
  }

  private void renderSettings() {
    loadingSpinner.setVisibility(View.GONE);
    clearStickyHero();
    rowsContainer.removeAllViews();
    updateNavStyles();

    rowsContainer.addView(buildSectionTitle("Screensaver"));
    rowsContainer.addView(buildScreensaverSettingsCard());

    rowsContainer.addView(buildSectionTitle("Server"));
    LinearLayout serverCard = new LinearLayout(this);
    serverCard.setOrientation(LinearLayout.VERTICAL);
    serverCard.setPadding(dp(24), dp(22), dp(24), dp(22));
    serverCard.setBackground(buildCardBackground(false));
    LinearLayout.LayoutParams serverParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    serverParams.leftMargin = dp(104);
    serverParams.rightMargin = dp(28);
    serverParams.bottomMargin = dp(18);
    serverCard.setLayoutParams(serverParams);
    serverCard.addView(buildSettingsCopy(
      "Connection",
      "Use Address for the VM IP, Port for the exposed HTTP port, and Host header only when nginx must receive a domain name."
    ));
    Button connectionButton = buildActionButton("Edit connection");
    connectionButton.setOnClickListener((view) -> renderConnectionConfig("", false));
    LinearLayout.LayoutParams connectionParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    connectionParams.topMargin = dp(16);
    connectionButton.setLayoutParams(connectionParams);
    serverCard.addView(connectionButton);
    rowsContainer.addView(serverCard);
  }

  private View buildScreensaverSettingsCard() {
    LinearLayout card = new LinearLayout(this);
    card.setOrientation(LinearLayout.VERTICAL);
    card.setPadding(dp(24), dp(22), dp(24), dp(22));
    card.setBackground(buildCardBackground(false));
    LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    cardParams.leftMargin = dp(104);
    cardParams.rightMargin = dp(28);
    cardParams.bottomMargin = dp(18);
    card.setLayoutParams(cardParams);

    int currentTimeout = TvScreensaverConfig.timeoutSeconds(this);
    card.addView(buildSettingsCopy(
      "Idle screensaver",
      currentTimeout <= 0
        ? "Disabled. The TV interface will stay on the current screen."
        : "Starts after " + formatTimeoutLabel(currentTimeout) + " without remote input."
    ));

    LinearLayout choices = new LinearLayout(this);
    choices.setOrientation(LinearLayout.HORIZONTAL);
    LinearLayout.LayoutParams choicesParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    choicesParams.topMargin = dp(16);
    choices.setLayoutParams(choicesParams);

    addScreensaverTimeoutButton(choices, "Off", 0, currentTimeout);
    addScreensaverTimeoutButton(choices, "2 min", 120, currentTimeout);
    addScreensaverTimeoutButton(choices, "5 min", 300, currentTimeout);
    addScreensaverTimeoutButton(choices, "10 min", 600, currentTimeout);
    addScreensaverTimeoutButton(choices, "20 min", 1200, currentTimeout);
    card.addView(choices);

    Button previewButton = buildActionButton("Preview screensaver");
    previewButton.setOnClickListener((view) -> showScreensaver());
    LinearLayout.LayoutParams previewParams = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      ViewGroup.LayoutParams.WRAP_CONTENT
    );
    previewParams.topMargin = dp(14);
    previewButton.setLayoutParams(previewParams);
    card.addView(previewButton);
    return card;
  }

  private TextView buildSettingsCopy(String titleText, String bodyText) {
    TextView view = new TextView(this);
    view.setText(titleText + "\n" + bodyText);
    view.setTextColor(Color.parseColor("#D3DBD6"));
    view.setTextSize(17f);
    view.setLineSpacing(dp(2), 1.0f);
    view.setMaxWidth(dp(920));
    return view;
  }

  private void addScreensaverTimeoutButton(LinearLayout row, String label, int timeoutSeconds, int currentTimeout) {
    Button button = buildSelectorButton(label, timeoutSeconds == currentTimeout, () -> {
      TvScreensaverConfig.saveTimeoutSeconds(this, timeoutSeconds);
      resetScreensaverTimer();
      renderSettings();
    });
    row.addView(button);
  }

  private String formatTimeoutLabel(int timeoutSeconds) {
    int minutes = Math.max(1, timeoutSeconds / 60);
    return minutes == 1 ? "1 minute" : minutes + " minutes";
  }

  private EditText buildConfigInput(String hint, String value, boolean password) {
    EditText input = new EditText(this);
    input.setHint(hint);
    input.setText(value == null ? "" : value);
    input.setSingleLine(true);
    input.setTextColor(Color.parseColor("#F3F6F2"));
    input.setHintTextColor(Color.parseColor("#77887F"));
    input.setTextSize(20f);
    input.setPadding(dp(14), dp(10), dp(14), dp(10));
    input.setBackground(buildInputBackground(false));
    input.setSelectAllOnFocus(true);
    input.setInputType(password
      ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
      : InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_NORMAL);
    input.setOnFocusChangeListener((view, hasFocus) -> input.setBackground(buildInputBackground(hasFocus)));
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(520), ViewGroup.LayoutParams.WRAP_CONTENT);
    params.topMargin = dp(14);
    input.setLayoutParams(params);
    return input;
  }

  private Button buildActionButton(String label) {
    Button button = new Button(this);
    button.setText(label);
    button.setTextColor(Color.parseColor("#F3F6F2"));
    button.setTextSize(16f);
    button.setAllCaps(false);
    button.setPadding(dp(18), dp(8), dp(18), dp(8));
    button.setBackground(buildButtonBackground(false));
    button.setOnFocusChangeListener((view, hasFocus) -> button.setBackground(buildButtonBackground(hasFocus)));
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
      ViewGroup.LayoutParams.WRAP_CONTENT,
      dp(52)
    );
    params.rightMargin = dp(10);
    button.setLayoutParams(params);
    return button;
  }

  private TextView buildMediaBadge(String kind) {
    TextView badge = new TextView(this);
    String label = "series".equals(kind) ? "TV Series" : "video".equals(kind) ? "Video" : kind;
    badge.setText(label == null ? "" : label);
    badge.setTextColor(Color.parseColor("#ECF2EE"));
    badge.setTextSize(11f);
    badge.setTypeface(Typeface.DEFAULT_BOLD);
    badge.setPadding(dp(9), dp(4), dp(9), dp(4));
    GradientDrawable background = new GradientDrawable();
    background.setColor(Color.parseColor("#AA050807"));
    background.setCornerRadius(0);
    background.setStroke(dp(1), Color.parseColor("#55ECF2EE"));
    badge.setBackground(background);
    return badge;
  }

  private GradientDrawable buildPosterBackground() {
    GradientDrawable drawable = new GradientDrawable(
      GradientDrawable.Orientation.TOP_BOTTOM,
      new int[]{Color.parseColor("#15231D"), Color.parseColor("#050807")}
    );
    drawable.setCornerRadii(new float[]{
      dp(14), dp(14),
      dp(14), dp(14),
      0, 0,
      0, 0,
    });
    return drawable;
  }

  private GradientDrawable buildVideoPosterBackground() {
    GradientDrawable drawable = new GradientDrawable(
      GradientDrawable.Orientation.TOP_BOTTOM,
      new int[]{Color.parseColor("#16201B"), Color.parseColor("#050807")}
    );
    drawable.setCornerRadius(0);
    return drawable;
  }

  private GradientDrawable buildVideoTitleOverlayBackground() {
    return new GradientDrawable(
      GradientDrawable.Orientation.TOP_BOTTOM,
      new int[]{Color.parseColor("#D0050908"), Color.parseColor("#70050908")}
    );
  }

  private GradientDrawable buildHeroBackground() {
    GradientDrawable drawable = new GradientDrawable(
      GradientDrawable.Orientation.TOP_BOTTOM,
      new int[]{Color.parseColor("#13251D"), Color.parseColor("#050807")}
    );
    drawable.setCornerRadius(0);
    return drawable;
  }

  private GradientDrawable buildHeroShade() {
    return new GradientDrawable(
      GradientDrawable.Orientation.LEFT_RIGHT,
      new int[]{
        Color.parseColor("#F2050908"),
        Color.parseColor("#C8050908"),
        Color.parseColor("#60050908"),
        Color.parseColor("#12050908")
      }
    );
  }

  private GradientDrawable buildCardBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(focused ? "#263C32" : "#101614"));
    drawable.setCornerRadius(dp(14));
    drawable.setStroke(dp(focused ? 4 : 2), Color.parseColor(focused ? "#F3FFF8" : "#24332C"));
    return drawable;
  }

  private GradientDrawable buildVideoCardBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.TRANSPARENT);
    drawable.setCornerRadius(0);
    drawable.setStroke(0, Color.TRANSPARENT);
    return drawable;
  }

  private GradientDrawable buildLoadMoreBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(focused ? "#203428" : "#121A16"));
    drawable.setCornerRadius(0);
    drawable.setStroke(0, Color.TRANSPARENT);
    return drawable;
  }

  private GradientDrawable buildPreparingOverlayBackground() {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor("#C0050908"));
    drawable.setCornerRadius(0);
    return drawable;
  }

  private GradientDrawable buildInputBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(focused ? "#17271F" : "#0E1714"));
    drawable.setCornerRadius(0);
    drawable.setStroke(dp(2), Color.parseColor(focused ? "#B7E1C7" : "#253A30"));
    return drawable;
  }

  private GradientDrawable buildButtonBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(focused ? "#244936" : "#17271F"));
    drawable.setCornerRadius(0);
    drawable.setStroke(dp(2), Color.parseColor(focused ? "#B7E1C7" : "#2F4D3D"));
    return drawable;
  }

  private GradientDrawable buildSelectorBackground(boolean selected, boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(selected ? "#244936" : focused ? "#17271F" : "#0E1714"));
    drawable.setCornerRadius(0);
    drawable.setStroke(dp(selected || focused ? 2 : 1), Color.parseColor(selected || focused ? "#B7E1C7" : "#24332C"));
    return drawable;
  }

  private GradientDrawable buildSidebarBackground() {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor("#CC0B1310"));
    drawable.setCornerRadius(0);
    drawable.setStroke(dp(1), Color.parseColor("#27372F"));
    return drawable;
  }

  private GradientDrawable buildSidebarTabBackground(boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setColor(Color.parseColor(focused ? "#E017271F" : "#CC0B1310"));
    drawable.setCornerRadii(new float[]{
      0, 0,
      0, 0,
      0, 0,
      0, 0,
    });
    drawable.setStroke(dp(focused ? 2 : 1), Color.parseColor(focused ? "#B7E1C7" : "#27372F"));
    return drawable;
  }

  private void styleNavButton(ImageButton button, boolean selected) {
    if (button == null) {
      return;
    }
    button.setBackground(buildNavBackground(selected, false));
    button.setOnFocusChangeListener((view, hasFocus) -> {
      view.setBackground(buildNavBackground(selected || hasFocus, hasFocus));
      view.animate()
        .scaleX(hasFocus ? 1.05f : 1.0f)
        .scaleY(hasFocus ? 1.05f : 1.0f)
        .setDuration(120L)
        .start();
    });
  }

  private void updateNavStyles() {
    styleNavButton(navVideo, currentMode == Mode.VIDEO);
    styleNavButton(navAudio, currentMode == Mode.AUDIO);
    styleNavButton(navSettings, currentMode == Mode.SETTINGS);
  }

  private GradientDrawable buildNavBackground(boolean selected, boolean focused) {
    GradientDrawable drawable = new GradientDrawable();
    drawable.setShape(GradientDrawable.RECTANGLE);
    drawable.setCornerRadius(0);
    drawable.setColor(Color.parseColor(selected ? "#244936" : focused ? "#17271F" : "#00000000"));
    drawable.setStroke(dp(selected || focused ? 2 : 0), Color.parseColor(selected || focused ? "#B7E1C7" : "#00000000"));
    return drawable;
  }

  private void hideSidebar() {
    if (!sidebarVisible) {
      return;
    }
    sidebarVisible = false;
    setSidebarButtonsFocusable(false);
    if (sidebarTab != null) {
      sidebarTab.bringToFront();
      sidebarTab.setVisibility(View.VISIBLE);
      sidebarTab.setAlpha(0f);
      sidebarTab.animate()
        .alpha(1f)
        .setDuration(160L)
        .start();
    }
    float travel = sidebar.getWidth() > 0 ? sidebar.getWidth() + dp(10) : dp(90);
    sidebar.animate()
      .translationX(-travel)
      .alpha(0.92f)
      .setDuration(220L)
      .start();
  }

  private void showSidebarAndFocusActiveButton() {
    if (!sidebarVisible) {
      sidebarVisible = true;
      setSidebarButtonsFocusable(true);
      if (sidebarTab != null) {
        sidebarTab.animate()
          .alpha(0f)
          .setDuration(120L)
          .withEndAction(() -> {
            if (sidebarVisible && sidebarTab != null) {
              sidebarTab.setVisibility(View.GONE);
            }
          })
          .start();
      }
      sidebar.animate()
        .translationX(0f)
        .alpha(1f)
        .setDuration(220L)
        .start();
    } else if (sidebarTab != null) {
      sidebarTab.setVisibility(View.GONE);
    }
    activeNavButton().requestFocus();
  }

  private void setSidebarButtonsFocusable(boolean focusable) {
    navVideo.setFocusable(focusable);
    navAudio.setFocusable(focusable);
    if (navSettings != null) {
      navSettings.setFocusable(focusable);
      navSettings.setFocusableInTouchMode(focusable);
    }
    navVideo.setFocusableInTouchMode(focusable);
    navAudio.setFocusableInTouchMode(focusable);
  }

  private ImageButton activeNavButton() {
    if (currentMode == Mode.SETTINGS && navSettings != null) {
      return navSettings;
    }
    return currentMode == Mode.AUDIO ? navAudio : navVideo;
  }

  private void resetScreensaverTimer() {
    uiHandler.removeCallbacks(screensaverRunnable);
    if (screensaverVisible) {
      return;
    }
    long timeoutMs = TvScreensaverConfig.timeoutMillis(this);
    if (timeoutMs > 0L) {
      uiHandler.postDelayed(screensaverRunnable, timeoutMs);
    }
  }

  private void ensureScreensaverView() {
    if (screensaverView != null) {
      return;
    }
    screensaverView = new TvScreensaverView(this);
    screensaverView.setVisibility(View.GONE);
    screensaverView.setAlpha(0f);
    addContentView(screensaverView, new ViewGroup.LayoutParams(
      ViewGroup.LayoutParams.MATCH_PARENT,
      ViewGroup.LayoutParams.MATCH_PARENT
    ));
  }

  private void showScreensaver() {
    ensureScreensaverView();
    if (screensaverVisible || screensaverView == null) {
      return;
    }
    screensaverVisible = true;
    uiHandler.removeCallbacks(screensaverRunnable);
    screensaverView.bringToFront();
    screensaverView.setVisibility(View.VISIBLE);
    screensaverView.start();
    screensaverView.animate()
      .alpha(1f)
      .setDuration(420L)
      .start();
  }

  private void hideScreensaver(boolean reschedule) {
    if (!screensaverVisible || screensaverView == null) {
      if (reschedule) {
        resetScreensaverTimer();
      }
      return;
    }
    screensaverVisible = false;
    screensaverView.stop();
    screensaverView.animate()
      .alpha(0f)
      .setDuration(220L)
      .withEndAction(() -> {
        if (screensaverView != null && !screensaverVisible) {
          screensaverView.setVisibility(View.GONE);
        }
        if (reschedule) {
          resetScreensaverTimer();
        }
      })
      .start();
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

  private int dp(int value) {
    return Math.round(value * getResources().getDisplayMetrics().density);
  }

  private static final class CardItem {
    final String kind;
    final String title;
    final String subtitle;
    final String description;
    final String playbackPath;
    final String trackJson;
    final String coverUrl;
    final boolean playbackCacheReady;
    final String playbackStatusMessage;
    final int playbackProgressPercent;

    CardItem(String kind, String title, String subtitle, String description, String playbackPath, String trackJson, String coverUrl) {
      this(kind, title, subtitle, description, playbackPath, trackJson, coverUrl, true, "", 100);
    }

    CardItem(String kind, String title, String subtitle, String description, String playbackPath, String trackJson, String coverUrl, boolean playbackCacheReady, String playbackStatusMessage, int playbackProgressPercent) {
      this.kind = kind;
      this.title = title;
      this.subtitle = subtitle;
      this.description = description;
      this.playbackPath = playbackPath;
      this.trackJson = trackJson;
      this.coverUrl = coverUrl;
      this.playbackCacheReady = playbackCacheReady;
      this.playbackStatusMessage = playbackStatusMessage == null ? "" : playbackStatusMessage;
      this.playbackProgressPercent = Math.max(0, Math.min(100, playbackProgressPercent));
    }
  }

  private static final class CardSection {
    final String sectionKey;
    final String title;
    final List<List<CardItem>> rows = new ArrayList<>();
    String nextUrl;
    boolean loading;
    String errorMessage = "";

    CardSection(String sectionKey, String title, List<CardItem> items, String nextUrl) {
      this.sectionKey = sectionKey;
      this.title = title;
      if (items != null && !items.isEmpty()) {
        this.rows.add(items);
      }
      this.nextUrl = nextUrl == null ? "" : nextUrl;
    }

    boolean hasMore() {
      return nextUrl != null && !nextUrl.trim().isEmpty();
    }
  }

  private static final class VideoGroupPage {
    final List<CardItem> items;
    final String nextUrl;

    VideoGroupPage(List<CardItem> items, String nextUrl) {
      this.items = items;
      this.nextUrl = nextUrl == null ? "" : nextUrl;
    }
  }
}
