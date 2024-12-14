#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Creating fast_forge directory structure...${NC}"

# Create main package directory
mkdir -p src/fast_forge

# Create main __init__.py
touch src/fast_forge/__init__.py
touch src/fast_forge/forge.py

# Create and populate tools directory
mkdir -p src/fast_forge/tools/auth
touch src/fast_forge/tools/__init__.py
touch src/fast_forge/tools/db.py
touch src/fast_forge/tools/model.py
touch src/fast_forge/tools/api.py
touch src/fast_forge/tools/auth/__init__.py
touch src/fast_forge/tools/auth/jwt.py
touch src/fast_forge/tools/auth/oauth.py
touch src/fast_forge/tools/auth/rbac.py

# Create and populate gen directory
mkdir -p src/fast_forge/gen/handlers
touch src/fast_forge/gen/__init__.py
touch src/fast_forge/gen/table.py
touch src/fast_forge/gen/view.py
touch src/fast_forge/gen/fn.py
touch src/fast_forge/gen/proc.py
touch src/fast_forge/gen/handlers/__init__.py
touch src/fast_forge/gen/handlers/crud.py
touch src/fast_forge/gen/handlers/sql.py

# Create and populate core directory
mkdir -p src/fast_forge/core
touch src/fast_forge/core/__init__.py
touch src/fast_forge/core/logging.py
touch src/fast_forge/core/config.py
touch src/fast_forge/core/errors.py

# Set permissions
chmod -R 755 src/fast_forge

# Print success message
echo -e "${GREEN}Directory structure created successfully!${NC}"

# Print the tree structure
echo -e "${BLUE}\nDirectory structure:${NC}"
tree src/fast_forge
