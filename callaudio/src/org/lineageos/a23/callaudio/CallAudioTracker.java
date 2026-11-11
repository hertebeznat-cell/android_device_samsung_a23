/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lineageos.a23.callaudio;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioManager;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.telephony.TelephonyCallback;
import android.telephony.TelephonyManager;
import android.util.Log;
import android.util.SparseArray;
import android.util.SparseIntArray;

import java.util.List;
import java.util.concurrent.Executor;

/**
 * Mirrors One UI Telecom (SamsungCallMultiSimAudioParam / SamsungCallAudioParam):
 * the stock HAL starts the voice session of the SIM named by g_call_sim_slot
 * (0x01 = SIM 1, 0x02 = SIM 2) when the audio mode becomes MODE_IN_CALL, and
 * takes g_call_state=2 / 1 (CALL_STATUS_CS_VOICE_CALL_ON / OFF) around the call.
 * The slot is set while a call rings or dials, before Telecom changes the mode,
 * and otherwise follows the default calling SIM.
 */
class CallAudioTracker {
    private static final String TAG = "A23CallAudio";

    private static final String CALL_STATE_ON = "g_call_state=2";
    private static final String CALL_STATE_OFF = "g_call_state=1";

    private final Context mContext;
    private final AudioManager mAudioManager;
    private final SubscriptionManager mSubscriptionManager;
    private final TelephonyManager mTelephonyManager;
    private final Executor mExecutor;

    /** Registered call state listeners, by subscription id. */
    private final SparseArray<SimCallListener> mListeners = new SparseArray<>();
    /** TelephonyManager.CALL_STATE_* by SIM slot. */
    private final SparseIntArray mCallStates = new SparseIntArray();

    private int mSlot = -1;
    private boolean mCallOn;

    CallAudioTracker(Context context) {
        mContext = context;
        mAudioManager = context.getSystemService(AudioManager.class);
        mSubscriptionManager = context.getSystemService(SubscriptionManager.class);
        mTelephonyManager = context.getSystemService(TelephonyManager.class);
        mExecutor = context.getMainExecutor();
    }

    void start() {
        mSubscriptionManager.addOnSubscriptionsChangedListener(mExecutor,
                new SubscriptionManager.OnSubscriptionsChangedListener() {
                    @Override
                    public void onSubscriptionsChanged() {
                        updateListeners();
                    }
                });
        mContext.registerReceiver(new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                update();
            }
        }, new IntentFilter(TelephonyManager.ACTION_DEFAULT_VOICE_SUBSCRIPTION_CHANGED),
                Context.RECEIVER_EXPORTED);
        updateListeners();
        update();
    }

    private void updateListeners() {
        List<SubscriptionInfo> subs = mSubscriptionManager.getActiveSubscriptionInfoList();
        SparseIntArray active = new SparseIntArray();
        if (subs != null) {
            for (SubscriptionInfo info : subs) {
                active.put(info.getSubscriptionId(), info.getSimSlotIndex());
            }
        }
        for (int i = mListeners.size() - 1; i >= 0; i--) {
            int subId = mListeners.keyAt(i);
            if (active.get(subId, -1) != mListeners.valueAt(i).mSimSlot) {
                SimCallListener listener = mListeners.valueAt(i);
                mTelephonyManager.unregisterTelephonyCallback(listener);
                mCallStates.delete(listener.mSimSlot);
                mListeners.removeAt(i);
            }
        }
        for (int i = 0; i < active.size(); i++) {
            int subId = active.keyAt(i);
            int slot = active.valueAt(i);
            if (slot < 0 || mListeners.get(subId) != null) {
                continue;
            }
            SimCallListener listener = new SimCallListener(slot);
            mTelephonyManager.createForSubscriptionId(subId)
                    .registerTelephonyCallback(mExecutor, listener);
            mListeners.put(subId, listener);
            Log.i(TAG, "listening to sub " + subId + " in slot " + slot);
        }
    }

    private void update() {
        int ringing = -1;
        int offhook = -1;
        for (int i = 0; i < mCallStates.size(); i++) {
            if (mCallStates.valueAt(i) == TelephonyManager.CALL_STATE_OFFHOOK) {
                offhook = mCallStates.keyAt(i);
            } else if (mCallStates.valueAt(i) == TelephonyManager.CALL_STATE_RINGING) {
                ringing = mCallStates.keyAt(i);
            }
        }
        if (offhook >= 0) {
            setSlot(offhook);
            if (!mCallOn) {
                setParameters(CALL_STATE_ON);
                mCallOn = true;
            }
            return;
        }
        if (mCallOn) {
            setParameters(CALL_STATE_OFF);
            mCallOn = false;
        }
        if (ringing >= 0) {
            setSlot(ringing);
            return;
        }
        int slot = SubscriptionManager.getSlotIndex(
                SubscriptionManager.getDefaultVoiceSubscriptionId());
        if (slot >= 0) {
            setSlot(slot);
        }
    }

    private void setSlot(int slot) {
        if (slot == mSlot) {
            return;
        }
        mSlot = slot;
        setParameters("g_call_sim_slot=0x0" + (slot + 1));
    }

    private void setParameters(String keyValuePairs) {
        Log.i(TAG, "setParameters " + keyValuePairs);
        mAudioManager.setParameters(keyValuePairs);
    }

    private class SimCallListener extends TelephonyCallback
            implements TelephonyCallback.CallStateListener {
        final int mSimSlot;

        SimCallListener(int slot) {
            mSimSlot = slot;
        }

        @Override
        public void onCallStateChanged(int state) {
            Log.i(TAG, "slot " + mSimSlot + " call state " + state);
            mCallStates.put(mSimSlot, state);
            update();
        }
    }
}
