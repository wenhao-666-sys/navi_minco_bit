#!/usr/bin/env bash
# Explicit build command; do not run without the user's build authorization.
set -euo pipefail
runtime_source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
runtime_build_dir="$(mktemp -d /tmp/nav-rclcpp.XXXXXX)"
python3 - "$runtime_source_dir" "$runtime_build_dir" <<'PY'
import hashlib, json, tarfile, urllib.request, sys
from pathlib import Path
source, build = map(Path, sys.argv[1:])
manifest = json.loads((source / 'manifest.json').read_text())
archive = build / 'source.tar.gz'
with urllib.request.urlopen(manifest['source_url'], timeout=60) as response:
    archive.write_bytes(response.read())
assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['source_sha256'], 'Source checksum mismatch'
assert hashlib.sha256((source / 'executor.patch').read_bytes()).hexdigest() == manifest['patch_sha256'], 'Patch checksum mismatch'
with tarfile.open(archive) as tar:
    assert all(not m.name.startswith('/') and '..' not in Path(m.name).parts and not m.issym() and not m.islnk() for m in tar.getmembers())
    tar.extractall(build)
PY
patch --batch --fuzz=0 -p1 -d "$runtime_build_dir/rclcpp-16.0.18/rclcpp" < "$runtime_source_dir/executor.patch"
set +u
source /opt/ros/humble/setup.bash
set -u
CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2 colcon \
  --log-base "$runtime_build_dir/log" build \
  --base-paths "$runtime_build_dir/rclcpp-16.0.18/rclcpp" \
  --build-base "$runtime_build_dir/build" --install-base "$runtime_build_dir/install" \
  --packages-select rclcpp --allow-overriding rclcpp --parallel-workers 1 \
  --event-handlers console_cohesion+ \
  --cmake-args -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=RelWithDebInfo
install -m 644 "$runtime_build_dir/install/rclcpp/lib/librclcpp.so" "$runtime_source_dir/librclcpp.so.new"
mv -f "$runtime_source_dir/librclcpp.so.new" "$runtime_source_dir/librclcpp.so"
python3 - "$runtime_source_dir" <<'PY'
import hashlib, json, sys
from pathlib import Path
source = Path(sys.argv[1])
manifest = json.loads((source / 'manifest.json').read_text())
manifest['library_sha256'] = hashlib.sha256((source / 'librclcpp.so').read_bytes()).hexdigest()
(source / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
echo "Private runtime updated; build navi2 to install it. Build logs: $runtime_build_dir/log"
