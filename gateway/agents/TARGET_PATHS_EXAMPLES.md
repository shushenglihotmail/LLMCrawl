# Template Agent - Target Paths Examples

## Overview

The **Target Paths** field supports multiple file sources:
- **Local files** - Regular paths without prefix
- **Azure DevOps files** - Paths with `azdo:` prefix
- **Azure DevOps queries** - Search patterns with `azdo:` prefix

You can mix local and Azure DevOps files in the same request!

## Local File Examples

### Single Local File
```
src/service.py
```

### Multiple Local Files
```
src/service.py
src/utils/helpers.py
tests/test_service.py
```

### Local Folder
```
src/models/
```

## Azure DevOps File Examples

### Single Azure DevOps File
```
azdo:MergedComponents/pkggen/Microsoft-NanoServer-PowerShell.json
```

### Multiple Azure DevOps Files
```
azdo:src/onecore/vm/compute/dll/ComputeServiceModule.cpp
azdo:src/onecore/vm/compute/dll/ComputeService.h
azdo:docs/ARCHITECTURE.md
```

### Azure DevOps Folder
```
azdo:MergedComponents/pkggen/
```

## Azure DevOps Query Examples

### Search by Keyword and File Pattern
```
azdo:Microsoft-NanoServer-PowerShell AND file:*.json
```
Finds all JSON files containing "Microsoft-NanoServer-PowerShell" in their name or path.

### Search by Extension
```
azdo:Microsoft-NanoServer-PowerShell ext:man
```
Finds all `.man` files with "Microsoft-NanoServer-PowerShell" in their content.

```
azdo:Azure ext:yml
```
Finds all YAML files containing "Azure".

### Search with Path Filter
```
azdo:path:/MergedComponents Microsoft-NanoServer-PowerShell
```
Search only within `/MergedComponents` folder.

### Advanced Query with Branch
```
azdo:branch:official/rs_sparc_ctr; path:/MergedComponents; Microsoft-NanoServer-PowerShell AND file:*.json
```
- Branch: `official/rs_sparc_ctr`
- Path: `/MergedComponents`
- Keyword: "Microsoft-NanoServer-PowerShell"
- File pattern: `*.json`

### Multiple Patterns
```
azdo:compute ext:cpp
azdo:network ext:h
azdo:pipeline file:*.yml
```
Searches multiple patterns and reads all matching files.

## Mixed Local + Azure DevOps Examples

### Local Tests + Azure DevOps Code
```
tests/test_service.py
azdo:src/services/NetworkService.cpp
azdo:src/services/NetworkService.h
```

### Azure DevOps Query + Local Reference
```
azdo:Microsoft-NanoServer-PowerShell ext:json
docs/local-notes.md
examples/sample-config.json
```

## Query Syntax Reference

### Inline Format (space-separated)
```
azdo:keyword file:pattern ext:extension
```

### Semicolon Format (explicit parameters)
```
azdo:branch:name; path:folder; keyword file:pattern
```

### Supported Parameters

| Parameter | Inline | Semicolon | Example |
|-----------|--------|-----------|---------|
| **File pattern** | `file:*.cpp` | `file:*.cpp` | Match filenames |
| **Extension** | `ext:json` | `ext:json` | File extension (without dot) |
| **Path filter** | `path:/src` | `path:/src` | Search within folder |
| **Branch** | ❌ | `branch:main` | Use specific branch |
| **Keyword** | `text` | `text` | Search in file content |

### Operators

- **AND** - All conditions must match (default)
- **OR** - Any condition can match

Example:
```
azdo:compute AND (network OR socket) ext:cpp
```

## Complete Workflow Examples

### 1. Understand Workflow - Mixed Sources

**Target Paths:**
```
azdo:MergedComponents/pkggen/Microsoft-NanoServer-PowerShell.json
local/config/override.json
docs/SETUP.md
```

**Request:**
```
Explain how the PowerShell package is configured and how local overrides work
```

### 2. Inspect Workflow - Azure DevOps Query

**Target Paths:**
```
azdo:security ext:cpp
azdo:authentication file:*Service.cpp
```

**Request:**
```
Check for security vulnerabilities and authentication issues
```

### 3. Generate Workflow - Reference Examples

**Target Paths:**
```
(leave empty)
```

**Reference Files:**
```
azdo:src/services/HttpService.cpp
azdo:src/services/NetworkBase.h
examples/local-service-template.cpp
```

**Request:**
```
Generate a new FileService class following the existing patterns
```

## Tips

1. **Always use `azdo:` prefix** for Azure DevOps files/queries
2. **One path per line** in multi-line input
3. **Queries match up to 10 files** to avoid token limits
4. **Use specific patterns** for better results (e.g., `ext:cpp` instead of broad keyword)
5. **Test queries separately** before combining with local files

## Error Handling

### "Could not read any target files"
- Check `azdo:` prefix is present for Azure DevOps files
- Verify file paths are correct
- Ensure Azure DevOps MCP server is configured

### "No files found for query"
- Query too specific - try broader keywords
- Check path exists in repository
- Verify branch is correct (default: main)

### "Azure DevOps MCP URL not configured"
- Set `AZURE_DEVOPS_MCP_URL` environment variable
- Verify Azure DevOps MCP server is running
- Check PAT token is valid

## Integration with HiChat WebClient

### Example Label Format (Short)
```
Example: azdo:path ext:cpp
```

### Help Icon with Popup Examples
Add a "?" or "ℹ️" icon next to Target Paths label that shows:
- 3-5 quick examples
- Link to full documentation
- Query syntax quick reference

### Popup Content (Suggested)
```html
<div class="examples-popup">
  <h3>Target Paths Examples</h3>

  <h4>Local File:</h4>
  <code>src/service.py</code>

  <h4>Azure DevOps File:</h4>
  <code>azdo:MergedComponents/file.json</code>

  <h4>Azure DevOps Query:</h4>
  <code>azdo:keyword ext:cpp</code>
  <code>azdo:path:/src; keyword file:*.h</code>

  <h4>Mixed:</h4>
  <code>tests/local.py
azdo:src/remote.cpp</code>

  <a href="#" onclick="showFullDocs()">View Full Documentation</a>
</div>
```

### Textarea Placeholder
```html
<textarea placeholder="Enter file paths (one per line)
Examples:
  src/local.py
  azdo:path file:*.json
  azdo:branch:main; keyword ext:cpp">
</textarea>
```
