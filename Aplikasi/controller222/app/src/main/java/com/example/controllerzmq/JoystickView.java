package com.example.controllerzmq;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;

public class JoystickView extends View {

    private Paint basePaint, handlePaint;
    private float centerX, centerY;
    private float baseRadius, handleRadius;
    private float handleX, handleY;
    private JoystickListener listener;

    public interface JoystickListener {
        void onJoystickMoved(float xPercent, float yPercent, int direction);
    }

    public JoystickView(Context context) {
        super(context);
        init();
    }

    public JoystickView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    private void init() {
        basePaint = new Paint();
        basePaint.setColor(Color.parseColor("#A1A1A1"));
        basePaint.setStyle(Paint.Style.FILL_AND_STROKE);
        basePaint.setAntiAlias(true);

        handlePaint = new Paint();
        handlePaint.setColor(Color.parseColor("#AA5EE0"));
        handlePaint.setStyle(Paint.Style.FILL_AND_STROKE);
        handlePaint.setAntiAlias(true);
    }

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);

        centerX = w / 2f;
        centerY = h / 2f;
        baseRadius = Math.min(w, h) / 3f;
        handleRadius = baseRadius / 2f;

        handleX = centerX;
        handleY = centerY;
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        canvas.drawCircle(centerX, centerY, baseRadius, basePaint);
        canvas.drawCircle(handleX, handleY, handleRadius, handlePaint);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        float touchX = event.getX();
        float touchY = event.getY();

        switch (event.getAction()) {
            case MotionEvent.ACTION_DOWN:
            case MotionEvent.ACTION_MOVE:
                float dx = touchX - centerX;
                float dy = touchY - centerY;
                float distance = (float) Math.sqrt(dx * dx + dy * dy);

                if (distance < baseRadius) {
                    handleX = touchX;
                    handleY = touchY;
                } else {
                    float ratio = baseRadius / distance;
                    handleX = centerX + dx * ratio;
                    handleY = centerY + dy * ratio;
                }

                float xPercent = (handleX - centerX) / baseRadius;
                float yPercent = (handleY - centerY) / baseRadius;
                int direction = getDirection(xPercent, yPercent);

                if (listener != null) {
                    listener.onJoystickMoved(xPercent, yPercent, direction);
                }

                invalidate();
                break;

            case MotionEvent.ACTION_UP:
                handleX = centerX;
                handleY = centerY;

                if (listener != null) {
                    listener.onJoystickMoved(0, 0, 0);
                }

                invalidate();
                break;
        }

        return true;
    }

    private int getDirection(float x, float y) {
        if (Math.abs(x) < 0.2 && Math.abs(y) < 0.2) {
            return 0;
        }

        double angle = Math.toDegrees(Math.atan2(y, x));
        angle = (angle + 360) % 360;

        if (angle >= 337.5 || angle < 22.5) return 3;
        else if (angle >= 22.5 && angle < 67.5) return 4;
        else if (angle >= 67.5 && angle < 112.5) return 5;
        else if (angle >= 112.5 && angle < 157.5) return 6;
        else if (angle >= 157.5 && angle < 202.5) return 7;
        else if (angle >= 202.5 && angle < 247.5) return 8;
        else if (angle >= 247.5 && angle < 292.5) return 1;
        else return 2;
    }

    public void setJoystickListener(JoystickListener listener) {
        this.listener = listener;
    }
}