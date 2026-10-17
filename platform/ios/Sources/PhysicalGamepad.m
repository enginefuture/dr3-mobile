// The same physical backend and HID edge handling are tested on macOS.
// The UIKit overlay owns dm_gamepad_reset; retain a separate physical reset.
#define dm_gamepad_reset dm_physical_gamepad_reset
#include "../../../native/gamepad_mac.m"
