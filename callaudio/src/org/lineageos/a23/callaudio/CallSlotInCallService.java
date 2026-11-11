/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lineageos.a23.callaudio;

import android.telecom.Call;
import android.telecom.InCallService;
import android.telecom.PhoneAccountHandle;
import android.telephony.SubscriptionManager;
import android.telephony.TelephonyManager;

/**
 * Non-UI InCallService (bound by Telecom for apps holding
 * CONTROL_INCALL_EXPERIENCE). Telecom adds a call here as soon as it is
 * created, before it moves the audio mode to MODE_IN_CALL, so the SIM slot
 * reaches the audio HAL before it opens the voice session.
 */
public class CallSlotInCallService extends InCallService {
    private final Call.Callback mCallback = new Call.Callback() {
        @Override
        public void onDetailsChanged(Call call, Call.Details details) {
            report(call);
        }
    };

    @Override
    public void onCallAdded(Call call) {
        call.registerCallback(mCallback);
        report(call);
    }

    @Override
    public void onCallRemoved(Call call) {
        call.unregisterCallback(mCallback);
    }

    private void report(Call call) {
        // A second call (call waiting, conference) must not move the voice
        // session away from the one in progress; CallAudioTracker follows
        // the per-SIM call states for those.
        if (getCalls().size() > 1) {
            return;
        }
        int state = call.getDetails().getState();
        if (state != Call.STATE_CONNECTING && state != Call.STATE_DIALING
                && state != Call.STATE_RINGING && state != Call.STATE_NEW
                && state != Call.STATE_ACTIVE) {
            return;
        }
        PhoneAccountHandle handle = call.getDetails().getAccountHandle();
        if (handle == null) {
            // Still waiting for the user to pick a SIM.
            return;
        }
        int subId = getSystemService(TelephonyManager.class).getSubscriptionId(handle);
        if (!SubscriptionManager.isValidSubscriptionId(subId)) {
            return;
        }
        int slot = SubscriptionManager.getSlotIndex(subId);
        if (slot >= 0) {
            CallAudioApp.onCallSlot(slot);
        }
    }
}
