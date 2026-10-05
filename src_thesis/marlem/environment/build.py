"""Build a market engine from an ``EngineSpec``."""

from __future__ import annotations

from typing import Optional

from src_thesis.marlem.core.engine import EngineSpec, MarketEngine
from src_thesis.marlem.environment.engine_lem import LemEngine


def build_engine(spec: EngineSpec, grid: Optional[object] = None) -> MarketEngine:
    """The engine for ``spec`` (today always the original ``LocalEnergyMarket``)."""
    return LemEngine(spec, grid)
