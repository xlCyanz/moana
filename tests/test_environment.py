"""Smoke checks for installed native dependencies, not MoanArt rendering."""

import io
from importlib.metadata import version
from importlib.resources import files

import aggdraw
import numpy as np
import pytest
from PIL import Image
from pydantic import BaseModel, ConfigDict, ValidationError

import moanart


def test_installed_package_metadata_and_typing_marker() -> None:
    assert version("moanart") == moanart.__version__
    assert files("moanart").joinpath("py.typed").is_file()


def test_numpy_pillow_png_roundtrip() -> None:
    pixels = np.array([[[12, 34, 56, 255], [0, 0, 0, 0]]], dtype=np.uint8)
    image = Image.fromarray(pixels)
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    with Image.open(output) as decoded:
        np.testing.assert_array_equal(np.asarray(decoded), pixels)


def test_aggdraw_native_extension_runs() -> None:
    image = Image.new("RGBA", (2, 2))
    drawing = aggdraw.Draw(image)
    drawing.rectangle((0, 0, 2, 2), aggdraw.Brush("red"))
    drawing.flush()
    assert image.getpixel((0, 0)) == (255, 0, 0, 255)


def test_pydantic_strict_validation_is_available() -> None:
    class Probe(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        count: int

    assert Probe(count=1).count == 1
    with pytest.raises(ValidationError):
        Probe.model_validate({"count": True})
    with pytest.raises(ValidationError):
        Probe.model_validate({"count": 1, "unknown": 2})
