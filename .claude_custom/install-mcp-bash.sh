#!/bin/bash

# Install MCP servers config from .mcp.json to ~/.claude.json
# This script merges the mcpServers configuration into the Claude config file

set -e

# Set up logging
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME=$(basename "$0")
LOG_FILE="$SCRIPT_DIR/${SCRIPT_NAME%.sh}.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1
SOURCE_FILE="$SCRIPT_DIR/.local.mcp.json"
TARGET_FILE="$HOME/.claude.json"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Installing MCP servers configuration...${NC}"

# Check if source file exists
if [ ! -f "$SOURCE_FILE" ]; then
    echo -e "${RED}Error: Source file $SOURCE_FILE not found!${NC}"
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is not installed. Please install jq first.${NC}"
    echo "On macOS: brew install jq"
    echo "On Linux: sudo apt-get install jq or sudo yum install jq"
    exit 1
fi

# No need to create directory for ~/.claude.json

# Backup existing config if it exists
if [ -f "$TARGET_FILE" ]; then
    BACKUP_FILE="$TARGET_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}Backing up existing config to $BACKUP_FILE...${NC}"
    cp "$TARGET_FILE" "$BACKUP_FILE"
fi

# Read the mcpServers configuration from source
MCP_SERVERS=$(jq '.mcpServers' "$SOURCE_FILE")

if [ "$MCP_SERVERS" = "null" ]; then
    echo -e "${RED}Error: No mcpServers configuration found in $SOURCE_FILE${NC}"
    exit 1
fi

# If target file doesn't exist, create it with the mcpServers configuration
if [ ! -f "$TARGET_FILE" ]; then
    echo -e "${YELLOW}Creating new config file...${NC}"
    echo "{}" | jq --argjson servers "$MCP_SERVERS" '. + {mcpServers: $servers}' > "$TARGET_FILE"
else
    # Merge the mcpServers configuration into existing config
    echo -e "${YELLOW}Merging configuration into existing file...${NC}"
    
    # Read existing config
    EXISTING_CONFIG=$(cat "$TARGET_FILE")
    
    # Merge configurations (new servers override existing ones with same keys)
    MERGED_CONFIG=$(echo "$EXISTING_CONFIG" | jq --argjson servers "$MCP_SERVERS" '
        if .mcpServers then
            .mcpServers = (.mcpServers + $servers)
        else
            . + {mcpServers: $servers}
        end
    ')
    
    # Write merged config back
    echo "$MERGED_CONFIG" | jq '.' > "$TARGET_FILE"
fi

# Verify the installation
if jq -e '.mcpServers' "$TARGET_FILE" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ MCP servers configuration installed successfully!${NC}"
    echo -e "${GREEN}Configuration file: $TARGET_FILE${NC}"
    echo -e "\nInstalled MCP servers:"
    jq -r '.mcpServers | to_entries[] | "  - \(.key)"' "$TARGET_FILE"
else
    echo -e "${RED}Error: Failed to verify installation${NC}"
    exit 1
fi
