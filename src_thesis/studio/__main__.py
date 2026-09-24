import os

from .app import main

main(
    port=int(os.environ.get("MARLEM_STUDIO_PORT", "8080")),
    show=os.environ.get("MARLEM_STUDIO_SHOW", "1") == "1",
)
