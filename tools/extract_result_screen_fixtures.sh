#!/usr/bin/env bash
# Extract result-screen fixture frames into tests/fixtures/result_screen/.
# Each scenario gets a sub-directory with 00.png / 01.png / 02.png
# (the full 3-frame None streak starting at game_end_index - 2).
#
# Run from repo root:
#   bash tools/extract_result_screen_fixtures.sh

set -e

FGS="tests/fixtures/full_game_session"
SES="sessions"
OUT="tests/fixtures/result_screen"

copy3() {
    local folder="$1"; local src="$2"; local f0="$3"; local f1="$4"; local f2="$5"
    mkdir -p "$OUT/$folder"
    cp "$src/$f0.png" "$OUT/$folder/00.png"
    cp "$src/$f1.png" "$OUT/$folder/01.png"
    cp "$src/$f2.png" "$OUT/$folder/02.png"
    echo "  $folder"
}

echo "=== Required ==="
copy3 win_normal_blue      "$FGS/full_game_blue-blue"            00381 00382 00383
copy3 win_overtime_blue    "$FGS/full_game_overtime_blue-blue"   00522 00523 00524
copy3 win_forfeit_blue     "$FGS/full_game_forfeit_blue-blue"    00259 00260 00261
copy3 loss_normal_blue     "$SES/loss_normal_blue"               00462 00463 00464
copy3 loss_overtime_blue   "$SES/loss_overtime_blue"             00444 00445 00446
copy3 loss_forfeit_orange  "$SES/loss_forfeit_orange"            00179 00180 00181
copy3 loss_overtime_orange "$SES/win_overtime_orange_blue"       00390 00391 00392

echo ""
echo "=== Optional ==="
copy3 win_normal_orange    "$FGS/full_game_orange-blue"              00428 00429 00430
copy3 win_overtime_orange  "$FGS/full_game_overtime_orange-blue"     00548 00549 00550

echo ""
echo "Done. Verify each 00.png shows the result card before committing."
