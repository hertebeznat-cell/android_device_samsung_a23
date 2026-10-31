/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lineageos.a23.callaudio;

import android.app.Application;
import android.os.UserHandle;

public class CallAudioApp extends Application {
    private static CallAudioTracker sTracker;

    @Override
    public void onCreate() {
        super.onCreate();
        start(this);
    }

    static synchronized void start(Application app) {
        // The persistent process runs once, as user 0.
        if (sTracker != null || UserHandle.myUserId() != UserHandle.USER_SYSTEM) {
            return;
        }
        sTracker = new CallAudioTracker(app);
        sTracker.start();
    }
}
