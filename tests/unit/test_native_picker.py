import sys

import pytest

from workflow_app.native_picker import PickerUnavailable, _read_picked_path


def _emitting(source):
    return [sys.executable, "-c", source]


def test_a_chosen_path_comes_back_stripped():
    assert (
        _read_picked_path(_emitting("print('/Users/operator/source')"))
        == "/Users/operator/source"
    )


def test_a_cancelled_dialog_reports_no_path():
    assert _read_picked_path(_emitting("print('')")) is None


def test_a_failed_dialog_raises_with_its_stderr():
    with pytest.raises(PickerUnavailable, match="no display available"):
        _read_picked_path(
            _emitting(
                "import sys; sys.stderr.write('no display available'); sys.exit(1)"
            )
        )


def test_a_missing_chooser_binary_raises():
    with pytest.raises(PickerUnavailable):
        _read_picked_path(["workcrew-no-such-chooser"])
