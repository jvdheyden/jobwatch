#!/bin/bash
set -euo pipefail

# Kept so old setup instructions cannot overwrite distribution security policy.
PLATFORM="${JOB_AGENT_PLATFORM:-$(uname -s)}"

usage() {
  cat <<HELP
Usage: $0

Retired installer: jobwatch no longer installs Bubblewrap AppArmor profiles.
Use your distribution's profile; see docs/machine_setup.md.
HELP
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$PLATFORM" != "Linux" ]]; then
  echo "Skipping bwrap AppArmor install on non-Linux platform: $PLATFORM"
  exit 0
fi

cat >&2 <<NOTICE
No AppArmor policy was changed. This installer is retired because its profile
could overwrite or conflict with the distribution's /usr/bin/bwrap policy.
Use the distribution's Bubblewrap package and AppArmor profile instead.
Do not install old .scheduler/bwrap-userns-restrict artifacts.
See docs/machine_setup.md for host verification and troubleshooting.
NOTICE
exit 1
