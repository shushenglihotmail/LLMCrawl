# Target Paths Quick Reference

## 📝 Basic Syntax

| Type | Format | Example |
|------|--------|---------|
| **Local File** | `path/to/file` | `src/service.py` |
| **Azure DevOps File** | `azdo:path/to/file` | `azdo:src/service.cpp` |
| **Azure DevOps Query** | `azdo:pattern filters` | `azdo:keyword ext:cpp` |

## 🔍 Query Patterns

```
azdo:keyword file:*.json              # File pattern
azdo:keyword ext:cpp                  # Extension only
azdo:path:/src keyword                # Path filter
azdo:branch:main; keyword ext:h       # Full syntax
```

## 💡 Common Examples

### Single Files
```
src/models/user.py
azdo:MergedComponents/package.json
```

### Multiple Files (one per line)
```
tests/test.py
azdo:src/main.cpp
azdo:src/main.h
```

### Query Examples
```
azdo:Microsoft-NanoServer-PowerShell AND file:*.json
azdo:compute ext:cpp
azdo:branch:official/rs_sparc_ctr; path:/MergedComponents; keyword
```

### Mixed Local + Azure DevOps
```
tests/local_test.py
azdo:src/remote_service.cpp
docs/notes.md
azdo:network ext:h
```

## ⚙️ Query Filters

| Filter | Syntax | Example |
|--------|--------|---------|
| File pattern | `file:*.ext` | `file:*.json` |
| Extension | `ext:type` | `ext:cpp` |
| Path | `path:/folder` | `path:/src` |
| Branch | `branch:name` | `branch:main` |
| Operators | `AND`, `OR` | `compute AND network` |

## 📌 Tips

✅ Always use `azdo:` prefix for Azure DevOps
✅ One path per line for multiple files
✅ Queries return up to 10 matching files
✅ Mix local and Azure DevOps freely

❌ Don't use `azdo:` for local files
❌ Don't forget `:` after filter keywords
❌ Don't use file extensions with dot in `ext:` (use `ext:cpp` not `ext:.cpp`)

## 🆘 Troubleshooting

**"Could not read any target files"**
→ Missing `azdo:` prefix or incorrect path

**"No files found for query"**
→ Query too specific, try broader keywords

**"Azure DevOps MCP URL not configured"**
→ Check environment variable `AZURE_DEVOPS_MCP_URL`
