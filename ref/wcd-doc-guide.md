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
