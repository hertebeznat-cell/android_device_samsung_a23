/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lineageos.a23.sehradio;

import android.app.Application;
import android.os.UserHandle;
import android.telephony.TelephonyManager;

public class SehRadioApp extends Application {
    private static boolean sStarted;

    @Override
    public void onCreate() {
        super.onCreate();
        start(this);
    }

    static synchronized void start(Application app) {
        // The persistent process runs once, as user 0.
        if (sStarted || UserHandle.myUserId() != UserHandle.USER_SYSTEM) {
            return;
        }
        sStarted = true;
        int slots = app.getSystemService(TelephonyManager.class).getSupportedModemCount();
        for (int slot = 1; slot <= slots; slot++) {
            new SehRadioConfigurator("slot" + slot).start();
        }
    }
}
