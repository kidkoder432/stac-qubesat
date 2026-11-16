#!/bin/sh
# Copy everything in pycubed/NewCode/ onto the CIRCUITPY drive, replacing files that already exist.
# Nothing on the board is deleted. Usage: ./deploy_to_board.sh [/path/to/CIRCUITPY]

SRC="$(cd "$(dirname "$0")" && pwd)/pycubed/NewCode/"
DEST="${1:-/Volumes/CIRCUITPY}"

if [ ! -d "$DEST" ]; then
    echo "CIRCUITPY is not mounted at $DEST (pass the path as an argument if it is elsewhere)." >&2
    exit 1
fi

# -t keeps timestamps; --no-perms/--no-owner/--no-group because the board is FAT.
rsync -rtv --no-perms --no-owner --no-group \
    --exclude '__pycache__/' --exclude '.DS_Store' --exclude '._*' \
    "$SRC" "$DEST/" || exit 1

sync
echo "Copied $SRC to $DEST. The board reloads on its own after a write; eject before unplugging."
