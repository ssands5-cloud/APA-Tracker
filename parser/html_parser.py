"""
Generic HTML table/summary parsing helpers shared by all scraper modules.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_table(html: str, table_selector: str, row_selector: str, columns: list[str]) -> list[dict[str, Any]]:
    """Parse an HTML table into a list of dicts keyed by `columns`.

    Cells beyond len(columns) are ignored; rows with fewer cells than
    `columns` are skipped (usually a header/footer row that slipped
    through the row_selector).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(table_selector)
    if table is None:
        logger.warning("Table not found for selector: %s", table_selector)
        return []

    records: list[dict[str, Any]] = []
    for row in table.select(row_selector):
        cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < len(columns):
            logger.debug("Skipping short row: %s", cells)
            continue
        records.append(dict(zip(columns, cells)))
    return records


def parse_summary_block(html: str, block_selector: str) -> dict[str, str]:
    """Parse a labeled key/value summary block (e.g. a player profile card)
    into a flat dict. Assumes label/value pairs live in adjacent elements
    with `.label` / `.value` classes; adjust to match the real markup once
    inspected.
    """
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one(block_selector)
    if block is None:
        logger.warning("Summary block not found for selector: %s", block_selector)
        return {}

    result: dict[str, str] = {}
    for label_el in block.select(".label"):
        value_el = label_el.find_next_sibling(class_="value")
        if value_el:
            result[label_el.get_text(strip=True)] = value_el.get_text(strip=True)
    return result
