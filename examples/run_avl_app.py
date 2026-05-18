"""Launch the AC_Design_Toolbox AVL Dash app.

The app requires an uploaded ``AircraftDefinition`` JSON before exporting AVL
geometry or running cases. Set ``ACDT_AVL_APP_DISABLE_BROWSER=1`` if you want
to suppress the browser-open hook in local workflows.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ac_design_toolbox.apps.avl import create_avl_app  # noqa: E402


HOST = "127.0.0.1"
PORT = int(os.environ.get("ACDT_AVL_APP_PORT", "8060"))


def main() -> None:
    """Run the standalone AVL Dash app."""

    app = create_avl_app()
    url = f"http://{HOST}:{PORT}/"
    if os.environ.get("ACDT_AVL_APP_DISABLE_BROWSER", "0") != "1":
        webbrowser.open(url)
    app.run(debug=False, host=HOST, port=PORT, use_reloader=False)


if __name__ == "__main__":
    main()
