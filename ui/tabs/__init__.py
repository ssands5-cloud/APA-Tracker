"""Demo tabs: self-contained HTML fragments rendered from the database.

Static HTML on purpose. The project's UI story is a file a captain can open
at a venue with no server and possibly no internet (see
scripts/render_demo_html.py and scripts/build_captains_edge.py), and
ui/dashboard_stub.py is still an explicit placeholder rather than a
committed framework choice. A tab here renders markup and nothing else, so
it can be embedded in the demo, opened alone, or asserted against in tests.
"""
