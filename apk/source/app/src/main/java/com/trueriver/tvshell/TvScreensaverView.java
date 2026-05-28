package com.trueriver.tvshell;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.os.SystemClock;
import android.util.AttributeSet;
import android.view.View;

public class TvScreensaverView extends View {
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
  private final Paint washPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
  private long startedAtMs = 0L;
  private boolean running = false;

  public TvScreensaverView(Context context) {
    super(context);
    configure();
  }

  public TvScreensaverView(Context context, AttributeSet attrs) {
    super(context, attrs);
    configure();
  }

  private void configure() {
    setBackgroundColor(Color.BLACK);
    setFocusable(false);
    setClickable(true);
  }

  public void start() {
    if (running) {
      return;
    }
    running = true;
    startedAtMs = SystemClock.uptimeMillis();
    invalidate();
  }

  public void stop() {
    running = false;
  }

  @Override
  protected void onDraw(Canvas canvas) {
    super.onDraw(canvas);
    int width = getWidth();
    int height = getHeight();
    if (width <= 0 || height <= 0) {
      return;
    }

    float seconds = (SystemClock.uptimeMillis() - startedAtMs) / 1000f;
    drawBackdrop(canvas, width, height, seconds);
    drawPlasmaCells(canvas, width, height, seconds);
    drawSoftRings(canvas, width, height, seconds);

    if (running) {
      postInvalidateDelayed(33L);
    }
  }

  private void drawBackdrop(Canvas canvas, int width, int height, float seconds) {
    int x = Math.round(width * (0.5f + 0.28f * (float) Math.sin(seconds * 0.071f)));
    int y = Math.round(height * (0.5f + 0.24f * (float) Math.cos(seconds * 0.053f)));
    washPaint.setShader(new RadialGradient(
      x,
      y,
      Math.max(width, height) * 0.82f,
      new int[]{
        Color.rgb(9, 28, 23),
        Color.rgb(3, 8, 10),
        Color.BLACK
      },
      new float[]{0f, 0.56f, 1f},
      Shader.TileMode.CLAMP
    ));
    canvas.drawRect(0, 0, width, height, washPaint);
    washPaint.setShader(null);
  }

  private void drawPlasmaCells(Canvas canvas, int width, int height, float seconds) {
    int cell = Math.max(18, Math.round(Math.min(width, height) / 42f));
    for (int y = -cell; y < height + cell; y += cell) {
      for (int x = -cell; x < width + cell; x += cell) {
        float nx = x / (float) width;
        float ny = y / (float) height;
        double wave =
          Math.sin((nx * 7.5) + seconds * 0.22)
            + Math.cos((ny * 8.3) - seconds * 0.17)
            + Math.sin(((nx + ny) * 6.1) + seconds * 0.11);
        float intensity = (float) ((wave + 3.0) / 6.0);
        int alpha = 34 + Math.round(intensity * 84);
        int red = 12 + Math.round(intensity * 32);
        int green = 54 + Math.round(intensity * 92);
        int blue = 48 + Math.round((1f - intensity) * 72);
        paint.setColor(Color.argb(alpha, red, green, blue));
        canvas.drawRect(x, y, x + cell + 1, y + cell + 1, paint);
      }
    }
  }

  private void drawSoftRings(Canvas canvas, int width, int height, float seconds) {
    paint.setStyle(Paint.Style.STROKE);
    for (int index = 0; index < 5; index += 1) {
      float phase = seconds * (0.055f + index * 0.011f) + index * 1.37f;
      float cx = width * (0.5f + 0.34f * (float) Math.sin(phase));
      float cy = height * (0.5f + 0.30f * (float) Math.cos(phase * 0.83f));
      float radius = Math.min(width, height) * (0.13f + index * 0.075f)
        + Math.min(width, height) * 0.045f * (float) Math.sin(seconds * 0.08f + index);
      paint.setStrokeWidth(Math.max(2f, Math.min(width, height) * 0.006f));
      paint.setShader(new LinearGradient(
        cx - radius,
        cy - radius,
        cx + radius,
        cy + radius,
        Color.argb(0, 130, 232, 177),
        Color.argb(120, 130, 232, 177),
        Shader.TileMode.CLAMP
      ));
      canvas.drawCircle(cx, cy, radius, paint);
      paint.setShader(null);
    }
    paint.setStyle(Paint.Style.FILL);
  }
}
