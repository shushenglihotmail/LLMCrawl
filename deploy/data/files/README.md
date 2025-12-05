# Local Files Directory

This directory is the default mount point for the Local Access MCP server.

To change the mounted folder, edit `.env` and set:

```bash
MCP_HOST_FOLDER=/path/to/your/folder
```

For example:
- Windows: `MCP_HOST_FOLDER=C:/src`
- Linux/Mac: `MCP_HOST_FOLDER=/home/user/src`

After changing, restart services with:
```bash
llmcrawl deploy --restart mcp-server
```
