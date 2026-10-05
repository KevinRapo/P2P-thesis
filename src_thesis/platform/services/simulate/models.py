"""Data types of the Simulate page: the controllers it offers."""

from pydantic import BaseModel, Field


class ControllerParam(BaseModel):
    """One parameter of a scripted controller.

    Attributes:
        name: Parameter name.
        label: Name shown in the UI.
        default: Value used when none is given.
        low: Smallest allowed value.
        high: Largest allowed value.
        help: One sentence explaining it.
    """

    name: str
    label: str
    default: float
    low: float
    high: float
    help: str = ""


class ControllerInfo(BaseModel):
    """A scripted controller the Simulate page offers.

    Attributes:
        name: Registry name (``RunCell.algorithm`` of a simulate run).
        title: Short title.
        description: What it does.
        params: Its parameters.
    """

    name: str
    title: str
    description: str
    params: list[ControllerParam] = Field(default_factory=list)
