#!/usr/bin/env bash
# Build the pinned native daemon with email evidence and automatic Jev discovery and signed-message briefs.
# Sources: kenn-io/msgvault v0.21.0, go.dev/dl, oven-sh/bun bun-v1.3.14.
set -euo pipefail

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 || $# -ne 1 ]]; then
    echo 'Usage on Linux x86_64: build-signed-mail-brief.sh NEW_OUTPUT_DIRECTORY' >&2
    exit 1
fi
MSGVAULT_OUTPUT=$1
MSGVAULT_BUILD_FILES=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $MSGVAULT_OUTPUT != /* || -e $MSGVAULT_OUTPUT || -L $MSGVAULT_OUTPUT ]]; then
    echo 'Output must be an absolute, non-existing directory.' >&2
    exit 1
fi
for required in curl sha256sum tar unzip patch make gcc g++ node python3; do
    command -v "$required" >/dev/null
done
# Unix socket tests include their test names beneath GOTMPDIR; keep the prefix
# short enough for Linux's 108-byte sockaddr_un path limit.
MSGVAULT_BUILD_STAGE=$(mktemp -d /tmp/mv.XXXXX)
trap 'rm -rf -- "$MSGVAULT_BUILD_STAGE"' EXIT
export GOPATH="$MSGVAULT_BUILD_STAGE/gopath"
export GOCACHE="$MSGVAULT_BUILD_STAGE/go-cache"
export GOTMPDIR="$MSGVAULT_BUILD_STAGE"
export GOTOOLCHAIN=local GOMAXPROCS=2 CGO_ENABLED=1
export PATH="$MSGVAULT_BUILD_STAGE/go/bin:$MSGVAULT_BUILD_STAGE/bun-linux-x64:$PATH"

download() {
    curl --fail --location --silent --show-error --retry 3 "$1" -o "$MSGVAULT_BUILD_STAGE/$2"
    printf '%s  %s\n' "$3" "$MSGVAULT_BUILD_STAGE/$2" | sha256sum --check
}
download https://go.dev/dl/go1.27.1.linux-amd64.tar.gz go.tar.gz \
    63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445
download https://github.com/oven-sh/bun/releases/download/bun-v1.3.14/bun-linux-x64.zip bun.zip \
    951ee2aee855f08595aeec6225226a298d3fea83a3dcd6465c09cbccdf7e848f
download https://codeload.github.com/kenn-io/msgvault/tar.gz/598ca5cc89042ded95e484b5315cc29b9342fa42 source.tar.gz \
    dd539641d913e9d54b055e14d3a57c1506351b0a94296bb357a137c3f363c7cb
tar -xzf "$MSGVAULT_BUILD_STAGE/go.tar.gz" -C "$MSGVAULT_BUILD_STAGE" --no-same-owner --no-same-permissions
tar -xzf "$MSGVAULT_BUILD_STAGE/source.tar.gz" -C "$MSGVAULT_BUILD_STAGE" --no-same-owner --no-same-permissions
unzip -q "$MSGVAULT_BUILD_STAGE/bun.zip" -d "$MSGVAULT_BUILD_STAGE"
cd "$MSGVAULT_BUILD_STAGE/msgvault-598ca5cc89042ded95e484b5315cc29b9342fa42"
patch --batch --fuzz=0 -p1 < "$MSGVAULT_BUILD_FILES/patches/people-email-evidence-v0.21.0.patch"
patch --batch --fuzz=0 -p1 < "$MSGVAULT_BUILD_FILES/patches/mailbox-discovery-v0.21.0.patch"
patch --batch --fuzz=0 -p1 < "$MSGVAULT_BUILD_FILES/patches/signed-mail-brief-v0.21.0.patch"
go fmt ./...
go vet -p 2 -tags 'fts5 sqlite_vec' ./...
go test -p 2 -tags 'fts5 sqlite_vec' -timeout 20m \
    -run 'Test(PersonSweep|LoadPersonSweep|ListPersonSweep|SearchPersonSweep|HydratePersonSweep|BuildBrief)' ./internal/store
go test -p 2 -tags 'fts5 sqlite_vec' -timeout 20m \
    ./internal/peoplesweep ./internal/personfacts ./internal/vector/preprocess ./internal/mailboxdiscovery
go test -p 2 -tags 'fts5 sqlite_vec' -timeout 20m -run 'TestSignedMailbox|TestSigningPerson|TestMailbox|TestPersonMatchScoring|TestPersonMatchConsent' ./internal/store ./internal/api ./cmd/msgvault/cmd
make build VERSION=v0.21.0-signed-brief-1 COMMIT=598ca5cc-signed-brief-1
mkdir -m 0755 "$MSGVAULT_OUTPUT"
install -m 0755 msgvault msgvault-codex-bridge "$MSGVAULT_OUTPUT/"
sha256sum "$MSGVAULT_OUTPUT/msgvault" "$MSGVAULT_OUTPUT/msgvault-codex-bridge" \
    > "$MSGVAULT_OUTPUT/SHA256SUMS"
cp "$MSGVAULT_BUILD_FILES/patches/people-email-evidence-v0.21.0.patch" "$MSGVAULT_OUTPUT/"
cp "$MSGVAULT_BUILD_FILES/patches/mailbox-discovery-v0.21.0.patch" "$MSGVAULT_OUTPUT/"
cp "$MSGVAULT_BUILD_FILES/patches/signed-mail-brief-v0.21.0.patch" "$MSGVAULT_OUTPUT/"
"$MSGVAULT_OUTPUT/msgvault" version
echo "Built and tested: $MSGVAULT_OUTPUT"
