#!/usr/bin/env python3
"""Small data models for the PDF multifile searcher.

This module contains lightweight dataclasses used across the project so
they can be imported from multiple places without creating circular
dependencies with the GUI code.
"""
from dataclasses import dataclass
import pymupdf as fitz


@dataclass
class Match:
    match_id: int
    page_number: int
    location: fitz.Rect
    context_location: fitz.Rect
    context: str = ""
