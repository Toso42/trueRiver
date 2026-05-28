package com.trueriver.tvshell;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.util.Base64;

import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;

final class TvConnectionConfig {
  private static final String PREFS_NAME = "trueriver_tv_connection";
  private static final String KEY_HOST = "host";
  private static final String KEY_PORT = "port";
  private static final String KEY_HOST_HEADER = "host_header";
  private static final String KEY_USERNAME = "username";
  private static final String KEY_PASSWORD = "password";

  final String host;
  final String port;
  final String hostHeader;
  final String username;
  final String password;

  private TvConnectionConfig(String host, String port, String hostHeader, String username, String password) {
    this.host = cleanHost(host);
    this.port = cleanPort(port);
    this.hostHeader = cleanHost(hostHeader);
    this.username = username == null ? "" : username.trim();
    this.password = password == null ? "" : password;
  }

  static TvConnectionConfig load(Context context) {
    SharedPreferences preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    return new TvConnectionConfig(
      preferences.getString(KEY_HOST, BuildConfig.TV_API_DEFAULT_HOST),
      preferences.getString(KEY_PORT, BuildConfig.TV_API_DEFAULT_PORT),
      preferences.getString(KEY_HOST_HEADER, BuildConfig.TV_API_HOST_HEADER),
      preferences.getString(KEY_USERNAME, ""),
      preferences.getString(KEY_PASSWORD, "")
    );
  }

  static boolean isConfigured(Context context) {
    TvConnectionConfig config = load(context);
    return !config.host.isEmpty() && !config.username.isEmpty() && !config.password.isEmpty();
  }

  static void save(Context context, String host, String port, String hostHeader, String username, String password) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .putString(KEY_HOST, cleanHost(host))
      .putString(KEY_PORT, cleanPort(port))
      .putString(KEY_HOST_HEADER, cleanHost(hostHeader))
      .putString(KEY_USERNAME, username == null ? "" : username.trim())
      .putString(KEY_PASSWORD, password == null ? "" : password)
      .apply();
  }

  String apiBaseUrl() {
    String baseUrl = serverBaseUrl();
    return baseUrl.isEmpty() ? "" : baseUrl + "/api";
  }

  String serverBaseUrl() {
    if (host.isEmpty()) {
      return "";
    }
    StringBuilder builder = new StringBuilder("http://");
    builder.append(host);
    if (!port.isEmpty() && !"80".equals(port)) {
      builder.append(':').append(port);
    }
    return builder.toString();
  }

  String bootUrl() {
    String baseUrl = serverBaseUrl();
    return baseUrl.isEmpty() ? "" : baseUrl + BuildConfig.TV_START_PATH;
  }

  String virtualHostHeader() {
    if (!hostHeader.isEmpty()) {
      return hostHeader;
    }
    String configured = BuildConfig.TV_API_HOST_HEADER == null ? "" : BuildConfig.TV_API_HOST_HEADER.trim();
    return configured.isEmpty() ? host : configured;
  }

  String rewriteServerUrl(String path) {
    if (path == null || path.trim().isEmpty()) {
      return "";
    }
    if (path.startsWith("http://") || path.startsWith("https://")) {
      Uri parsed = Uri.parse(path);
      if (serverBaseUrl().isEmpty()) {
        return "";
      }
      StringBuilder builder = new StringBuilder(serverBaseUrl());
      builder.append(parsed.getEncodedPath() == null ? "/" : parsed.getEncodedPath());
      if (parsed.getEncodedQuery() != null && !parsed.getEncodedQuery().isEmpty()) {
        builder.append('?').append(parsed.getEncodedQuery());
      }
      return builder.toString();
    }
    if (path.startsWith("/")) {
      return serverBaseUrl().isEmpty() ? "" : serverBaseUrl() + path;
    }
    return serverBaseUrl().isEmpty() ? "" : serverBaseUrl() + "/" + path;
  }

  void applyHeaders(HttpURLConnection connection) {
    String virtualHost = virtualHostHeader();
    if (!virtualHost.isEmpty()) {
      connection.setRequestProperty("Host", virtualHost);
      connection.setRequestProperty("X-Forwarded-Host", virtualHost);
    }
    connection.setRequestProperty("Authorization", basicAuthHeader());
  }

  String basicAuthHeader() {
    String credential = username + ":" + password;
    return "Basic " + Base64.encodeToString(credential.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
  }

  private static String cleanHost(String rawHost) {
    String value = rawHost == null ? "" : rawHost.trim();
    value = value.replace("https://", "").replace("http://", "");
    int slashIndex = value.indexOf('/');
    if (slashIndex >= 0) {
      value = value.substring(0, slashIndex);
    }
    int colonIndex = value.indexOf(':');
    if (colonIndex >= 0) {
      value = value.substring(0, colonIndex);
    }
    return value.trim();
  }

  private static String cleanPort(String rawPort) {
    String value = rawPort == null ? "" : rawPort.trim();
    return value.replaceAll("[^0-9]", "");
  }
}
