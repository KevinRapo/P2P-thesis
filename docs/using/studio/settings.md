# Settings

Local preferences of this computer.

- **Workspace folder:** where the Studio keeps the active scenario, the experiment
  being prepared, the network cache and the browser state. The default is
  `%LOCALAPPDATA%\MARLEM`; choose another and *Use this folder*, or set
  `MARLEM_HOME` (environment or `.env`), which wins over both. Existing files are not
  moved.
- **Network cache:** built networks are kept on disk, so they open in a fraction of a
  second instead of 3-4 s. The Studio prepares the LV and MV networks at start-up;
  *Prepare* builds the larger levels (up to 120 MB each), *Clear cache* empties it.
- **Appearance:** dark mode.
