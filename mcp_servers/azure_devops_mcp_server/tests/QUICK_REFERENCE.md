# Quick Reference - Azure DevOps File Search

## Command-Line Tool (test_search.py)

### Basic Usage

```bash
# Set PAT token first
export AZURE_DEVOPS_PAT=your_pat_token

# Search files
python test_search.py --filter "FILTER_STRING"
python test_search.py --path PATH --filter "FILTER_STRING"

# Get file content
python test_search.py --get-file "FILE_PATH"
```

### Common Commands

| Task | Command |
|------|---------|
| List root files | `python test_search.py --filter "ext:txt"` |
| Search by extension | `python test_search.py --filter "ext:json"` |
| Search in path | `python test_search.py --path /src --filter "ext:cpp"` |
| Get file content | `python test_search.py --get-file ".gitignore"` |
| Limit output lines | `python test_search.py --get-file "README.md" --max-lines 50` |
| Recursive search | `python test_search.py --filter "ext:yml" --recursive` |
| Verbose output | `python test_search.py --filter "ext:json" -v` |

### Filter Syntax

| Filter Type | Syntax | Example |
|-------------|--------|---------|
| Extension | `ext:EXT` | `ext:json`, `ext:yml`, `ext:cpp` |
| File pattern | `file:PATTERN` | `file:*.cpp`, `file:azure-*`, `file:*test*` |
| Path pattern | `path:PATH` | `path:/src/`, `path:**/test/**` |
| Keyword | `WORD` | `Azure`, `"connection timeout"` |

### Combining Filters

```bash
# Multiple filters (AND logic)
python test_search.py --filter "Azure ext:json"
python test_search.py --filter "file:*service* ext:cs"
python test_search.py --path /src --filter "ext:cpp"
```

## MCP Tools (JSON API)

### search_azure_devops_files

```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "path_pattern": "src/",           // Optional: path filter
    "file_pattern": "*test*",         // Optional: filename filter
    "extension": "cpp",               // Optional: file extension
    "keyword": "Azure",               // Optional: content search
    "recursive": false,               // Optional: deep search (default: false)
    "max_results": 50                 // Optional: limit results
  }
}
```

### get_azure_devops_file

```json
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": ".gitignore",        // Required: path to file
    "branch": "main"                  // Optional: branch name
  }
}
```

## Quick Examples

### Search Examples

```bash
# Root YAML files (fast, non-recursive)
python test_search.py --filter "ext:yml"

# JSON files in src/MergedComponents
python test_search.py --path /src/MergedComponents --filter "ext:json"

# All C++ test files anywhere (recursive)
python test_search.py --filter "file:*test* ext:cpp" --recursive

# Files starting with "azure-"
python test_search.py --filter "file:azure-*" --recursive

# Files in any test directory (deep search)
python test_search.py --path "**/test/**" --filter "ext:cpp" --recursive
```

### File Content Examples

```bash
# View .gitignore
python test_search.py --get-file ".gitignore"

# View first 20 lines
python test_search.py --get-file "README.md" --max-lines 20

# File from specific path
python test_search.py --get-file "src/main.cpp"

# File from different branch
python test_search.py --get-file "README.md" --branch main
```

## Important Notes

⚠️ **Safety**: Searches are non-recursive by default (root level only)
- Add `--recursive` flag for deep searches
- Recursive searches are slower on large repos

⚠️ **Performance**:
- Non-recursive: Fast (seconds)
- Recursive: Slower (depends on repo size)
- Keyword search: Very slow (searches file contents)

⚠️ **Glob Patterns**:
- `**` = any depth (requires `--recursive`)
- `*` = any characters
- `?` = single character

## Options Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--filter "FILTER"` | Filter string with patterns | - |
| `--path PATH` | Path pattern to search in | Root |
| `--get-file FILE` | Get content of specific file | - |
| `--recursive` | Search subdirectories | false |
| `--max-results N` | Limit number of results | 50 |
| `--max-lines N` | Limit file content lines | All |
| `--branch NAME` | Branch to search | official/rs_sparc_ctr_exp |
| `--verbose`, `-v` | Show detailed info | false |
| `--organization ORG` | Azure DevOps org | microsoft |
| `--project PROJ` | Project name | OS |
| `--repository REPO` | Repository name | os.2020 |

## Environment Variables

```bash
# Required
export AZURE_DEVOPS_PAT=your_pat_token

# Optional overrides
export AZURE_DEVOPS_ORG=microsoft
export AZURE_DEVOPS_PROJECT=OS
export AZURE_DEVOPS_REPO=os.2020
export AZURE_DEVOPS_BRANCH=official/rs_sparc_ctr_exp
```

## Help

```bash
python test_search.py --help
```
