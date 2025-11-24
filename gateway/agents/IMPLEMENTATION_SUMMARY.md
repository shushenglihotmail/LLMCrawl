# Azure DevOps Query Pattern Implementation Summary

## Overview

Implemented comprehensive Azure DevOps query pattern support in the LLMCrawl template agent with explicit `azdo:` prefix logic and support for mixed local/Azure DevOps file sources.

## Backend Implementation

### Files Modified

1. **gateway/agents/file_explanation_agent.py**
   - Added `azure_devops_mcp_url` parameter to `CodeIntelligenceAgent.__init__()`
   - Modified `_read_file()` to detect and route query patterns
   - Added `_is_azure_devops_query()` - Pattern detection
   - Added `_read_azure_devops_query()` - Query execution
   - Added `_parse_azure_devops_query()` - Query parsing
   - Enhanced `_read_azure_devops_file()` with detailed logging
   - Added `_list_files()` and `_list_azure_devops_files()` for folder operations

2. **gateway/routers/agent.py**
   - Updated `get_agent()` to pass `azure_devops_mcp_url` from environment

3. **gateway/routers/tools.py**
   - Added `search_azure_devops_files` to tool list

## Features Implemented

### 1. Explicit Prefix Logic
- **Local files**: No prefix (e.g., `src/service.py`)
- **Azure DevOps files**: `azdo:` prefix (e.g., `azdo:src/service.cpp`)
- **Azure DevOps queries**: `azdo:` prefix with patterns (e.g., `azdo:keyword ext:cpp`)
- **No fallback**: If `azdo:` is missing, only local MCP is tried

### 2. Query Pattern Support

#### Inline Format (space-separated)
```
azdo:keyword file:*.json ext:man
```

#### Semicolon Format (explicit parameters)
```
azdo:branch:official/main; path:/src; keyword file:*.h
```

#### Supported Filters
- `file:*.pattern` - Filename pattern matching
- `ext:type` - File extension (without dot)
- `path:/folder` - Search within specific folder
- `branch:name` - Use specific branch (semicolon format only)

#### Operators
- `AND` - All conditions must match (default behavior)
- `OR` - Any condition can match

### 3. Mixed Source Support
Users can specify multiple paths with different sources:
```
tests/local_test.py
azdo:src/remote_service.cpp
azdo:compute ext:cpp
docs/notes.md
```

### 4. Query Execution
- Pattern detection via `_is_azure_devops_query()` checks for keywords: `file:`, `ext:`, `path:`, `branch:`, `AND`, `OR`
- Query parsing extracts parameters using regex
- Search executes via Azure DevOps MCP `search_azure_devops_files` tool
- Reads up to 10 matching files
- Combines content into single response with file markers

## Documentation Created

### For Developers

1. **TARGET_PATHS_EXAMPLES.md** (comprehensive guide)
   - Complete syntax reference
   - Category-organized examples (local, Azure DevOps, queries, mixed)
   - Workflow examples
   - Error handling guide
   - Tips and best practices
   - HiChat webclient integration suggestions

2. **QUICK_REFERENCE.md** (concise cheat sheet)
   - Basic syntax table
   - Query patterns
   - Common examples
   - Query filters reference
   - Tips and troubleshooting

3. **target_paths_examples.json** (structured data)
   - JSON format for programmatic access
   - Categorized examples
   - Quick reference objects
   - Troubleshooting entries
   - Can be loaded by webclient

### For Users (UI Integration)

4. **target_paths_popup.html** (ready-to-use UI component)
   - Complete HTML/CSS/JS implementation
   - Help icon (❓) next to "Target Paths" label
   - Modal popup with examples
   - "Use This Example" buttons to populate field
   - Responsive design with scrolling
   - Quick reference tables
   - Tips section
   - Copy-to-clipboard fallback

## HiChat Webclient Integration

### Option 1: Inline Help Icon
Add next to "Target Paths" label:
```html
<label>
  Target Paths:
  <span class="help-icon" onclick="showHelp()">❓</span>
</label>
```

### Option 2: Placeholder with Examples
```html
<textarea placeholder="Enter file paths (one per line)
Examples:
  src/local.py
  azdo:path file:*.json
  azdo:branch:main; keyword ext:cpp">
</textarea>
```

### Option 3: Full Popup (Recommended)
Use the provided `target_paths_popup.html`:
1. Copy HTML into webclient template
2. Adjust field selector in `useExample()` function
3. Style as needed to match theme
4. Add help icon next to label

### Option 4: Load from JSON
```javascript
fetch('/api/target-paths-examples')
  .then(res => res.json())
  .then(data => {
    // Populate examples dropdown or help popup
    renderExamples(data.targetPathExamples);
  });
```

## Testing Checklist

### Backend Tests
- [ ] Local file read: `src/file.py`
- [ ] Azure DevOps file read: `azdo:src/file.cpp`
- [ ] Query with file pattern: `azdo:keyword file:*.json`
- [ ] Query with extension: `azdo:keyword ext:cpp`
- [ ] Query with path: `azdo:path:/src keyword`
- [ ] Full query: `azdo:branch:main; path:/src; keyword file:*.h`
- [ ] Mixed sources: Multiple lines with local + Azure DevOps
- [ ] No azdo: prefix on Azure DevOps file → Should fail with clear error
- [ ] Query returns 0 files → Should log "no files found"
- [ ] Query returns 10+ files → Should read first 10

### UI Tests
- [ ] Help icon visible next to Target Paths label
- [ ] Help icon opens popup on click
- [ ] Popup displays all example categories
- [ ] "Use This Example" buttons populate field correctly
- [ ] Close button and overlay click close popup
- [ ] Examples show proper formatting (line breaks preserved)
- [ ] Responsive design works on different screen sizes

## Environment Setup

### Required Environment Variables

```bash
# Azure DevOps MCP Server URL
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp-server:8004

# Or for stdio mode in VS Code
# Configure in mcp.json instead
```

### VS Code Integration (Optional)

Users can also use Azure DevOps MCP in VS Code directly:

**%APPDATA%\Code\User\mcp.json**:
```json
{
  "servers": {
    "azure-devops": {
      "type": "stdio",
      "command": "python",
      "args": [
        "-m",
        "azure_devops_mcp_server.main",
        "--mode",
        "stdio"
      ],
      "inputs": [
        {
          "name": "AZURE_DEVOPS_PAT",
          "description": "Azure DevOps Personal Access Token",
          "required": true
        },
        {
          "name": "AZURE_DEVOPS_ORG",
          "description": "Azure DevOps Organization URL",
          "required": true
        }
      ]
    }
  }
}
```

## Query Pattern Examples

### Simple Examples
```
azdo:Microsoft-NanoServer-PowerShell AND file:*.json
azdo:Microsoft-NanoServer-PowerShell ext:man
azdo:compute ext:cpp
azdo:network file:*.h
```

### Advanced Examples
```
azdo:branch:official/rs_sparc_ctr; path:/MergedComponents; Microsoft-NanoServer-PowerShell AND file:*.json
azdo:path:/src/services; authentication file:*Service.cpp
azdo:branch:feature/network; path:/protocols; (tcp OR udp) ext:h
```

### Mixed Source Examples
```
tests/test_network.py
azdo:src/network/NetworkService.cpp
azdo:src/network/NetworkService.h
docs/network-design.md
azdo:network ext:cpp
```

## Error Handling

### User-Facing Errors

1. **"Could not read any target files"**
   - Missing `azdo:` prefix for Azure DevOps files
   - File path incorrect
   - File doesn't exist in repository

2. **"No files found for query"**
   - Query too specific
   - Path/branch incorrect
   - No matching files in repository

3. **"Azure DevOps MCP URL not configured"**
   - Environment variable not set
   - Server not running
   - PAT token invalid

### Developer Logs

All file operations log detailed information:
```python
logger.info(f"Reading Azure DevOps file: {file_path}")
logger.info(f"Executing Azure DevOps query: {query}")
logger.info(f"Found {len(files)} matching files for query")
logger.error(f"Failed to read file {file_path}: {error}")
```

## Performance Considerations

- **Query limit**: Max 10 files per query to avoid token limits
- **Timeout**: 60 seconds for MCP operations
- **Recursive search**: Azure DevOps queries search recursively by default
- **Parallel reads**: Files read sequentially to preserve order

## Future Enhancements

### Potential Features
1. **Query result preview**: Show matching files before reading content
2. **File selection**: Let user select which files from query results to read
3. **Saved queries**: Store frequently used query patterns
4. **Query builder UI**: Visual query builder with dropdowns
5. **Syntax highlighting**: Color-code query syntax in input field
6. **Auto-complete**: Suggest filters and patterns as user types
7. **Query history**: Remember recent queries per user
8. **Batch operations**: Support multiple queries with different parameters

### Code Improvements
1. **Caching**: Cache query results for repeated requests
2. **Pagination**: Support reading more than 10 files if needed
3. **Streaming**: Stream file content for large files
4. **Validation**: Pre-validate queries before execution
5. **Metrics**: Track query performance and usage patterns

## Documentation Files Location

All documentation and examples are in `gateway/agents/`:

```
gateway/agents/
├── TARGET_PATHS_EXAMPLES.md      # Comprehensive guide
├── QUICK_REFERENCE.md            # Concise cheat sheet
├── target_paths_examples.json    # Structured data for UI
├── target_paths_popup.html       # Ready-to-use UI component
├── AZURE_DEVOPS_USAGE.md        # Azure DevOps usage patterns
└── file_explanation_agent.py     # Implementation
```

## Summary

✅ **Complete backend implementation** with query pattern support
✅ **Explicit azdo: prefix logic** (no fallback)
✅ **Mixed local/Azure DevOps sources** supported
✅ **Comprehensive documentation** for developers and users
✅ **Ready-to-use UI component** for HiChat webclient
✅ **Detailed error handling** and logging
✅ **JSON data format** for programmatic access

**Next Steps:**
1. Integrate popup HTML into HiChat webclient
2. Test all query patterns end-to-end
3. Deploy and validate with real Azure DevOps repositories
4. Collect user feedback for UX improvements
