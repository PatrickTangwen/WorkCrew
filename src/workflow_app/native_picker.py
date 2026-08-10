"""Native OS file and folder choosers for the local WorkCrew UI.

The UI runs in the operator's ordinary browser, where no web API can return an
absolute filesystem path. The server therefore opens the host's own chooser --
Finder on macOS, the Tk dialog elsewhere -- and hands the picked path back.
Both paths run in a subprocess so the GUI never shares a thread with uvicorn.
"""

import subprocess
import sys

_OSASCRIPT = """
on run argv
\tset promptText to item 1 of argv
\tset startFolder to POSIX file (item 2 of argv)
\ttry
\t\ttell application "System Events"
\t\t\tactivate
\t\t\tset chosen to {verb} with prompt promptText default location startFolder
\t\tend tell
\ton error number -128
\t\treturn ""
\tend try
\treturn POSIX path of chosen
end run
"""

_OSASCRIPT_VERBS = {"directory": "choose folder", "file": "choose file"}


class PickerUnavailable(RuntimeError):
    """The host could not open a native chooser."""


def pick_path(mode, prompt, default_location):
    """Open the host's native chooser; return the picked path, or None if cancelled."""
    if sys.platform == "darwin":
        return _pick_with_osascript(mode, prompt, default_location)
    return _pick_with_tk(mode, prompt, default_location)


def _pick_with_osascript(mode, prompt, default_location):
    script = _OSASCRIPT.format(verb=_OSASCRIPT_VERBS[mode])
    return _read_picked_path(["osascript", "-e", script, prompt, str(default_location)])


def _pick_with_tk(mode, prompt, default_location):
    return _read_picked_path(
        [
            sys.executable,
            "-m",
            "workflow_app.native_picker",
            mode,
            prompt,
            str(default_location),
        ]
    )


def _read_picked_path(command):
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise PickerUnavailable(str(exc)) from exc
    if completed.returncode != 0:
        raise PickerUnavailable(
            completed.stderr.strip() or "The native file chooser failed to open"
        )
    # Both chooser backends report a cancelled dialog as empty output.
    return completed.stdout.strip() or None


def _run_tk_dialog(mode, prompt, default_location):
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if mode == "directory":
            return filedialog.askdirectory(title=prompt, initialdir=default_location)
        return filedialog.askopenfilename(title=prompt, initialdir=default_location)
    finally:
        root.destroy()


if __name__ == "__main__":
    mode, prompt, default_location = sys.argv[1:4]
    sys.stdout.write(_run_tk_dialog(mode, prompt, default_location))
