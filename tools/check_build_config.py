"""Check that every build entrypoint selects the reviewed platform and sources."""
import json
import re
import xml.etree.ElementTree as ET


def audit(root, device, lock):
    errors = []

    def read(name):
        path = device / name
        if not path.is_file():
            errors.append(f'Missing build workflow file: {name}')
            return ''
        return path.read_text(encoding='utf-8-sig')

    def require(condition, message):
        if not condition:
            errors.append(message)

    lunch = lock['lunch']
    server = read('server_build.sh')
    crave = read('crave_build.sh')
    require(bool(re.search(r'^lunch\s+' + re.escape(lunch) + r'\s*$', server, re.M)),
            'Server lunch differs from source-lock.json')
    choices = re.findall(r'\blineage_a23-\w+-(?:userdebug|user)\b', read('AndroidProducts.mk'))
    require(set(choices) == {lunch, lunch.removesuffix('debug')},
            'AndroidProducts.mk must offer only the reviewed Android release')
    require(f'EVO_BRANCH="{lock["manifest_branch"]}"' in crave,
            'Crave manifest branch differs from source-lock.json')
    require('A23_REMOTE_BUILD' in server and 'microsoft /proc/sys/kernel/osrelease' in server,
            'Server build must require remote opt-in and reject WSL')
    for name, script in (('build_a23.sh', read('build_a23.sh')), ('crave_build.sh', crave)):
        require('exec bash ' in script and '/server_build.sh' in script,
                f'{name} must delegate to the shared guarded server pipeline')
        require(not re.search(r'^\s*(?:m\s|lunch\s|source build/envsetup)', script, re.M),
                f'{name} bypasses the shared server pipeline')
    for marker in ('export EVO_BUILD_TYPE=Unofficial WITH_GMS=true',
                   'STAGE=selinux-validation', 'STAGE=stock-vendor-selinux-validation',
                   'STAGE=recovery-selinux-validation', 'STAGE=selinux-output-validation',
                   'check_selinux_ownership.py',
                   'STAGE=vndk-snapshot-validation', 'STAGE=kernel-config',
                   'STAGE=kernel-compilation', 'STAGE=compilation',
                   'check_build_artifacts.py'):
        require(marker in server, f'Shared server pipeline is missing {marker}')
    stages = ('STAGE=vndk-compatibility-patches', 'STAGE=sepolicy-compatibility-patches',
              'STAGE=cts-sepolicy-compatibility-patches',
              'STAGE=releasetools-compatibility-patches',
              'STAGE=vintf-compatibility-patches',
              'STAGE=kernel-compatibility-patches', 'STAGE=preflight')
    require(all(stage in server for stage in stages) and
            [server.find(stage) for stage in stages] == sorted(server.find(stage) for stage in stages),
            'Compatibility patches must be applied before server preflight')
    require(bool(re.search(r'^STAGE=cts-sepolicy-compatibility-patches\n' +
                           re.escape('apply_series cts "$device/patches/cts"') + r'\s*$', server, re.M)),
            'CTS SELinux compatibility stage must run its reviewed command against cts')
    build_stages = (
        ('selinux-validation', 'm -j"$BUILD_JOBS" selinux_policy'),
        ('stock-vendor-selinux-validation', 'm -j"$BUILD_JOBS" a23_stock_vendor_policy_compat_test'),
        ('recovery-selinux-validation', 'm -j"$BUILD_JOBS" sepolicy.recovery'),
        ('selinux-output-validation',
         'python3 "$device/tools/check_selinux_ownership.py" --root "$PWD" --server --product-out "$product_out"'),
        ('vndk-snapshot-validation', 'm -j"$BUILD_JOBS" com.android.vndk.v30'),
        ('kernel-config', 'm -j"$BUILD_JOBS" kernelconfig'),
        ('kernel-compilation', 'm -j"$BUILD_JOBS" kernel'),
        ('compilation', 'm -j"$BUILD_JOBS" evolution'),
    )
    build_positions = []
    for stage, command in build_stages:
        matches = list(re.finditer(r'^STAGE=' + re.escape(stage) + r'\s*$', server, re.M))
        require(len(matches) == 1, f'Require exactly one server build stage: {stage}')
        if len(matches) == 1:
            build_positions.append(matches[0].start())
        require(bool(re.search(r'^STAGE=' + re.escape(stage) + r'\n' +
                               re.escape(command) + r'\s*$', server, re.M)),
                f'Server stage {stage} must run its reviewed command')
    require(len(build_positions) == len(build_stages) and
            build_positions == sorted(build_positions),
            'SELinux validation must precede VNDK, kernel and ROM compilation in the reviewed order')
    require('python3 "$device/tools/apply_vintf_compat.py" --root "$PWD" --apply' in server,
            'Server must restore the stock FCM 5 and kernel 4.19 requirements before preflight')
    require(not re.search(r'https://(?:upload\.|api\.)?gofile|git\s+push|gh\s+release', server + crave),
            'Build scripts must preserve artifacts locally without publishing them')
    for name in ('extract-files.sh', 'setup-makefiles.sh'):
        script = read(name)
        require('exit 2' in script and not re.search(r'^\s*(?:setup_vendor|extract |sed |source )', script, re.M),
                f'{name} must not regenerate the reviewed vendor tree with legacy helpers')
    dependencies = read('lineage.dependencies')
    try:
        require(json.loads(dependencies) == [],
                'Use the explicit local manifest; automatic dependencies can replace pinned sources')
    except ValueError as error:
        errors.append(f'Invalid lineage.dependencies: {error}')

    manifests = []
    template = root / 'local_manifests/evolution-a23.xml'
    if template.is_file():
        manifests.append(('local_manifests/evolution-a23.xml', template.read_text(encoding='utf-8-sig')))
    embedded = re.search(r'cat > \.repo/local_manifests/a23\.xml <<MANIFEST\n(.*?)\nMANIFEST', crave, re.S)
    require(embedded is not None, 'Crave local manifest template is missing')
    if embedded:
        manifests.append(('Crave local manifest', embedded[1]))
    expected = {
        'kernel/samsung/a23': ('blxyzY/android_kernel_samsung_sm6225', lock['kernel_revision']),
        'prebuilts/vndk/v30': ('platform/prebuilts/vndk/v30', lock['vndk_snapshot_revision']),
        'hardware/samsung': ('LineageOS/android_hardware_samsung', 'lineage-24.0'),
        'device/samsung/a23': ('hertebeznat-cell/android_device_samsung_a23', None),
        'vendor/samsung/a235f': ('hertebeznat-cell/android_vendor_samsung_a235f', None),
    }
    for name, xml in manifests:
        try:
            manifest = ET.fromstring(xml)
        except ET.ParseError as error:
            errors.append(f'Invalid {name}: {error}')
            continue
        for path, (repository, revision) in expected.items():
            projects = [project for project in manifest.findall('project') if project.get('path') == path]
            require(len(projects) == 1, f'{name}: require one project at {path}')
            if len(projects) == 1:
                project = projects[0]
                require(project.get('name') == repository, f'{name}: wrong repository at {path}')
                if revision:
                    require(project.get('revision') == revision, f'{name}: wrong revision at {path}')
    return errors
