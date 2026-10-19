#include "duress.h"

#include <furi.h>
#include <furi_hal.h>

// ---------------------------------------------------------------------
// 1. The duress sequence. Same Up/Down/Left/Right/Ok d-pad presses the
// real PIN uses. Edit this to something your hand can produce under
// stress, distinct from the real PIN.
// ---------------------------------------------------------------------
static const InputKey duress_pin_sequence[] = {
    InputKeyUp,
    InputKeyDown,
    InputKeyLeft,
    InputKeyRight,
};
#define DURESS_PIN_LENGTH (sizeof(duress_pin_sequence) / sizeof(InputKey))

// SD wipe window: LBA 0-2047 inclusive = 2048 sectors = 1 MiB, per spec.
#define WIPE_SECTOR_SIZE 512u
#define WIPE_LBA_START 0u
#define WIPE_LBA_END 2047u

bool duress_pin_matches(const InputKey* keys, uint8_t length) {
    if(length != DURESS_PIN_LENGTH) {
        return false;
    }
    bool match = true;
    for(uint8_t i = 0; i < DURESS_PIN_LENGTH; i++) {
        if(keys[i] != duress_pin_sequence[i]) {
            match = false;
        }
    }
    return match;
}

// --- Step A: SD card -----------------------------------------------------
static void wipe_sd_card(void) {
    if(furi_hal_sd_get_card_state() != FuriStatusOk) {
        // No card, or not initialized -- nothing to overwrite. Per spec
        // this must fall through to flash + reset, not hang or retry.
        return;
    }

    uint32_t zero_block[WIPE_SECTOR_SIZE / sizeof(uint32_t)] = {0};

    for(uint32_t lba = WIPE_LBA_START; lba <= WIPE_LBA_END; lba++) {
        // Return value intentionally ignored: a mid-run failure (bad
        // sector, card pulled) must not abort the sequence -- Steps C
        // and D still have to run either way.
        furi_hal_sd_write_blocks(zero_block, lba, 1);
    }
}

// --- Step B: RAM secrets --------------------------------------------------
static void scrub_known_secrets(Desktop* desktop) {
    UNUSED(desktop);
    // Intentionally empty for now -- see PATCH_NOTES.md. The real unlock
    // PIN used to live at desktop->settings.pin_code and got zeroed right
    // here; that field is gone in your build (PIN storage moved to RTC
    // backup registers when internal LFS was removed), and I don't have a
    // confirmed accessor for its replacement to scrub instead of
    // guessing at one. Point me at it (or `git grep -n pin_fails` in
    // applications/services/desktop and paste back the RTC calls it
    // finds) and I'll fill this in for real.
}

// --- Step C: internal flash vector table ----------------------------------
static void destroy_boot_vector(void) {
    // furi_hal_flash_erase() runs in its own critical section and handles
    // unlock/lock internally -- do not wrap this in a manual
    // HAL_FLASH_Unlock()/HAL_FLASH_Lock() pair. On the WB55 it's also the
    // thing that coordinates the erase with the CM0 BLE/FUS core over
    // IPCC; raw HAL_FLASH_* calls skip that coordination entirely.
    furi_hal_flash_erase(0); // page 0 == 0x08000000: vector table + reset stub
}

// --- Step D + orchestration ------------------------------------------------
void execute_duress_wipe(Desktop* desktop) {
    // Deliberately NOT wrapped in __disable_irq(): furi_hal_sd_write_blocks()
    // completes via DMA/SDIO-controller interrupt on this HAL. Mask
    // interrupts first and Step A hangs forever waiting on a completion
    // signal that can now never fire.
    wipe_sd_card();
    scrub_known_secrets(desktop);
    destroy_boot_vector();
    NVIC_SystemReset(); // does not return
}