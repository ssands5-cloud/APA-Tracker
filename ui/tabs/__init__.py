"""Demo tabs: self-contained HTML fragments rendered from the database.

Static HTML on purpose. The project's UI story is a file a captain can open
at a venue with no server and possibly no internet (see
scripts/render_demo_html.py, scripts/build_captains_edge.py, and
ui/dashboard.py, the static Coach Dashboard that replaced the old
ui/dashboard_stub.py placeholder). A tab here renders markup and nothing
else, so it can be embedded in the demo, opened alone, or asserted against
in tests.
"""
