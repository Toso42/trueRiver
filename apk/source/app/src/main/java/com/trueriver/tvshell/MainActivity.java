package com.trueriver.tvshell;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public class MainActivity extends Activity {
  private static final long BACK_EXIT_WINDOW_MS = 1200L;
  private static final int BOOT_PROBE_MAX_ATTEMPTS = 24;
  private static final long BOOT_PROBE_INTERVAL_MS = 500L;

  private WebView webView;
  private FrameLayout webContainer;
  private FrameLayout fullscreenContainer;
  private ProgressBar loadingSpinner;
  private TextView statusMessage;
  private View customView;
  private WebChromeClient.CustomViewCallback customViewCallback;
  private long lastBackEscapeAt = 0L;
  private boolean appReady = false;
  private Bundle pendingState;
  private final Handler handler = new Handler(Looper.getMainLooper());
  private int bootProbeAttempt = 0;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    requestWindowFeature(Window.FEATURE_NO_TITLE);
    setContentView(R.layout.activity_main);

    webContainer = findViewById(R.id.web_container);
    fullscreenContainer = findViewById(R.id.fullscreen_container);
    loadingSpinner = findViewById(R.id.loading_spinner);
    statusMessage = findViewById(R.id.status_message);
    pendingState = savedInstanceState;

    configureWindow();
    showStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nPreparing web shell...");
    webContainer.post(this::bootstrapWebView);
  }

  private void configureWindow() {
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    enterImmersiveMode();
  }

  @SuppressLint("SetJavaScriptEnabled")
  private void bootstrapWebView() {
    if (webView != null) {
      return;
    }

    webView = new WebView(this);
    webView.setLayoutParams(
      new FrameLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.MATCH_PARENT
      )
    );
    webContainer.addView(webView);

    WebSettings settings = webView.getSettings();
    settings.setJavaScriptEnabled(true);
    settings.setDomStorageEnabled(true);
    settings.setMediaPlaybackRequiresUserGesture(false);
    settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
    settings.setAllowFileAccess(false);
    settings.setAllowContentAccess(false);
    settings.setBuiltInZoomControls(false);
    settings.setDisplayZoomControls(false);
    settings.setUseWideViewPort(true);
    settings.setLoadWithOverviewMode(true);
    settings.setUserAgentString(settings.getUserAgentString() + " " + BuildConfig.TV_USER_AGENT_SUFFIX);

    webView.setBackgroundColor(Color.BLACK);
    webView.setFocusable(true);
    webView.setFocusableInTouchMode(true);
    webView.setVerticalScrollBarEnabled(false);
    webView.setHorizontalScrollBarEnabled(false);
    webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
    webView.setVisibility(View.INVISIBLE);
    webView.clearCache(true);
    webView.clearHistory();
    webView.addJavascriptInterface(new TvShellBridge(), "AndroidBridge");
    webView.setWebViewClient(new TvWebViewClient());
    webView.setWebChromeClient(new TvWebChromeClient());
    WebView.setWebContentsDebuggingEnabled(true);

    if (pendingState != null) {
      showStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nRestoring session...");
      webView.restoreState(pendingState);
      pendingState = null;
      startBootProbe();
    } else {
      TvConnectionConfig config = TvConnectionConfig.load(this);
      showStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nLoading " + (config.bootUrl().isEmpty() ? "connection config" : config.bootUrl()));
      loadBootDocument();
    }
  }

  private void loadBootDocument() {
    TvConnectionConfig config = TvConnectionConfig.load(this);
    if (!TvConnectionConfig.isConfigured(this)) {
      reportStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nConnection is not configured.\nOpen Native mode and set host, port, user and password.");
      return;
    }
    new Thread(() -> {
      HttpURLConnection connection = null;
      InputStream stream = null;
      try {
        String bootUrl = config.bootUrl();
        connection = (HttpURLConnection) new URL(bootUrl).openConnection();
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(20000);
        connection.setInstanceFollowRedirects(false);
        config.applyHeaders(connection);
        connection.setRequestProperty("X-Forwarded-Proto", "https");
        connection.setRequestProperty("User-Agent", webView != null ? webView.getSettings().getUserAgentString() : BuildConfig.TV_USER_AGENT_SUFFIX);
        connection.connect();

        int status = connection.getResponseCode();
        stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        if (stream == null) {
          throw new IllegalStateException("No response body from boot document");
        }
        String html = readFully(stream);
        if (status < 200 || status >= 300) {
          throw new IllegalStateException("HTTP " + status + " while fetching boot document");
        }

        runOnUiThread(() -> {
          if (webView == null) {
            return;
          }
          webView.loadDataWithBaseURL(
            bootUrl,
            html,
            "text/html",
            "utf-8",
            bootUrl
          );
          startBootProbe();
        });
      } catch (Exception error) {
        reportStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nBoot document error:\n" + error.getMessage());
      } finally {
        try {
          if (stream != null) {
            stream.close();
          }
        } catch (Exception ignored) {}
        if (connection != null) {
          connection.disconnect();
        }
      }
    }).start();
  }

  @Override
  protected void onResume() {
    super.onResume();
    enterImmersiveMode();
    if (webView != null) {
      webView.onResume();
      webView.resumeTimers();
      webView.requestFocus();
    }
  }

  @Override
  protected void onPause() {
    if (webView != null) {
      webView.onPause();
      webView.pauseTimers();
    }
    super.onPause();
  }

  @Override
  protected void onDestroy() {
    handler.removeCallbacksAndMessages(null);
    if (webView != null) {
      webView.stopLoading();
      webView.destroy();
    }
    super.onDestroy();
  }

  @Override
  protected void onSaveInstanceState(Bundle outState) {
    if (webView != null) {
      webView.saveState(outState);
    }
    super.onSaveInstanceState(outState);
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
    if (handleRemoteKey(event)) {
      return true;
    }
    return super.dispatchKeyEvent(event);
  }

  private boolean handleRemoteKey(KeyEvent event) {
    switch (event.getKeyCode()) {
      case KeyEvent.KEYCODE_DPAD_UP:
        return dispatchPageKey(event, "ArrowUp", "ArrowUp", 38);
      case KeyEvent.KEYCODE_DPAD_DOWN:
        return dispatchPageKey(event, "ArrowDown", "ArrowDown", 40);
      case KeyEvent.KEYCODE_DPAD_LEFT:
        return dispatchPageKey(event, "ArrowLeft", "ArrowLeft", 37);
      case KeyEvent.KEYCODE_DPAD_RIGHT:
        return dispatchPageKey(event, "ArrowRight", "ArrowRight", 39);
      case KeyEvent.KEYCODE_DPAD_CENTER:
      case KeyEvent.KEYCODE_ENTER:
      case KeyEvent.KEYCODE_NUMPAD_ENTER:
        return dispatchPageKey(event, "Enter", "Enter", 13);
      case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE:
      case KeyEvent.KEYCODE_SPACE:
        return dispatchPageKey(event, " ", "Space", 32);
      case KeyEvent.KEYCODE_BACK:
        return handleBackKey(event);
      default:
        return false;
    }
  }

  private boolean dispatchPageKey(KeyEvent event, String key, String code, int which) {
    if (event.getAction() != KeyEvent.ACTION_DOWN && event.getAction() != KeyEvent.ACTION_UP) {
      return true;
    }
    dispatchSyntheticKey(
      event.getAction() == KeyEvent.ACTION_DOWN ? "keydown" : "keyup",
      key,
      code,
      which,
      event.getRepeatCount()
    );
    return true;
  }

  private boolean handleBackKey(KeyEvent event) {
    if (event.getAction() != KeyEvent.ACTION_DOWN) {
      return true;
    }

    long now = SystemClock.elapsedRealtime();
    if (!appReady) {
      finishAndRemoveTask();
      finishAffinity();
      moveTaskToBack(true);
      return true;
    }
    if (now - lastBackEscapeAt < BACK_EXIT_WINDOW_MS) {
      finishAndRemoveTask();
      finishAffinity();
      moveTaskToBack(true);
      return true;
    }

    lastBackEscapeAt = now;
    dispatchEscapeSequence();
    Toast.makeText(this, "Back again to exit app", Toast.LENGTH_SHORT).show();
    return true;
  }

  private void dispatchEscapeSequence() {
    dispatchSyntheticKey("keydown", "Escape", "Escape", 27, 0);
    dispatchSyntheticKey("keyup", "Escape", "Escape", 27, 0);
    dispatchSyntheticKey("keydown", "Backspace", "Backspace", 8, 0);
    dispatchSyntheticKey("keyup", "Backspace", "Backspace", 8, 0);
  }

  private Map<String, String> buildHostHeaders() {
    Map<String, String> headers = new HashMap<>();
    TvConnectionConfig config = TvConnectionConfig.load(this);
    String virtualHost = config.virtualHostHeader();
    if (!virtualHost.isEmpty()) {
      headers.put("Host", virtualHost);
      headers.put("X-Forwarded-Host", virtualHost);
    }
    headers.put("X-Forwarded-Proto", "https");
    return headers;
  }

  private boolean shouldProxyRequest(Uri uri) {
    if (uri == null) {
      return false;
    }
    String host = uri.getHost();
    TvConnectionConfig config = TvConnectionConfig.load(this);
    String virtualHost = config.virtualHostHeader();
    return config.host.equalsIgnoreCase(host) || (!virtualHost.isEmpty() && virtualHost.equalsIgnoreCase(host));
  }

  private URL rewriteUrl(Uri uri) throws Exception {
    TvConnectionConfig config = TvConnectionConfig.load(this);
    StringBuilder builder = new StringBuilder(config.serverBaseUrl());
    builder.append(uri.getEncodedPath() == null ? "/" : uri.getEncodedPath());
    if (uri.getEncodedQuery() != null && !uri.getEncodedQuery().isEmpty()) {
      builder.append('?').append(uri.getEncodedQuery());
    }
    return new URL(builder.toString());
  }

  private WebResourceResponse proxyRequest(WebResourceRequest request) {
    if (request == null || request.getUrl() == null) {
      return null;
    }
    if (!"GET".equalsIgnoreCase(request.getMethod())) {
      return null;
    }
    if (!shouldProxyRequest(request.getUrl())) {
      return null;
    }

    HttpURLConnection connection = null;
    try {
      connection = (HttpURLConnection) rewriteUrl(request.getUrl()).openConnection();
      connection.setRequestMethod("GET");
      connection.setConnectTimeout(10000);
      connection.setReadTimeout(20000);
      connection.setInstanceFollowRedirects(false);
      TvConnectionConfig.load(this).applyHeaders(connection);
      connection.setRequestProperty("X-Forwarded-Proto", "https");
      connection.setRequestProperty("User-Agent", webView != null ? webView.getSettings().getUserAgentString() : BuildConfig.TV_USER_AGENT_SUFFIX);
      for (Map.Entry<String, String> entry : request.getRequestHeaders().entrySet()) {
        String key = entry.getKey();
        if (key == null) {
          continue;
        }
        String lowered = key.toLowerCase(Locale.ROOT);
        if ("host".equals(lowered) || "x-forwarded-host".equals(lowered) || "x-forwarded-proto".equals(lowered)) {
          continue;
        }
        connection.setRequestProperty(key, entry.getValue());
      }
      connection.connect();

      int status = connection.getResponseCode();
      InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
      if (stream == null) {
        return null;
      }

      String contentType = connection.getContentType();
      String mimeType = extractMimeType(contentType);
      String encoding = extractCharset(contentType);
      WebResourceResponse response = new WebResourceResponse(
        mimeType,
        encoding,
        status,
        connection.getResponseMessage(),
        flattenHeaders(connection),
        stream
      );
      return response;
    } catch (Exception error) {
      reportStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nProxy error:\n" + error.getMessage());
      if (connection != null) {
        connection.disconnect();
      }
      return null;
    }
  }

  private Map<String, String> flattenHeaders(HttpURLConnection connection) {
    Map<String, String> headers = new HashMap<>();
    for (Map.Entry<String, java.util.List<String>> entry : connection.getHeaderFields().entrySet()) {
      if (entry.getKey() == null || entry.getValue() == null || entry.getValue().isEmpty()) {
        continue;
      }
      headers.put(entry.getKey(), entry.getValue().get(0));
    }
    return headers;
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

  private String extractMimeType(String contentType) {
    if (contentType == null || contentType.isEmpty()) {
      return "application/octet-stream";
    }
    int separator = contentType.indexOf(';');
    if (separator >= 0) {
      return contentType.substring(0, separator).trim();
    }
    return contentType.trim();
  }

  private String extractCharset(String contentType) {
    if (contentType == null) {
      return "utf-8";
    }
    String[] parts = contentType.split(";");
    for (String part : parts) {
      String trimmed = part.trim().toLowerCase(Locale.ROOT);
      if (trimmed.startsWith("charset=")) {
        return trimmed.substring("charset=".length()).trim();
      }
    }
    return "utf-8";
  }

  private void dispatchSyntheticKey(String type, String key, String code, int which, int repeat) {
    if (webView == null) {
      return;
    }

    String script = "(function(){"
      + "var target=document.activeElement||document.body||document.documentElement;"
      + "if(!target){return;}"
      + "var ev=new KeyboardEvent(" + JSONObject.quote(type) + ",{"
      + "key:" + JSONObject.quote(key) + ","
      + "code:" + JSONObject.quote(code) + ","
      + "keyCode:" + which + ","
      + "which:" + which + ","
      + "repeat:" + (repeat > 0 ? "true" : "false") + ","
      + "bubbles:true,cancelable:true"
      + "});"
      + "target.dispatchEvent(ev);"
      + "})();";

    webView.evaluateJavascript(script, null);
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

  private void showStatus(String message) {
    if (statusMessage == null) {
      return;
    }
    statusMessage.setText(message);
    statusMessage.setVisibility(View.VISIBLE);
    if (webView != null) {
      webView.setVisibility(View.INVISIBLE);
    }
  }

  private void hideStatus() {
    if (statusMessage == null) {
      return;
    }
    statusMessage.setVisibility(View.GONE);
    if (webContainer != null) {
      webContainer.setVisibility(View.VISIBLE);
    }
    if (webView != null) {
      webView.setVisibility(View.VISIBLE);
    }
  }

  private void reportStatus(String message) {
    runOnUiThread(() -> showStatus(message));
  }

  private void markAppReady() {
    runOnUiThread(() -> {
      appReady = true;
      handler.removeCallbacksAndMessages(null);
      loadingSpinner.setVisibility(View.GONE);
      hideStatus();
      if (webView != null) {
        webView.requestFocus();
      }
    });
  }

  private void installPageHooks() {
    if (webView == null) {
      return;
    }
    String script = "(function(){"
      + "if(window.__trueRiverAndroidHookInstalled){return;}"
      + "window.__trueRiverAndroidHookInstalled=true;"
      + "window.addEventListener('error',function(e){"
      + "if(window.AndroidBridge&&window.AndroidBridge.onAppError){"
      + "window.AndroidBridge.onAppError(String(e.message||'window error'));"
      + "}"
      + "});"
      + "window.addEventListener('unhandledrejection',function(e){"
      + "var reason=e&&e.reason;"
      + "var text=(typeof reason==='string')?reason:(reason&&reason.message)||'unhandled rejection';"
      + "if(window.AndroidBridge&&window.AndroidBridge.onAppError){"
      + "window.AndroidBridge.onAppError(String(text));"
      + "}"
      + "});"
      + "})();";
    webView.evaluateJavascript(script, null);
  }

  private void startBootProbe() {
    bootProbeAttempt = 0;
    scheduleBootProbe();
  }

  private void scheduleBootProbe() {
    handler.postDelayed(this::runBootProbe, BOOT_PROBE_INTERVAL_MS);
  }

  private void runBootProbe() {
    if (appReady || webView == null) {
      return;
    }

    bootProbeAttempt += 1;
    String script = "(function(){"
      + "var root=document.getElementById('root');"
      + "var rootHtmlLen=root&&root.innerHTML?root.innerHTML.length:0;"
      + "var bodyText=(document.body&&document.body.innerText)?document.body.innerText.trim().slice(0,120):'';"
      + "return JSON.stringify({"
      + "readyState:document.readyState,"
      + "href:String(location.href),"
      + "title:String(document.title||''),"
      + "rootHtmlLen:rootHtmlLen,"
      + "bodyText:bodyText"
      + "});"
      + "})();";

    webView.evaluateJavascript(script, (result) -> {
      if (appReady) {
        return;
      }

      String raw = result == null ? "" : result;
      String unwrapped = unwrapJsString(raw);
      int rootHtmlLen = extractInt(unwrapped, "rootHtmlLen");
      String title = extractString(unwrapped, "title");
      String bodyText = extractString(unwrapped, "bodyText");

      if (rootHtmlLen > 0) {
        markAppReady();
        return;
      }

      String message = "trueRiver TV " + BuildConfig.VERSION_NAME
        + "\nPage loaded. Waiting for app boot..."
        + "\nProbe " + bootProbeAttempt + "/" + BOOT_PROBE_MAX_ATTEMPTS
        + (title.isEmpty() ? "" : "\nTitle: " + title)
        + (bodyText.isEmpty() ? "" : "\nBody: " + bodyText);
      showStatus(message);

      if (bootProbeAttempt < BOOT_PROBE_MAX_ATTEMPTS) {
        scheduleBootProbe();
      }
    });
  }

  private String unwrapJsString(String raw) {
    String value = raw == null ? "" : raw.trim();
    if (value.startsWith("\"") && value.endsWith("\"") && value.length() >= 2) {
      value = value.substring(1, value.length() - 1);
    }
    return value.replace("\\\\", "\\").replace("\\\"", "\"");
  }

  private int extractInt(String json, String key) {
    try {
      JSONObject object = new JSONObject(json);
      return object.optInt(key, 0);
    } catch (Exception ignored) {
      return 0;
    }
  }

  private String extractString(String json, String key) {
    try {
      JSONObject object = new JSONObject(json);
      return object.optString(key, "");
    } catch (Exception ignored) {
      return "";
    }
  }

  private final class TvShellBridge {
    @JavascriptInterface
    public void onAppReady() {
      markAppReady();
    }

    @JavascriptInterface
    public void onAppError(String message) {
      reportStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nApp error:\n" + message);
    }
  }

  private final class TvWebViewClient extends WebViewClient {
    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
      WebResourceResponse proxied = proxyRequest(request);
      if (proxied != null) {
        return proxied;
      }
      return super.shouldInterceptRequest(view, request);
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
      return false;
    }

    @Override
    public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
      loadingSpinner.setVisibility(View.VISIBLE);
      showStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nLoading " + url);
    }

    @Override
    public void onPageFinished(WebView view, String url) {
      loadingSpinner.setVisibility(View.GONE);
      showStatus("trueRiver TV " + BuildConfig.VERSION_NAME + "\nPage loaded.\nWaiting for app boot...");
      installPageHooks();
      startBootProbe();
      view.requestFocus();
      enterImmersiveMode();
    }

    @Override
    public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
      handler.cancel();
      loadingSpinner.setVisibility(View.GONE);
      showStatus("SSL error while loading trueRiver TV");
      Toast.makeText(MainActivity.this, "SSL error while loading trueRiver", Toast.LENGTH_LONG).show();
    }

    @Override
    public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
      if (request.isForMainFrame()) {
        loadingSpinner.setVisibility(View.GONE);
        showStatus("HTTP error " + errorResponse.getStatusCode() + "\n" + request.getUrl());
        Toast.makeText(MainActivity.this, "HTTP error " + errorResponse.getStatusCode(), Toast.LENGTH_SHORT).show();
      }
    }

    @Override
    public void onReceivedError(
      WebView view,
      WebResourceRequest request,
      android.webkit.WebResourceError error
    ) {
      if (request.isForMainFrame()) {
        loadingSpinner.setVisibility(View.GONE);
        showStatus("Load error: " + error.getDescription() + "\n" + request.getUrl());
      }
    }
  }

  private final class TvWebChromeClient extends WebChromeClient {
    @Override
    public boolean onConsoleMessage(ConsoleMessage consoleMessage) {
      if (!appReady && consoleMessage != null) {
        String level = consoleMessage.messageLevel() != null ? consoleMessage.messageLevel().name() : "LOG";
        showStatus(
          "trueRiver TV "
            + BuildConfig.VERSION_NAME
            + "\nConsole "
            + level
            + ":\n"
            + consoleMessage.message()
        );
      }
      return super.onConsoleMessage(consoleMessage);
    }

    @Override
    public void onProgressChanged(WebView view, int newProgress) {
      if (!appReady) {
        loadingSpinner.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
      }
    }

    @Override
    public void onShowCustomView(View view, CustomViewCallback callback) {
      if (customView != null) {
        callback.onCustomViewHidden();
        return;
      }

      customView = view;
      customViewCallback = callback;
      fullscreenContainer.addView(
        view,
        new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
      );
      fullscreenContainer.setVisibility(View.VISIBLE);
      webView.setVisibility(View.GONE);
      enterImmersiveMode();
    }

    @Override
    public void onHideCustomView() {
      if (customView == null) {
        return;
      }

      fullscreenContainer.removeView(customView);
      fullscreenContainer.setVisibility(View.GONE);
      customView = null;
      webView.setVisibility(View.VISIBLE);
      if (customViewCallback != null) {
        customViewCallback.onCustomViewHidden();
        customViewCallback = null;
      }
      enterImmersiveMode();
    }
  }
}
