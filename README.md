# WARNO Solo 10v10

Experimental Windows helper that expands a local WARNO Skirmish lobby to ten
slots per side, plus a tool to restore saved lobby settings to vanilla 4v4.

**This is an external memory patch, not a normal Steam Workshop mod.** It is
unofficial and is not endorsed by Eugen Systems. It is intended for solo
Skirmish; the current helper does not automatically detect multiplayer or the
current menu. Use the shortcut to start a solo session, or run it from the
Solo menu if WARNO is already open. Quit and restore 4v4 before multiplayer.

## What it changes

- Enable 10v10 changes three instruction bytes in the running game. It checks
  the executable SHA-256, target process path, and full surrounding function.
  It does not modify `WARNO.exe` on disk.
- WARNO may save a lobby containing 19 AI. Closing the game removes the memory
  patch but **does not remove that saved lobby**, which can break vanilla
  Skirmish on the next launch.
- Restore 4v4 backs up the latest profile, then trims the saved AI list and AI
  count to vanilla limits. It preserves existing object IDs, deck properties,
  statistics, and unrelated profile records. It refuses to write while WARNO
  is running.
- A hidden helper started by Enable 10v10 waits for that game process to exit
  and attempts the same profile cleanup. Use the explicit restore shortcut
  before a vanilla session, especially after a reboot or interrupted helper.

## Requirements

- Windows 64-bit, Windows PowerShell 5.1 or later.
- [Python 3.14 or later, 64-bit](https://www.python.org/downloads/windows/),
  including `pythonw.exe`. No third-party Python packages are required.
- Your own licensed WARNO installation. Only the executable below is supported:

| Build detail | Supported value |
| --- | --- |
| Steam build | `24793975` |
| Executable size | `55,736,360` bytes |
| SHA-256 | `70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8` |

Updates with a different executable are refused. Do not remove the checks or
reuse these addresses on another build.

## Setup

1. Download or clone this repository to a permanent, writable folder.
2. Open PowerShell in that folder and run:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1
   ```

3. Select `WARNO.exe`, the `PROFILE.profile2` for the Steam account you play
   with, and Python if prompted. Play the game once first if no profile exists.
   The Steam profile is usually under
   `Steam\userdata\<account-id>\1611600\remote\PROFILE.profile2`.
4. Setup creates **WARNO - Enable 10v10** and **WARNO - Restore 4v4** desktop
   shortcuts. It saves your paths in Git-ignored `config.local.json`.

Setup validates the build and reads the profile, but does not patch the game
or alter the profile. Keep this folder in place; the shortcuts point to it.
If you move it, run Setup again. Existing shortcuts with these names are updated.

### Enable 10v10

1. Run **WARNO - Enable 10v10**. It checks the saved lobby, starts WARNO through
   Steam if needed, waits for its window, then applies the patch automatically.
   If WARNO is already running, go to the **Solo menu** before running it.
2. Wait for the green success message. The game can continue loading afterward.
3. Open **Solo -> Skirmish**, then add AI: you plus nine allied AI versus ten
   enemy AI. If a lobby was already open, leave and reopen it.

Run Enable again for each new game process. Close its visible window after
success; the cleanup helper continues in the background.

Startup waits up to three minutes. If Steam needs an update or displays a
launch prompt, finish that step and run the shortcut again. `-CheckOnly`
never launches WARNO or changes its saved profile. An interrupted previous
cleanup is repaired, with a backup if changes are needed, before a new launch.

The desktop shortcut runs a PowerShell launcher, which calls the Python
memory patch. If it reports an error, check `launcher-enable.log` beside the
scripts. A lobby stays 4v4 until the launcher reports success and you leave
and reopen the lobby. After downloading an update, run
`Create-Desktop-Shortcuts.ps1` to point your shortcuts at the updated copy.

### Restore vanilla 4v4

1. Quit WARNO completely. Allow around ten seconds for background cleanup.
2. Run **WARNO - Restore 4v4** and wait for success.
3. Start WARNO normally and open **Solo -> Skirmish**.

The restore operation is a no-op when the saved lobby already fits vanilla
limits. Do not run Enable for a vanilla session. Backups are under
`Documents\WARNO_Profile_Backups`; local logs are beside the scripts.

## Validation and limitations

Observed on the supported build: the RAM patch produces a ten-slot-per-team
lobby, and a surgically repaired 19-AI profile opens normally in vanilla 4v4.
The repository includes synthetic profile tests so no player's profile needs
to be distributed:

```powershell
py -3.14 -m unittest discover -s tests -v
```

**Not yet verified end to end:** a complete 19-AI battle and the background
helper's complete game-exit/restart cycle. The parser supports the observed
ESAV v3/CNDF layout and refuses ambiguous or unsupported profiles. Steam Cloud
can race with a local profile write; if cleanup fails, keep WARNO closed and
run Restore again. This tool does not manage Cloud settings.

The launcher cannot enforce the Solo-menu requirement. No anti-cheat bypass,
DRM bypass, game executable, player profile, or game asset is included.

## Distribution and game terms

Source availability is not permission from Eugen Systems to modify WARNO.
WARNO's [EULA](https://store.steampowered.com//eula/1611600_eula_0), especially
section 1.2, and Eugen's [Terms of Use](https://eugensystems.com/terms-of-use/)
restrict certain external modification tools. This project has no approval
from Eugen Systems; do not represent it as an approved Workshop mod.

## Format references

The profile parser was written for this tool using observations of the local
profile format. Historical CNDF documentation in
[moddingSuite](https://github.com/is-consulting/moddingSuite/blob/master/ndfbin_reversing.txt)
helped identify type tags. No moddingSuite source, original third-party helper,
game binary, disassembly dump, or real saved profile is included here.
