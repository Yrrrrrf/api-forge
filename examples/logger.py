from forge.core.logging import *


# Basic logging
log.info("Starting application")
log.success("Database connected")

# Using sections
log.section("Data Processing")

# Using indentation
with log.indent():
    log.info("Processing file 1")
    with log.indent():
        log.debug("Parsing data")
        log.success("Data parsed")

# # Using timer
# with log.timer("Data import"):
#     # ... some time-consuming operation
#     pass

# Using tables
headers = ["Name", "Status", "Count"]
rows = [
    ["Process A", "Running", 42],
    ["Process B", "Stopped", 18]
]
