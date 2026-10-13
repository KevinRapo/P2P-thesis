"""Prints each test's docstring first, so the run output says what was checked."""

import inspect

import pytest


@pytest.fixture(autouse=True)
def _describe(request):
    doc = inspect.getdoc(request.function)
    if doc:
        print(doc, end="\n\n")
