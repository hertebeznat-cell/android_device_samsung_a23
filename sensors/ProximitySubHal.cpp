/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

// Proximity sensor for the Galaxy A23 4G, as a sub-HAL of the stock sensors
// multi-HAL (loaded through /odm/etc/sensors/hals.conf, see init.a23.rc).
//
// The phone has no proximity sensor. One UI detects the ear with the touch
// controller: Samsung's sensors.grip.so exposes it as the vendor type
// com.samsung.sensor.hover_proximity, which Samsung's framework handles and
// AOSP ignores. This sub-HAL does the same work (ear_detect_enable through
// the sec_cmd interface, events from the sec_touchproximity input device) and
// reports a standard android.sensor.proximity, so Android's in-call
// proximity wake lock turns the screen off at the ear. The Novatek driver
// keeps ear detection running while the display is off (nvt_ts_set_ed_mode).
//
// The driver reports the hover level (0 = nothing near, 1-5 = a face closer
// and closer); proximity sensors report a distance, so near maps to 0 cm and
// far to the maximum range.
//
// Only liblog and the HIDL/RefBase basics are used: at runtime the multi-HAL
// process runs on the Android 11 (VNDK 30) libraries.

#define LOG_TAG "A23ProximitySubHal"

#include "SubHal.h"

#include <dirent.h>
#include <fcntl.h>
#include <linux/input.h>
#include <log/log.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include <atomic>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

using ::android::sp;
using ::android::hardware::hidl_handle;
using ::android::hardware::hidl_string;
using ::android::hardware::hidl_vec;
using ::android::hardware::Return;
using ::android::hardware::Void;
using ::android::hardware::sensors::V1_0::Event;
using ::android::hardware::sensors::V1_0::MetaDataEventType;
using ::android::hardware::sensors::V1_0::OperationMode;
using ::android::hardware::sensors::V1_0::RateLevel;
using ::android::hardware::sensors::V1_0::Result;
using ::android::hardware::sensors::V1_0::SensorFlagBits;
using ::android::hardware::sensors::V1_0::SensorInfo;
using ::android::hardware::sensors::V1_0::SensorType;
using ::android::hardware::sensors::V1_0::SharedMemInfo;
using ::android::hardware::sensors::V2_0::implementation::IHalProxyCallback;

constexpr int32_t kHandle = 1;
constexpr float kFar = 5.0f;  // cm, the maximum range
constexpr float kNear = 0.0f;
constexpr const char* kTspCmd = "/sys/class/sec/tsp/cmd";
constexpr const char* kInputName = "sec_touchproximity";

int64_t nowNs() {
    struct timespec ts;
    clock_gettime(CLOCK_BOOTTIME, &ts);
    return ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

bool writeTspCmd(const char* cmd) {
    int fd = open(kTspCmd, O_WRONLY | O_CLOEXEC);
    if (fd < 0) {
        ALOGE("open %s: %s", kTspCmd, strerror(errno));
        return false;
    }
    ssize_t len = strlen(cmd);
    bool ok = write(fd, cmd, len) == len;
    if (!ok) ALOGE("write %s to %s: %s", cmd, kTspCmd, strerror(errno));
    close(fd);
    return ok;
}

int openProximityInput() {
    DIR* dir = opendir("/dev/input");
    if (dir == nullptr) {
        ALOGE("opendir /dev/input: %s", strerror(errno));
        return -1;
    }
    int found = -1;
    while (struct dirent* entry = readdir(dir)) {
        if (strncmp(entry->d_name, "event", 5) != 0) continue;
        std::string path = std::string("/dev/input/") + entry->d_name;
        int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NONBLOCK);
        if (fd < 0) continue;
        char name[64] = {};
        if (ioctl(fd, EVIOCGNAME(sizeof(name) - 1), name) > 0 && strcmp(name, kInputName) == 0) {
            found = fd;
            break;
        }
        close(fd);
    }
    closedir(dir);
    if (found < 0) ALOGE("input device %s not found", kInputName);
    return found;
}

class ProximitySubHal : public ISensorsSubHal {
  public:
    Return<void> getSensorsList(getSensorsList_cb _hidl_cb) override {
        SensorInfo info;
        info.sensorHandle = kHandle;
        info.name = "A23 Proximity (touch ear detection)";
        info.vendor = "LineageOS";
        info.version = 1;
        info.type = SensorType::PROXIMITY;
        info.typeAsString = "android.sensor.proximity";
        info.maxRange = kFar;
        info.resolution = kFar;
        info.power = 0.1f;
        info.minDelay = 0;
        info.fifoReservedEventCount = 0;
        info.fifoMaxEventCount = 0;
        info.requiredPermission = "";
        info.maxDelay = 0;
        info.flags = static_cast<uint32_t>(SensorFlagBits::WAKE_UP) |
                     static_cast<uint32_t>(SensorFlagBits::ON_CHANGE_MODE);
        hidl_vec<SensorInfo> list;
        list.resize(1);
        list[0] = info;
        _hidl_cb(list);
        return Void();
    }

    Return<Result> setOperationMode(OperationMode mode) override {
        return mode == OperationMode::NORMAL ? Result::OK : Result::BAD_VALUE;
    }

    Return<Result> activate(int32_t sensorHandle, bool enabled) override {
        if (sensorHandle != kHandle) return Result::BAD_VALUE;
        std::lock_guard<std::mutex> lock(mLock);
        if (enabled) {
            start();
        } else {
            stop();
        }
        return Result::OK;
    }

    Return<Result> batch(int32_t sensorHandle, int64_t /* samplingPeriodNs */,
                         int64_t /* maxReportLatencyNs */) override {
        return sensorHandle == kHandle ? Result::OK : Result::BAD_VALUE;
    }

    Return<Result> flush(int32_t sensorHandle) override {
        if (sensorHandle != kHandle) return Result::BAD_VALUE;
        Event event = {};
        event.timestamp = 0;
        event.sensorHandle = kHandle;
        event.sensorType = SensorType::META_DATA;
        event.u.meta.what = MetaDataEventType::META_DATA_FLUSH_COMPLETE;
        post(event);
        return Result::OK;
    }

    Return<Result> injectSensorData(const Event& /* event */) override {
        return Result::INVALID_OPERATION;
    }

    Return<void> registerDirectChannel(const SharedMemInfo& /* mem */,
                                       registerDirectChannel_cb _hidl_cb) override {
        _hidl_cb(Result::INVALID_OPERATION, -1);
        return Void();
    }

    Return<Result> unregisterDirectChannel(int32_t /* channelHandle */) override {
        return Result::INVALID_OPERATION;
    }

    Return<void> configDirectReport(int32_t /* sensorHandle */, int32_t /* channelHandle */,
                                    RateLevel /* rate */, configDirectReport_cb _hidl_cb) override {
        _hidl_cb(Result::INVALID_OPERATION, 0);
        return Void();
    }

    Return<void> debug(const hidl_handle& fd, const hidl_vec<hidl_string>& /* args */) override {
        if (fd.getNativeHandle() != nullptr && fd->numFds > 0) {
            dprintf(fd->data[0], "%s: active=%d near=%d\n", getName().c_str(),
                    mThread.joinable(), mNear.load());
        }
        return Void();
    }

    const std::string getName() override { return "A23ProximitySubHal"; }

    Return<Result> initialize(const sp<IHalProxyCallback>& halProxyCallback) override {
        std::lock_guard<std::mutex> lock(mLock);
        // Called again whenever the framework restarts: start from scratch.
        stop();
        {
            std::lock_guard<std::mutex> cbLock(mCallbackLock);
            mCallback = halProxyCallback;
        }
        return Result::OK;
    }

  private:
    // Both with mLock held.
    void start() {
        if (mThread.joinable()) return;
        mInputFd = openProximityInput();
        if (mInputFd < 0) return;
        mStopFd = eventfd(0, EFD_CLOEXEC);
        writeTspCmd("ear_detect_enable,1");
        // On-change sensors report their state when activated.
        mNear = false;
        postProximity(false);
        mThread = std::thread(&ProximitySubHal::readLoop, this);
        ALOGI("enabled");
    }

    void stop() {
        if (!mThread.joinable()) return;
        uint64_t one = 1;
        if (write(mStopFd, &one, sizeof(one)) != static_cast<ssize_t>(sizeof(one))) {
            ALOGE("wake reader: %s", strerror(errno));
        }
        mThread.join();
        close(mStopFd);
        close(mInputFd);
        mStopFd = mInputFd = -1;
        writeTspCmd("ear_detect_enable,0");
        ALOGI("disabled");
    }

    void readLoop() {
        int level = 0;
        struct pollfd fds[2] = {{mInputFd, POLLIN, 0}, {mStopFd, POLLIN, 0}};
        while (true) {
            if (poll(fds, 2, -1) < 0) {
                if (errno == EINTR) continue;
                ALOGE("poll: %s", strerror(errno));
                return;
            }
            if (fds[1].revents) return;
            if (!(fds[0].revents & POLLIN)) continue;
            struct input_event events[16];
            ssize_t n = read(mInputFd, events, sizeof(events));
            if (n <= 0) continue;
            size_t count = static_cast<size_t>(n) / sizeof(events[0]);
            for (size_t i = 0; i < count; i++) {
                const struct input_event& ev = events[i];
                if (ev.type == EV_ABS && ev.code == ABS_MT_CUSTOM) {
                    level = ev.value;
                } else if (ev.type == EV_SYN && ev.code == SYN_REPORT) {
                    bool near = level > 0;
                    ALOGI("hover level %d -> %s", level, near ? "near" : "far");
                    if (near != mNear) {
                        mNear = near;
                        postProximity(near);
                    }
                }
            }
        }
    }

    void postProximity(bool near) {
        Event event = {};
        event.timestamp = nowNs();
        event.sensorHandle = kHandle;
        event.sensorType = SensorType::PROXIMITY;
        event.u.scalar = near ? kNear : kFar;
        post(event);
    }

    void post(const Event& event) {
        sp<IHalProxyCallback> callback;
        {
            std::lock_guard<std::mutex> lock(mCallbackLock);
            callback = mCallback;
        }
        if (callback == nullptr) return;
        // Every event of this sub-HAL belongs to a wake-up sensor.
        callback->postEvents(std::vector<Event>{event}, callback->createScopedWakelock(true));
    }

    std::mutex mLock;
    std::mutex mCallbackLock;
    sp<IHalProxyCallback> mCallback;
    std::thread mThread;
    int mInputFd = -1;
    int mStopFd = -1;
    std::atomic<bool> mNear = false;
};

ProximitySubHal gSubHal;

}  // namespace

ISensorsSubHal* sensorsHalGetSubHal(uint32_t* version) {
    *version = SUB_HAL_2_0_VERSION;
    return &gSubHal;
}
