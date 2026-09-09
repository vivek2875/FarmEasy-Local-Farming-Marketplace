"""Read-only FarmEasy analytics API package."""

from .app import create_app, create_production_app

__all__ = ["create_app", "create_production_app"]
