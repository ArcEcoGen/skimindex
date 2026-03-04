#!/bin/bash
set -euo pipefail

# Default values
GITHUB_REPO="https://github.com/metabarcoding/obitools4"
INSTALL_DIR="/usr/local"
OBITOOLS_PREFIX=""
VERSION=""
LIST_VERSIONS=false

# Help message
function display_help {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  -i, --install-dir       Directory where obitools are installed "
  echo "                          (e.g., use /usr/local not /usr/local/bin)."
  echo "  -p, --obitools-prefix   Prefix added to the obitools command names if you"
  echo "                          want to have several versions of obitools at the"
  echo "                          same time on your system (e.g., -p g will produce "
  echo "                          gobigrep command instead of obigrep)."
  echo "  -v, --version           Install a specific version (e.g., 4.4.8)."
  echo "                          If not specified, installs the latest version."
  echo "  -l, --list              List all available versions and exit."
  echo "  -h, --help              Display this help message."
  echo ""
  echo "Examples:"
  echo "  $0                      # Install latest version"
  echo "  $0 -l                   # List available versions"
  echo "  $0 -v 4.4.8             # Install specific version"
  echo "  $0 -i /opt/local        # Install to custom directory"
}

# List available versions from GitHub releases
function list_versions {
  echo "Fetching available versions..." 1>&2
  echo ""
  curl -fsSL --http1.1 --retry 3 --retry-delay 2 "https://api.github.com/repos/metabarcoding/obitools4/releases" \
    | grep '"tag_name":' \
    | sed -E 's/.*"tag_name": "Release_([0-9.]+)".*/\1/' \
    | sort -V -r
}

# Get latest version from GitHub releases
function get_latest_version {
  curl -fsSL --http1.1 --retry 3 --retry-delay 2 "https://api.github.com/repos/metabarcoding/obitools4/releases" \
    | grep '"tag_name":' \
    | sed -E 's/.*"tag_name": "Release_([0-9.]+)".*/\1/' \
    | sort -V -r \
    | head -1
}

# Resolve Go archive filename via the official JSON API (no HTML scraping)
# Usage: get_go_archive <os> <arch>
function get_go_archive {
  local os="$1"
  local arch="$2"
  local filename
  # Search directly for filenames matching go<version>.<os>-<arch>.tar.gz
  # This avoids any JSON key spacing issue ("filename":"..." vs "filename": "...")
  filename=$(curl -fsSL --http1.1 --retry 3 --retry-delay 2 "https://go.dev/dl/?mode=json" \
    | grep -oE "go[0-9][^\"']*\\.${os}-${arch}\\.tar\\.gz" \
    | head -1)
  if [[ -z "$filename" ]]; then
    echo "Error: could not find a Go release for os=${os} arch=${arch}" 1>&2
    exit 1
  fi
  echo "$filename"
}

# Parse command line arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    -i|--install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    -p|--obitools-prefix)
      OBITOOLS_PREFIX="$2"
      shift 2
      ;;
    -v|--version)
      VERSION="$2"
      shift 2
      ;;
    -l|--list)
      LIST_VERSIONS=true
      shift
      ;;
    -h|--help)
      display_help
      exit 0
      ;;
    *)
      echo "Error: Unsupported option $1" 1>&2
      display_help 1>&2
      exit 1
      ;;
  esac
done

# List versions and exit if requested
if [ "$LIST_VERSIONS" = true ]; then
  echo "Available OBITools4 versions:"
  echo "=============================="
  list_versions
  exit 0
fi

# Determine version to install
if [ -z "$VERSION" ]; then
  echo "Fetching latest version..." 1>&2
  VERSION=$(get_latest_version)
  if [ -z "$VERSION" ]; then
    echo "Error: Could not determine latest version" 1>&2
    exit 1
  fi
  echo "Latest version: $VERSION" 1>&2
else
  echo "Installing version: $VERSION" 1>&2
fi

# Construct source URL for the specified version
OBIURL4="${GITHUB_REPO}/archive/refs/tags/Release_${VERSION}.zip"

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')   # linux | darwin
ARCH=$(uname -m)

case "$ARCH" in
  x86_64)           ARCH="amd64" ;;
  aarch64 | arm64)  ARCH="arm64" ;;
  armv7l)           ARCH="armv6l" ;;
  *)
    echo "Error: unsupported architecture: $ARCH" 1>&2
    exit 1
    ;;
esac

# Create temporary working directory
WORK_DIR=$(mktemp -d "obitools4.XXXXXX")
trap '[[ -d "$WORK_DIR" ]] && { chmod -R +w "$WORK_DIR"; rm -rf "$WORK_DIR"; }' EXIT

mkdir -p "${WORK_DIR}/cache"

# Create installation directory
mkdir -p "${INSTALL_DIR}/bin" 2>/dev/null \
  || (echo "Please enter your password for installing obitools in ${INSTALL_DIR}" 1>&2 \
      && sudo mkdir -p "${INSTALL_DIR}/bin")

if [[ ! -d "${INSTALL_DIR}/bin" ]]; then
  echo "Error: Could not create ${INSTALL_DIR}/bin directory" 1>&2
  exit 1
fi

INSTALL_DIR="$(cd "${INSTALL_DIR}" && pwd)"

echo "================================" 1>&2
echo "OBITools4 Installation" 1>&2
echo "================================" 1>&2
echo "VERSION=$VERSION" 1>&2
echo "OS=$OS  ARCH=$ARCH" 1>&2
echo "WORK_DIR=$WORK_DIR" 1>&2
echo "INSTALL_DIR=$INSTALL_DIR" 1>&2
echo "OBITOOLS_PREFIX=$OBITOOLS_PREFIX" 1>&2
echo "================================" 1>&2

pushd "$WORK_DIR" > /dev/null

# Use system Go if available (e.g. golang Docker image), otherwise download it
if command -v go &>/dev/null; then
  echo "Go already available: $(go version)" 1>&2
else
  echo "Downloading Go..." 1>&2
  GOFILE=$(get_go_archive "$OS" "$ARCH")
  GOURL="https://go.dev/dl/${GOFILE}"
  echo "Installing Go from: $GOURL" 1>&2
  curl -fsSL --http1.1 --retry 3 --retry-delay 2 "$GOURL" -o go.tar.gz
  tar zxf go.tar.gz
  rm go.tar.gz
  PATH="$(pwd)/go/bin:$PATH"
  export PATH
  GOPATH="$(pwd)/go"
  export GOPATH
fi

export GOCACHE="$(pwd)/cache"
mkdir -p "$GOCACHE"
echo "GOCACHE=$GOCACHE" 1>&2

# Download OBITools4 source
echo "Downloading OBITools4 v${VERSION}..." 1>&2
echo "Source URL: $OBIURL4" 1>&2

curl -fsSL --http1.1 --retry 3 --retry-delay 2 "$OBIURL4" -o obitools4.zip

unzip -q obitools4.zip

# Find the extracted directory
OBITOOLS_DIR=$(ls -d obitools4-* 2>/dev/null | head -1)

if [ -z "$OBITOOLS_DIR" ] || [ ! -d "$OBITOOLS_DIR" ]; then
  echo "Error: Could not find extracted OBITools4 directory" 1>&2
  exit 1
fi

echo "Building OBITools4..." 1>&2
cd "$OBITOOLS_DIR"
mkdir -p vendor

if [[ -z "$OBITOOLS_PREFIX" ]]; then
  make GOFLAGS="-buildvcs=false"
else
  make GOFLAGS="-buildvcs=false" OBITOOLS_PREFIX="${OBITOOLS_PREFIX}"
fi

# Install binaries
echo "Installing binaries to ${INSTALL_DIR}/bin..." 1>&2
cp build/* "${INSTALL_DIR}/bin" 2>/dev/null \
  || (echo "Please enter your password for installing obitools in ${INSTALL_DIR}" 1>&2 \
      && sudo cp build/* "${INSTALL_DIR}/bin")

popd > /dev/null

echo "" 1>&2
echo "================================" 1>&2
echo "OBITools4 v${VERSION} installed successfully!" 1>&2
echo "Binaries location: ${INSTALL_DIR}/bin" 1>&2
if [[ -n "$OBITOOLS_PREFIX" ]]; then
  echo "Command prefix: ${OBITOOLS_PREFIX}" 1>&2
fi
echo "================================" 1>&2
