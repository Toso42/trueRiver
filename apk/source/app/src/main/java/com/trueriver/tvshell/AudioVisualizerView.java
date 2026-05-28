package com.trueriver.tvshell;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.util.AttributeSet;
import android.view.View;

public class AudioVisualizerView extends View {
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
  private final Path path = new Path();
  private boolean playing = false;
  private float progress = 0f;
  private float phase = 0f;

  public AudioVisualizerView(Context context) {
    super(context);
  }

  public AudioVisualizerView(Context context, AttributeSet attrs) {
    super(context, attrs);
  }

  public void setPlaybackState(boolean isPlaying, float playbackProgress) {
    playing = isPlaying;
    progress = Math.max(0f, Math.min(playbackProgress, 1f));
    postInvalidateOnAnimation();
  }

  @Override
  protected void onDraw(Canvas canvas) {
    super.onDraw(canvas);
    int width = getWidth();
    int height = getHeight();
    if (width <= 0 || height <= 0) {
      return;
    }

    phase += playing ? 0.018f : 0.004f;
    float cx = width * (0.5f + (float) Math.sin(phase * 0.33f) * 0.045f);
    float cy = height * (0.48f + (float) Math.cos(phase * 0.27f) * 0.035f);
    float base = Math.min(width, height);
    float pulse = 0.72f + (float) Math.sin(phase * 2.1f) * 0.08f + progress * 0.16f;

    paint.setShader(new LinearGradient(
      0,
      0,
      width,
      height,
      new int[] {
        Color.rgb(3, 6, 5),
        Color.rgb(9, 18, 15),
        Color.rgb(2, 4, 4)
      },
      new float[] { 0f, 0.48f, 1f },
      Shader.TileMode.CLAMP
    ));
    canvas.drawRect(0, 0, width, height, paint);

    paint.setShader(new RadialGradient(
      cx,
      cy,
      base * 0.62f,
      new int[] {
        Color.argb(88, 83, 184, 137),
        Color.argb(44, 46, 106, 83),
        Color.argb(0, 0, 0, 0)
      },
      new float[] { 0f, 0.44f, 1f },
      Shader.TileMode.CLAMP
    ));
    canvas.drawCircle(cx, cy, base * 0.62f, paint);
    paint.setShader(null);

    for (int ring = 0; ring < 7; ring += 1) {
      drawRing(canvas, cx, cy, base * (0.12f + ring * 0.052f) * pulse, ring);
    }

    drawProgressBars(canvas, width, height);
    postInvalidateOnAnimation();
  }

  private void drawRing(Canvas canvas, float cx, float cy, float radius, int ring) {
    path.reset();
    int points = 144;
    float direction = ring % 2 == 0 ? 1f : -1f;
    for (int point = 0; point <= points; point += 1) {
      float angle = (float) ((point / (float) points) * Math.PI * 2f);
      float wobble = (float) Math.sin(angle * (3 + ring) + phase * direction * (1.4f + ring * 0.12f));
      float stretched = radius + wobble * radius * (0.08f + ring * 0.006f);
      float x = cx + (float) Math.cos(angle + phase * 0.05f * direction) * stretched;
      float y = cy + (float) Math.sin(angle - phase * 0.04f) * stretched;
      if (point == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    paint.setStyle(Paint.Style.STROKE);
    paint.setStrokeWidth(Math.max(2f, getWidth() * 0.0016f));
    int alpha = Math.max(28, 118 - ring * 10);
    if (ring % 2 == 0) {
      paint.setColor(Color.argb(alpha, 94, 213, 154));
    } else {
      paint.setColor(Color.argb(alpha, 214, 235, 170));
    }
    canvas.drawPath(path, paint);
    paint.setStyle(Paint.Style.FILL);
  }

  private void drawProgressBars(Canvas canvas, int width, int height) {
    int bars = 56;
    float barWidth = width / (float) bars;
    for (int index = 0; index < bars; index += 1) {
      float wave = (float) Math.sin(phase * 1.7f + index * 0.34f);
      float slowWave = (float) Math.cos(phase * 0.7f - index * 0.19f);
      float amount = 0.18f + Math.abs(wave * 0.52f + slowWave * 0.22f) + progress * 0.18f;
      float barHeight = Math.min(height * 0.28f, Math.max(4f, height * 0.2f * amount));
      int alpha = 46 + Math.min(130, Math.round(amount * 110f));
      paint.setColor(Color.argb(alpha, 83, 184, 137));
      canvas.drawRect(index * barWidth, height - barHeight, index * barWidth + Math.max(1f, barWidth - 3f), height, paint);
    }
  }
}
