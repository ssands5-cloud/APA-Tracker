"""Fixture-backed ingest pipeline.

Turns the scraper's captured GraphQL fixtures into rows in the SQLite
database, then into the workbook, demo JSON and Captain's Edge artifacts.

The scraper (`scraper/full_auto_scrape.py`) is contract-bound and is not
touched by anything here -- this package starts where fixture generation
ends. See README-scraper.md for the fixture contract itself.
"""
