/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lineageos.a23.callaudio;

import android.content.Context;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Display;
import android.view.View;
import android.view.WindowManager;

/**
 * In-call ear detection. The A23 has no proximity sensor: One UI detects the
 * ear with the touch controller ("virtual proximity", the stock sensor HAL's
 * com.samsung.sensor.hover_proximity, which turns on ear_detect_enable in the
 * touch driver while active). It reports the driver's hover level, 0 when
 * nothing is near and above 0 for a face, the opposite of a proximity
 * distance, so the framework's proximity wake lock cannot use it.
 *
 * While a call plays through the earpiece and the touch controller reports
 * a face, a black touch-blocking overlay covers the screen at minimum
 * brightness. The panel stays on so that the touch controller keeps sensing
 * the ear (it powers down with the display), and the overlay goes away as
 * soon as the phone leaves the ear.
 */
class ProximityGuard implements SensorEventListener {
    private static final String TAG = "A23Proximity";
    private static final String HOVER_PROXIMITY = "com.samsung.sensor.hover_proximity";
    /** Ignore a brief release, e.g. while moving the phone against the cheek. */
    private static final long FAR_DELAY_MS = 300;

    private final Context mContext;
    private final AudioManager mAudioManager;
    private final SensorManager mSensorManager;
    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private final Sensor mSensor;

    private WindowManager mWindowManager;
    private View mOverlay;
    private boolean mInCall;
    private boolean mListening;
    private boolean mNear;

    private final Runnable mHideOverlay = this::hideOverlay;

    private final AudioDeviceCallback mDeviceCallback = new AudioDeviceCallback() {
        @Override
        public void onAudioDevicesAdded(AudioDeviceInfo[] added) {
            update();
        }

        @Override
        public void onAudioDevicesRemoved(AudioDeviceInfo[] removed) {
            update();
        }
    };

    private final AudioManager.OnCommunicationDeviceChangedListener mCommunicationListener =
            device -> update();

    ProximityGuard(Context context) {
        mContext = context;
        mAudioManager = context.getSystemService(AudioManager.class);
        mSensorManager = context.getSystemService(SensorManager.class);
        Sensor found = null;
        for (Sensor sensor : mSensorManager.getSensorList(Sensor.TYPE_ALL)) {
            if (HOVER_PROXIMITY.equals(sensor.getStringType())) {
                found = sensor;
                break;
            }
        }
        mSensor = found;
        Log.i(TAG, "hover proximity sensor: " + (found == null ? "none"
                : found.getName() + ", max range " + found.getMaximumRange()));
        mAudioManager.registerAudioDeviceCallback(mDeviceCallback, mHandler);
        mAudioManager.addOnCommunicationDeviceChangedListener(context.getMainExecutor(),
                mCommunicationListener);
    }

    /** Called with whether a call is off hook (dialing, active or on hold). */
    void setInCall(boolean inCall) {
        mInCall = inCall;
        update();
    }

    private boolean usesEarpiece() {
        AudioDeviceInfo device = mAudioManager.getCommunicationDevice();
        return device != null && device.getType() == AudioDeviceInfo.TYPE_BUILTIN_EARPIECE;
    }

    private void update() {
        boolean listen = mSensor != null && mInCall && usesEarpiece();
        if (listen == mListening) {
            return;
        }
        mListening = listen;
        if (listen) {
            mSensorManager.registerListener(this, mSensor, SensorManager.SENSOR_DELAY_NORMAL,
                    mHandler);
        } else {
            mSensorManager.unregisterListener(this);
            mNear = false;
            mHandler.removeCallbacks(mHideOverlay);
            hideOverlay();
        }
        Log.i(TAG, listen ? "listening" : "stopped");
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        boolean near = event.values[0] > 0;
        Log.i(TAG, "hover " + event.values[0]);
        if (near == mNear) {
            return;
        }
        mNear = near;
        if (near) {
            mHandler.removeCallbacks(mHideOverlay);
            showOverlay();
        } else {
            mHandler.postDelayed(mHideOverlay, FAR_DELAY_MS);
        }
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
    }

    private void showOverlay() {
        if (mOverlay != null) {
            return;
        }
        if (mWindowManager == null) {
            Display display = mContext.getSystemService(android.hardware.display.DisplayManager.class)
                    .getDisplay(Display.DEFAULT_DISPLAY);
            mWindowManager = mContext.createWindowContext(display,
                    WindowManager.LayoutParams.TYPE_SECURE_SYSTEM_OVERLAY, null)
                    .getSystemService(WindowManager.class);
        }
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_SECURE_SYSTEM_OVERLAY,
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
                        | WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
                PixelFormat.OPAQUE);
        lp.setTitle("A23ProximityOverlay");
        lp.layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
        lp.setFitInsetsTypes(0);
        lp.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_OFF;
        View view = new View(mContext);
        view.setBackgroundColor(Color.BLACK);
        // Swallow every touch from the cheek.
        view.setOnTouchListener((v, e) -> true);
        try {
            mWindowManager.addView(view, lp);
            mOverlay = view;
            Log.i(TAG, "near: screen covered");
        } catch (RuntimeException e) {
            Log.e(TAG, "cannot add overlay", e);
        }
    }

    private void hideOverlay() {
        if (mOverlay == null) {
            return;
        }
        try {
            mWindowManager.removeView(mOverlay);
        } catch (RuntimeException e) {
            Log.e(TAG, "cannot remove overlay", e);
        }
        mOverlay = null;
        Log.i(TAG, "far: screen uncovered");
    }
}
