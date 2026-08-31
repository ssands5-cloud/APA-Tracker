"""
Generic HTML table/summary parsing helpers shared by all scraper modules.

Parsing here is deliberately strict. A scraper that returns a wrong number is
far more expensive than one that stops: a wrong number reaches the database,
gets aggregated, and is indistinguishable from a real one months later. So a
table whose shape does not match what the caller declared raises rather than
guessing which cell went where.
"""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TableNotFoundError(LookupError):
    """The table selector matched nothing on the page.

    Distinct from "the table was empty": an absent table usually means the
    markup moved or the page is an error/login page, and reporting it as
    zero rows renders a missing result as a definite one.
    """


class TableShapeError(ValueError):
    """A row's cell count does not match the declared column set.

    Carries the offending cells so the caller can see what actually arrived
    rather than re-fetching the page to find out.
    """

    def __init__(self, selector: str, row_index: int, columns: list[str], cells: list[str]) -> None:
        self.selector = selector
        self.row_index = row_index
        self.columns = list(columns)
        self.cells = list(cells)
        super().__init__(
            f"Row {row_index} of {selector!r} has {len(cells)} cell(s) but "
            f"{len(columns)} column(s) were declared. Declared: {self.columns}. "
            f"Received: {self.cells}. The portal markup has probably changed -- "
            f"update the column list in parser/apa_page_map.py rather than "
            f"letting values map to the wrong fields."
        )


def _is_header_row(row) -> bool:
    """True when every cell in the row is a <th>.

    Header rows routinely appear inside <tbody> on this portal, and a header
    row that survives into the results reads as a data row whose values are
    the column captions.
    """
    cells = row.find_all(["td", "th"])
    return bool(cells) and all(cell.name == "th" for cell in cells)


def parse_table(
    html: str,
    table_selector: str,
    row_selector: str,
    columns: list[str],
    *,
    strict: bool = True,
) -> list[dict[str, Any]]:
    """Parse an HTML table into a list of dicts keyed by `columns`.

    Cells are matched to columns by position, so a row of the wrong width
    means every field after the discrepancy is wrong. In strict mode -- the
    default -- that raises :class:`TableShapeError` instead of returning
    plausible-looking, misaligned data.

    Header rows (every cell a ``<th>``) and completely empty rows are skipped
    before the width check, since neither is a shape problem.

    Args:
        html: The page source.
        table_selector: CSS selector for the table.
        row_selector: CSS selector for rows, relative to the table.
        columns: Field names, in the order the cells appear.
        strict: Raise on a shape mismatch. Set ``False`` to log and skip the
            offending row instead -- appropriate only for exploratory work,
            never for a run whose output is ingested.

    Raises:
        TableNotFoundError: `table_selector` matched nothing (strict only).
        TableShapeError: A data row's width did not match `columns` (strict only).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(table_selector)
    if table is None:
        if strict:
            raise TableNotFoundError(
                f"No table matched {table_selector!r}. The page may be a login "
                f"or error page, or the markup has changed."
            )
        logger.warning("Table not found for selector: %s", table_selector)
        return []

    records: list[dict[str, Any]] = []
    for index, row in enumerate(table.select(row_selector)):
        raw_cells = row.find_all(["td", "th"])
        if not raw_cells:
            continue
        if _is_header_row(row):
            logger.debug("Skipping header row %s in %s", index, table_selector)
            continue

        cells = [cell.get_text(strip=True) for cell in raw_cells]
        if len(cells) != len(columns):
            error = TableShapeError(table_selector, index, columns, cells)
            if strict:
                raise error
            logger.warning("%s", error)
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
