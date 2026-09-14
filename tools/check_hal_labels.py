"""Check the six stock HAL executable labels; not a policy compiler."""
import re

HALS = {
    'vendor.samsung.hardware.biometrics.fingerprint@3.0-service': 'hal_fingerprint_default_exec',
    'vendor.samsung.hardware.light-service': 'hal_light_default_exec',
    'android.hardware.sensors@2.0-service.multihal': 'hal_sensors_default_exec',
    'vendor.samsung.hardware.vibrator-service': 'hal_vibrator_default_exec',
    'android.hardware.usb@1.3-service.coral': 'hal_usb_default_exec',
    'android.hardware.health@2.1-service-samsung': 'hal_health_default_exec',
}


def audit(device, vendor):
    errors = []
    contexts = (device / 'sepolicy/vendor/file_contexts').read_text()
    stock = (vendor / 'proprietary/vendor/etc/selinux/vendor_file_contexts').read_text()
    for name, label in HALS.items():
        path = '/vendor/bin/hw/' + name
        if not (vendor / ('proprietary' + path)).is_file():
            errors.append(f'Missing HAL binary: {path}')
        expected = f'u:object_r:{label}:s0'
        for source, text in (('device', contexts), ('stock', stock)):
            matches = []
            for line in text.splitlines():
                fields = line.split()
                if not fields or fields[0].startswith('#'):
                    continue
                if re.fullmatch(fields[0], path):
                    matches.append(fields[-1])
            if expected not in matches:
                errors.append(f'{source} context missing for {path}: {expected}')
    return errors
