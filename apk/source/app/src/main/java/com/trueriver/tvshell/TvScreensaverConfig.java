package com.trueriver.tvshell;

import android.content.Context;
import android.content.SharedPreferences;

final class TvScreensaverConfig {
  private static final String PREFS_NAME = "trueriver_tv_screensaver";
  private static final String KEY_TIMEOUT_SECONDS = "timeout_seconds";
  static final int DEFAULT_TIMEOUT_SECONDS = 300;

  private TvScreensaverConfig() {
  }

  static int timeoutSeconds(Context context) {
    SharedPreferences preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    int value = preferences.getInt(KEY_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS);
    return Math.max(0, value);
  }

  static long timeoutMillis(Context context) {
    int seconds = timeoutSeconds(context);
    return seconds <= 0 ? 0L : seconds * 1000L;
  }

  static void saveTimeoutSeconds(Context context, int timeoutSeconds) {
    context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
      .edit()
      .putInt(KEY_TIMEOUT_SECONDS, Math.max(0, timeoutSeconds))
      .apply();
  }
}
