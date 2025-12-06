# Windows Composition Database Documentation Guide

## Repository Location

Windows Composition Database (WCD) documentation lives in an Azure DevOps repository with the following settings:

- **Project**: `OneCore`
- **Repository**: `WindowsCompositionData`
- **Branch**: `main`
- **Path**: `/WindowsCompositionData.Docs`

All documents are Markdown files.

- To list all documentation files, search for: `file:*.md` under `/WindowsCompositionData.Docs`.
- **Important**: Links inside these Markdown files are intended for web rendering only. They may not be valid in the raw repo view. **Ignore them and do not attempt to follow them.**

## Folder Structure

- `/WindowsCompositionData.Docs/Concepts`  – Conceptual explanations of WCD and its data model.
- `/WindowsCompositionData.Docs/Generated` – Generated object model definitions and reference material.
- `/WindowsCompositionData.Docs/Samples`   – Sample code (C#, PowerShell, etc.) demonstrating how to query and use WCD.

## Key Entry Points

- `/WindowsCompositionData.Docs/index.md` – Main landing page and high-level overview of WCD.
- `/WindowsCompositionData.Docs/Generated/ObjectModel.md` – Overview of the WCD object model and its core types.

## WCD Query Best Practices

The WCD database contains extensive information. Queries can easily exceed token limits or time out if not properly constrained. Follow these rules when constructing WCD queries:

### Rule 1: Never Query Unbounded Collections

**WRONG** - Returns thousands of items, will exceed token limits:
```powershell
$d.Editions['FOD_Pseudo'].ContainedPackagesDeep
$d.Components
$d.Packages
```

**CORRECT** - Always apply filters or select specific items:
```powershell
# Filter by name pattern
$d.Editions['FOD_Pseudo'].ContainedPackagesDeep |
    Where-Object { $_.Name -like 'Microsoft-Windows-Media*' }

# Select only needed properties
$d.Editions['FOD_Pseudo'].ContainedPackagesDeep |
    Where-Object { $_.Name -like 'Shell*' } |
    Select-Object Name, FodCapability
```

### Rule 2: Use Pagination for Large Result Sets

When you must retrieve many items, split into multiple queries:

```powershell
# Query A-M
$d.Packages | Where-Object { $_.Name[0] -ge 'A' -and $_.Name[0] -le 'M' }

# Query N-Z
$d.Packages | Where-Object { $_.Name[0] -ge 'N' -and $_.Name[0] -le 'Z' }
```

### Rule 3: Query Specific Entities by Name

Instead of browsing collections, query known entity names directly:

```powershell
# Direct lookup - fast and bounded
$d.Components['Microsoft-Windows-Shell-Setup']
$d.Packages['Microsoft-Windows-MediaPlayer-Package']
```

### Rule 4: Limit Output Properties

Use `Select-Object` to return only the properties you need:

```powershell
# Instead of returning full objects
$d.Components['Microsoft-Windows-Shell-Setup'] |
    Select-Object Name, Version, ContainedFeatures
```

### Rule 5: Use Count Before Fetching

Check result size before fetching large collections:

```powershell
# Check count first
($d.Editions['FOD_Pseudo'].ContainedPackagesDeep | Measure-Object).Count

# If count is large (>100), apply filters before fetching
``` try to use multiple queries that each query returns partial results instead of one big query.
