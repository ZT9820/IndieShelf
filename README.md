# IndieShelf

A lightweight Windows desktop library for organizing, launching, and tracking
your indie games. It uses Python's standard library, so there are no
third-party packages to install.

## Features

- Add games by selecting their `.exe` files.
- Launch a selected game from the library.
- Automatically detect a game's process and track playtime and last-played
  time while the app is open.
- Set each game's status to **Playing** or **Finished**.
- Resize the window; the layout, text, and game-list columns adjust to fit.
- Keep your library in a local data file on your PC.

## Requirements

- Windows 10 or later.
- Python 3.10 or later with **Tcl/Tk** installed (included in the standard
  Windows Python installer).

## Run

1. Install Python from [python.org](https://www.python.org/downloads/windows/).
   Ensure the Python launcher is installed.
2. Download or clone this repository.
3. Double-click **Start IndieShelf.bat**.

You can also open `IndieShelf.pyw` directly. If Windows asks which app to use,
install Python with its file-association option enabled.

## Use

1. Click **+ Add game** and choose the game's `.exe`.
2. Select the game and click **▶ Launch selected**, double-click its row, or
   press **Enter**.
3. Use **Set status** to switch manually between **Playing** and **Finished**.
4. Use **Remove** to remove a game from the list. This does not uninstall it.

Playtime is checked every three seconds and tracked only while IndieShelf is
open and the selected executable itself is running. Close the app and playtime
tracking pauses.

## Data and privacy

The app does not need an account or network access. Your library is saved at
`%LOCALAPPDATA%\IndieShelf\games.json`.

On the first launch after updating from Simple Game Library, IndieShelf copies
your existing library into the new data folder. The old data file is left
untouched as a backup.

## Run tests

From the repository folder, run:

```powershell
python -m unittest discover -s tests -v
```

## Acknowledgements

IndieShelf was created by its project author with development assistance from
GitHub Copilot, an AI assistant. The author guides the project and is
responsible for reviewing and publishing its contents.

## License

No license has been added yet. Choose a license before distributing or
relicensing the project.
