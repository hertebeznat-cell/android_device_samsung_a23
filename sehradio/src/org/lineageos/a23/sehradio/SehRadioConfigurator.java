/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

package org.lineageos.a23.sehradio;

import android.os.HwBinder;
import android.os.HwBlob;
import android.os.HwParcel;
import android.os.IHwBinder;
import android.os.RemoteException;
import android.util.Log;

/**
 * Sends ISehRadio.setVendorSpecificConfiguration(serial, [{FW_READY, 1}]) to one
 * RIL instance, and again whenever that RIL restarts.
 *
 * The call is written by hand rather than with generated HIDL classes, which
 * would need Samsung's .hal files in the tree. Layout as in hidl-gen's Java:
 * int32 serial, then vec<SehVendorConfiguration> as a 16-byte hidl_vec blob
 * whose buffer holds 32-byte structs of two hidl_strings (name, value).
 */
class SehRadioConfigurator extends Thread implements IHwBinder.DeathRecipient {
    private static final String TAG = "A23SehRadio";

    private static final String INTERFACE = "vendor.samsung.hardware.radio@2.2::ISehRadio";
    // 41 methods in @2.0, 3 in @2.1, then setNrMode_2_2 (45),
    // getVendorSpecificConfiguration (46) and setVendorSpecificConfiguration (47);
    // checked against BpHwSehRadio in the stock vendor.samsung.hardware.radio@2.2.so.
    private static final int SET_VENDOR_SPECIFIC_CONFIGURATION = 47;
    // Same serial as LineageOS sehradiomanager; the response is not needed.
    private static final int SERIAL = 0x3232;

    private static final String[][] CONFIGURATION = {
        {"FW_READY", "1"},
    };

    private static final long RETRY_MS = 10_000;

    private final String mInstance;

    SehRadioConfigurator(String instance) {
        super(TAG + "-" + instance);
        mInstance = instance;
    }

    @Override
    public void run() {
        while (true) {
            try {
                IHwBinder radio = HwBinder.getService(INTERFACE, mInstance, true /* retry */);
                setVendorSpecificConfiguration(radio);
                radio.linkToDeath(this, 0);
                Log.i(TAG, mInstance + ": sent FW_READY");
                return;
            } catch (RemoteException | RuntimeException e) {
                Log.e(TAG, mInstance + ": could not configure the RIL, retrying", e);
            }
            sleepQuietly(RETRY_MS);
        }
    }

    @Override
    public void serviceDied(long cookie) {
        Log.w(TAG, mInstance + ": RIL died, configuring it again");
        new SehRadioConfigurator(mInstance).start();
    }

    private static void setVendorSpecificConfiguration(IHwBinder radio) throws RemoteException {
        HwParcel request = new HwParcel();
        request.writeInterfaceToken(INTERFACE);
        request.writeInt32(SERIAL);

        HwBlob vector = new HwBlob(16);
        vector.putInt32(8 /* mSize */, CONFIGURATION.length);
        vector.putBool(12 /* mOwnsBuffer */, false);
        HwBlob entries = new HwBlob(CONFIGURATION.length * 32);
        for (int i = 0; i < CONFIGURATION.length; i++) {
            entries.putString(i * 32 /* name */, CONFIGURATION[i][0]);
            entries.putString(i * 32 + 16 /* value */, CONFIGURATION[i][1]);
        }
        vector.putBlob(0 /* mBuffer */, entries);
        request.writeBuffer(vector);

        HwParcel reply = new HwParcel();
        try {
            radio.transact(SET_VENDOR_SPECIFIC_CONFIGURATION, request, reply,
                    IHwBinder.FLAG_ONEWAY);
            request.releaseTemporaryStorage();
        } finally {
            reply.release();
        }
    }

    private static void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
