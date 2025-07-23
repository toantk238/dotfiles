# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code for all projects

## System Prompt and MCP Configuration

### MCP Servers Available
The following MCP (Model Context Protocol) servers are available globally for all Claude Code projects:

1. **Sequential Thinking Server** (`@modelcontextprotocol/server-sequential-thinking`)
   - Enables dynamic and reflective problem-solving through structured thinking
   - Useful for breaking down complex problems, planning with room for revision, and multi-step solutions
   - Can be invoked using the `mcp__sequential-thinking__sequentialthinking` tool

2. **Memory Server** (`@modelcontextprotocol/server-memory`)
   - Provides a persistent knowledge graph for storing and retrieving information
   - Useful for maintaining context across conversations and storing important project knowledge
   - Available tools:
     - `mcp__memory__create_entities` - Create entities in the knowledge graph
     - `mcp__memory__create_relations` - Create relationships between entities
     - `mcp__memory__add_observations` - Add observations to entities
     - `mcp__memory__search_nodes` - Search the knowledge graph
     - `mcp__memory__read_graph` - Read the entire knowledge graph

### Using MCP Servers
When working with complex problems or needing to maintain long-term context:
- Use the sequential thinking server for complex refactoring or architectural decisions
- Use the memory server to store important project knowledge, API patterns, or team decisions
- These tools are especially helpful for maintaining consistency across the codebase migration

### Example Use Cases

#### Sequential Thinking Server
```
# Use for complex migrations or refactoring:
- Breaking down the Spring Boot to Go migration into phases
- Planning API endpoint conversions with potential revisions
- Analyzing dependencies and determining migration order
- Solving complex entity relationship mappings
```

#### Memory Server
```
# Store project-specific knowledge:
- API endpoint mappings between Spring Boot and Go
- Common patterns used in the codebase
- Team decisions about architecture
- Migration progress and completed tasks
- Database schema changes and reasons
```
