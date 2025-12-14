# Windows Composition Database (WCD) Tool

The Windows Composition Database (WCD) tool allows the LLM agent to query the internal Windows composition graph (the `$d` object) to answer questions about Editions, Packages, Assemblies, and Files.

## Architecture

Because the WCD requires access to internal network shares and a persistent PowerShell session on a Windows host, it cannot run directly inside the Linux-based Gateway container.

We use a **Bridge Architecture**:

1.  **WCD Bridge Service**: Runs natively on your Windows Host. It initializes the PowerShell session and exposes an HTTP endpoint.
2.  **Gateway Agent**: Runs in Docker. It sends queries to the Bridge Service via HTTP.

```mermaid
graph LR
    subgraph Docker Container
        Gateway[Gateway Agent]
    end

    subgraph Windows Host
        Bridge[WCD Bridge Service]
        PS[PowerShell Session ($d)]
        Share[Internal Network Share]
    end

    Gateway -- HTTP POST /query --> Bridge
    Bridge -- Stdio --> PS
    PS -- SMB --> Share
```

## Setup Guide

### 1. Host Prerequisites

On your **Windows Host machine** (not inside Docker), ensure you have Python installed.

Install the required dependencies:
```powershell
pip install fastapi uvicorn
```

### 2. Start the Bridge Service

There are multiple ways to start the WCD Bridge depending on your setup:

#### Option A: Using PowerShell Script (Development)

For development from the source repository:

**Network Share Mode:**
```powershell
cd c:\src\github\LLMCrawl
.\scripts\start_wcd_bridge.ps1 -WinCompShareCmd "\\winbuilds\release\rs_sparc_ctr_exp\29503.1000.251209-1700"
```

**WCDaaS Local Mode (Recommended):**

First, download the WCD tools by opening this URL in your browser:
```
https://wcdaas-pme.azurewebsites.net/default.aspx?action=wcd&branch=rs_sparc_ctr_exp&buildName=29503.1000.251209-1700&arch=amd64
```

Then start the bridge:
```powershell
cd c:\src\github\LLMCrawl
.\scripts\start_wcd_bridge.ps1 -UseWcdaasLocal -Branch rs_sparc_ctr_exp -BuildName 29503.1000.251209-1700
```

Script parameters:
- `-WinCompShareCmd` - Base path to Windows build release folder
- `-UseWcdaasLocal` - Use local WCDaaS download instead of network share
- `-Branch` - WCD branch name (default: rs_sparc_ctr_exp)
- `-BuildName` - Build name (required for WCDaaS local mode)
- `-Arch` - Architecture folder (default: amd64fre)

#### Option B: Using LLMCrawl CLI (Installed Package)

If you have LLMCrawl installed as a package:

**Network Share Mode:**
```powershell
llmcrawl wcd-bridge --build "\\winbuilds\release\rs_sparc_ctr_exp\29503.1000.251209-1700"
```

**WCDaaS Local Mode:**
```powershell
llmcrawl wcd-bridge --wcdaas-local --branch rs_sparc_ctr_exp --build-name 29503.1000.251209-1700
```

CLI options:
- `--build`, `-b` - Base path to Windows build release folder
- `--cmd`, `-c` - Full path to InteractViaPowerShell.cmd
- `--wcdaas-local` - Use local WCDaaS download
- `--branch` - WCD branch name (default: rs_sparc_ctr_exp)
- `--build-name` - Build name (required for --wcdaas-local)
- `--arch`, `-a` - Architecture folder (default: amd64fre)
- `--port`, `-p` - Port to run the bridge on (default: 8005)

This will:
- Set the appropriate environment variables
- Launch the bridge service
- The service listens on `0.0.0.0:8005`

### 3. Configure the Gateway

Update your `deploy/.env` file to point the Gateway to the Bridge Service.

If running Docker Desktop, use `host.docker.internal` to reach the host:

```dotenv
# deploy/.env

# URL of the Windows Composition Bridge service running on the host
WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005
```

Restart the Gateway service to apply changes:
```bash
docker-compose restart gateway
```

## Usage in HiChat

1.  Open the **HiChat** web client.
2.  Select **Code Analysis** or **Build System Analysis** workflow.
3.  In the "Expose" section, check the **Win Comp DB** box.
4.  Ask your question!

### Example Queries

The LLM can now generate PowerShell queries against the `$d` object. You can ask questions like:

*   "What are the desktop editions?"
*   "Which files are in the OneCoreUAP Edition?"
*   "How is the package 'Microsoft-Windows-HTTP-API' included in ServerCore?"
*   "Who owns the API 'GetNamedPipeHandleState'?"
*   "Find all editions containing 'mshtml.dll'."

### Manual Testing

You can verify the bridge is working by sending a curl request from the host:

```powershell
curl -X POST http://localhost:8005/query `
     -H "Content-Type: application/json" `
     -d '{"query": "$d.Editions[''Professional''].Name"}'
```

## Troubleshooting

**"Windows Composition Bridge not configured"**
- Ensure `WIN_COMP_BRIDGE_URL` is set in `deploy/.env`.

**"Error connecting to bridge"**
- Ensure the Bridge Service is running on the host (check the detached window).
- Ensure the Gateway container can reach the host (try `ping host.docker.internal` inside the container).

**"PowerShell session died"**
- The Bridge Service attempts to restart the session automatically.
- Check the console output of the Bridge Service window for errors related to the `InteractViaPowerShell.cmd` script.
