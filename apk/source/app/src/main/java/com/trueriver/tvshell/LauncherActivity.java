package com.trueriver.tvshell;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;

public class LauncherActivity extends Activity {
  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    requestWindowFeature(Window.FEATURE_NO_TITLE);
    setContentView(R.layout.activity_launcher);
    configureWindow();
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
    if (event.getAction() != KeyEvent.ACTION_DOWN) {
      return true;
    }
    switch (event.getKeyCode()) {
      case KeyEvent.KEYCODE_DPAD_CENTER:
      case KeyEvent.KEYCODE_ENTER:
      case KeyEvent.KEYCODE_NUMPAD_ENTER:
      case KeyEvent.KEYCODE_SPACE:
      case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE:
        openWebShell();
        return true;
      case KeyEvent.KEYCODE_BACK:
        finish();
        return true;
      default:
        return super.dispatchKeyEvent(event);
    }
  }

  private void openWebShell() {
    startActivity(new Intent(this, MainActivity.class));
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
}
