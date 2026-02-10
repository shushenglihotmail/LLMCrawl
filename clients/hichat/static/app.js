// HiChat Web Client - Application JavaScript (Python Version)
// Service mode only - connects to LLMCrawl gateway

// Initialize Mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: 'default',
    securityLevel: 'loose',
    flowchart: {
        useMaxWidth: true,
        htmlLabels: true
    }
});

// Token refresh state
let isRefreshingToken = false;
let refreshPromise = null;

// Enhanced fetch with automatic token refresh on 401
async function fetchWithAuth(url, options = {}) {
    let response = await fetch(url, options);

    // If 401 and auth is enabled, try to refresh token
    if (response.status === 401 && currentConfig && currentConfig.authEnabled) {
        console.log('Received 401, attempting token refresh...');

        // If already refreshing, wait for that operation
        if (isRefreshingToken) {
            await refreshPromise;
            // Retry original request after refresh completes
            response = await fetch(url, options);
            return response;
        }

        // Start token refresh
        isRefreshingToken = true;
        refreshPromise = refreshToken();

        try {
            const refreshResult = await refreshPromise;

            if (refreshResult.success) {
                console.log('Token refreshed successfully, retrying request...');
                // Retry original request with new token
                response = await fetch(url, options);
            } else if (refreshResult.requiresLogin) {
                // Silent refresh failed, need interactive login
                console.warn('Token expired, prompting user to re-authenticate...');
                showAuthenticationPrompt();
                throw new Error('Authentication required. Please sign in again.');
            } else {
                throw new Error(refreshResult.error || 'Token refresh failed');
            }
        } finally {
            isRefreshingToken = false;
            refreshPromise = null;
        }
    }

    return response;
}

// Refresh access token
async function refreshToken() {
    try {
        const response = await fetch('/api/auth/refresh', {
            method: 'POST'
        });
        return await response.json();
    } catch (error) {
        console.error('Token refresh error:', error);
        return { success: false, error: error.message };
    }
}

// Show authentication prompt to user
function showAuthenticationPrompt() {
    const chatMessages = document.getElementById('chatMessages');
    const authPrompt = document.createElement('div');
    authPrompt.className = 'auth-prompt-message';
    authPrompt.innerHTML = `
        <div class="auth-prompt-content">
            <div class="auth-icon">🔐</div>
            <h3>Authentication Required</h3>
            <p>Your session has expired. Please sign in again to continue.</p>
            <button onclick="window.location.href='/api/auth/login'" class="auth-button">Sign In</button>
        </div>
    `;
    chatMessages.appendChild(authPrompt);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Render Mermaid diagrams in markdown content
let mermaidCounter = 0;
async function renderMermaidDiagrams(container) {
    // Find all code blocks with language 'mermaid'
    const codeBlocks = container.querySelectorAll('pre code.language-mermaid');

    for (const codeBlock of codeBlocks) {
        const pre = codeBlock.parentElement;
        const mermaidCode = codeBlock.textContent;

        // Create a container for the rendered diagram
        const diagramDiv = document.createElement('div');
        diagramDiv.className = 'mermaid-diagram';
        const diagramId = 'mermaid-' + (++mermaidCounter);

        try {
            // Render the mermaid diagram
            const { svg } = await mermaid.render(diagramId, mermaidCode);
            diagramDiv.innerHTML = svg;

            // Replace the code block with the rendered diagram
            pre.parentNode.replaceChild(diagramDiv, pre);
        } catch (error) {
            console.error('Mermaid rendering error:', error);
            // Keep the original code block on error
            diagramDiv.innerHTML = '<div class="mermaid-error">⚠️ Diagram rendering failed: ' + error.message + '</div>';
            diagramDiv.appendChild(pre.cloneNode(true));
            pre.parentNode.replaceChild(diagramDiv, pre);
        }
    }
}

// Path validation functions
function validateAzdoUri(uri) {
    if (!uri.startsWith('azdo:')) {
        return { valid: false, error: 'Azure DevOps URI must start with "azdo:"' };
    }

    const rest = uri.substring(5);

    if (!rest.startsWith('/')) {
        return { valid: false, error: 'Path must start with "/" after "azdo:"' };
    }

    const hasSearchText = rest.includes(':');
    if (!hasSearchText) {
        return { valid: false, error: 'Azure DevOps URI must include searchText after colon (e.g., azdo:/path:ext:xml)' };
    }

    const beforeQuery = rest.split('?')[0];
    const searchTextPart = beforeQuery.substring(beforeQuery.lastIndexOf(':') + 1);
    if (!searchTextPart || searchTextPart.trim() === '') {
        return { valid: false, error: 'Search text cannot be empty after colon' };
    }

    return { valid: true };
}

function validateLocalPath(path) {
    if (!path.startsWith('/')) {
        return { valid: false, error: 'Local path must start with "/"' };
    }

    const invalidChars = /[<>"|?]/;
    if (invalidChars.test(path)) {
        return { valid: false, error: 'Path contains invalid characters: < > " |' };
    }

    if (path === '/') {
        return { valid: false, error: 'Path cannot be just "/" - specify a file or folder' };
    }

    return { valid: true };
}

function validateTargetPath(path) {
    path = path.trim();
    if (!path) return { valid: true };

    if (path.startsWith('azdo:')) {
        return validateAzdoUri(path);
    }

    if (path.startsWith('/')) {
        return validateLocalPath(path);
    }

    return {
        valid: false,
        error: 'Path must be a local path starting with "/" or Azure DevOps URI starting with "azdo:"'
    };
}

function validateReferencePath(path) {
    path = path.trim();
    if (!path) return { valid: true };

    if (path.startsWith('azdo:')) {
        return validateAzdoUri(path);
    }

    if (path.startsWith('/')) {
        return validateLocalPath(path);
    }

    return {
        valid: false,
        error: 'Reference path must be a local path starting with "/" or Azure DevOps URI starting with "azdo:"'
    };
}

function validateAllPaths() {
    const errors = [];

    const targetPathsText = document.getElementById('targetPaths').value.trim();
    if (targetPathsText) {
        const targetPaths = targetPathsText.split('\n').map(p => p.trim()).filter(p => p);
        targetPaths.forEach((path, index) => {
            const result = validateTargetPath(path);
            if (!result.valid) {
                errors.push(`Target Path line ${index + 1}: ${result.error}\n  → "${path}"`);
            }
        });
    }

    const referenceFilesText = document.getElementById('referenceFiles').value.trim();
    if (referenceFilesText) {
        const referenceFiles = referenceFilesText.split('\n').map(p => p.trim()).filter(p => p);
        referenceFiles.forEach((path, index) => {
            const result = validateReferencePath(path);
            if (!result.valid) {
                errors.push(`Reference File line ${index + 1}: ${result.error}\n  → "${path}"`);
            }
        });
    }

    return errors;
}

function showValidationError(errors) {
    const errorMessage = '⚠️ Invalid Path Format\n\n' + errors.join('\n\n') +
        '\n\n📖 Valid formats:\n' +
        '• Target Paths: azdo:/path:searchText\n' +
        '• Reference Files: /local/path or azdo:/path:searchText';
    alert(errorMessage);
}

// Dynamic tooltip positioning
document.addEventListener('DOMContentLoaded', function () {
    const seedUrlsInput = document.getElementById('seedUrlsInput');
    if (seedUrlsInput) {
        seedUrlsInput.addEventListener('input', updateDownloadButtonState);
    }

    const helpIcons = document.querySelectorAll('.help-icon');

    helpIcons.forEach(icon => {
        icon.addEventListener('mouseenter', function (e) {
            const tooltip = this.querySelector('.help-tooltip');
            if (!tooltip) return;

            const iconRect = this.getBoundingClientRect();
            const tooltipRect = tooltip.getBoundingClientRect();
            const viewportHeight = window.innerHeight;

            const spaceAbove = iconRect.top;
            const spaceBelow = viewportHeight - iconRect.bottom;

            if (spaceBelow > tooltipRect.height + 10 || spaceBelow > spaceAbove) {
                tooltip.style.top = (iconRect.bottom + 8) + 'px';
            } else {
                tooltip.style.top = (iconRect.top - tooltipRect.height - 8) + 'px';
            }

            tooltip.style.left = (iconRect.left + iconRect.width / 2) + 'px';
            tooltip.style.transform = 'translateX(-50%)';
        });
    });
});

let conversationId = '';
let currentConfig = {};
let messageHistory = [];
let historyIndex = -1;
let unsavedInput = '';
let clearHistoryFlag = false;
let currentWorkflow = 'general_chat';
let currentAbortController = null;
let isRequestInProgress = false;

// Workflow UI configuration
const WORKFLOW_UI_CONFIG = {
    general_chat: {
        targetFilesEnabled: false,
        referenceFilesEnabled: false,
        azureDevOpsExposable: false,
        localMcpExposable: true,
        crawlerExposable: true,
        windowsCompositionExposable: false,
        seedUrlsEnabled: true
    },
    code_analysis: {
        targetFilesEnabled: true,
        referenceFilesEnabled: true,
        azureDevOpsExposable: true,
        localMcpExposable: true,
        crawlerExposable: true,
        windowsCompositionExposable: true,
        seedUrlsEnabled: true
    },
    build_system_analysis: {
        targetFilesEnabled: true,
        referenceFilesEnabled: true,
        azureDevOpsExposable: true,
        localMcpExposable: true,
        crawlerExposable: true,
        windowsCompositionExposable: true,
        seedUrlsEnabled: true
    },
    file_explorer: {
        targetFilesEnabled: true,
        referenceFilesEnabled: true,
        azureDevOpsExposable: true,
        localMcpExposable: true,
        crawlerExposable: true,
        windowsCompositionExposable: false,
        seedUrlsEnabled: true
    }
};

// Apply workflow UI restrictions
function applyWorkflowRestrictions(workflow) {
    const config = WORKFLOW_UI_CONFIG[workflow] || WORKFLOW_UI_CONFIG.general_chat;

    // Target Paths
    const targetPathsTextarea = document.getElementById('targetPaths');
    const targetPathsLabel = targetPathsTextarea.closest('.form-group').querySelector('label');
    targetPathsTextarea.disabled = !config.targetFilesEnabled;
    targetPathsTextarea.style.opacity = config.targetFilesEnabled ? '1' : '0.5';
    if (!config.targetFilesEnabled) {
        targetPathsTextarea.value = '';
        targetPathsLabel.style.opacity = '0.5';
    } else {
        targetPathsLabel.style.opacity = '1';
    }

    // Reference Files
    const referenceFilesTextarea = document.getElementById('referenceFiles');
    const referenceFilesLabel = referenceFilesTextarea.closest('.form-group').querySelector('label');
    referenceFilesTextarea.disabled = !config.referenceFilesEnabled;
    referenceFilesTextarea.style.opacity = config.referenceFilesEnabled ? '1' : '0.5';
    if (!config.referenceFilesEnabled) {
        referenceFilesTextarea.value = '';
        referenceFilesLabel.style.opacity = '0.5';
    } else {
        referenceFilesLabel.style.opacity = '1';
    }

    // Azure DevOps MCP checkbox
    const azureMcpCheckbox = document.getElementById('exposeAzureMcp');
    const azureMcpLabel = azureMcpCheckbox.closest('.switch-item');
    azureMcpCheckbox.disabled = !config.azureDevOpsExposable;
    azureMcpLabel.style.opacity = config.azureDevOpsExposable ? '1' : '0.5';
    if (!config.azureDevOpsExposable) {
        azureMcpCheckbox.checked = false;
    }

    // Windows Composition checkbox
    const winCompCheckbox = document.getElementById('exposeWindowsComposition');
    const winCompLabel = winCompCheckbox.closest('.switch-item');
    winCompCheckbox.disabled = !config.windowsCompositionExposable;
    winCompLabel.style.opacity = config.windowsCompositionExposable ? '1' : '0.5';
    if (!config.windowsCompositionExposable) {
        winCompCheckbox.checked = false;
    }

    console.log('Applied workflow restrictions for:', workflow, config);
}

// Workflow selector change handler
document.getElementById('workflowSelector').addEventListener('change', function () {
    currentWorkflow = this.value;
    applyWorkflowRestrictions(currentWorkflow);
    console.log('Workflow changed to:', currentWorkflow);
});

// Panel collapse/expand functionality
function togglePanel() {
    const panel = document.getElementById('unifiedPanel');
    const btn = document.getElementById('collapseBtn');
    panel.classList.toggle('collapsed');
    btn.textContent = panel.classList.contains('collapsed') ? '▶' : '▼';
}

// Message history navigation
document.addEventListener('DOMContentLoaded', function () {
    const messageInput = document.getElementById('messageInput');

    messageInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitRequest();
            return;
        }

        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (messageHistory.length === 0) return;

            if (historyIndex === -1) {
                unsavedInput = messageInput.value;
                historyIndex = messageHistory.length - 1;
            } else if (historyIndex > 0) {
                historyIndex--;
            }

            if (historyIndex >= 0) {
                messageInput.value = messageHistory[historyIndex];
            }
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (messageHistory.length === 0) return;

            if (historyIndex < messageHistory.length - 1 && historyIndex >= 0) {
                historyIndex++;
                messageInput.value = messageHistory[historyIndex];
            } else if (historyIndex >= 0) {
                historyIndex = -1;
                messageInput.value = unsavedInput;
                unsavedInput = '';
            }
        }
    });
});

// Load initial configuration and models
async function loadConfig() {
    try {
        const response = await fetchWithAuth('/api/config');
        currentConfig = await response.json();
        await loadModels();
        applyWorkflowRestrictions(currentWorkflow);
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

// Load available models from gateway
async function loadModels() {
    try {
        const response = await fetchWithAuth('/api/models');
        if (!response.ok) {
            throw new Error('Failed to fetch models');
        }
        const data = await response.json();
        const modelsData = data.models;

        const modelSelector = document.getElementById('modelSelector');
        modelSelector.innerHTML = '';

        modelsData.forEach(model => {
            const option = document.createElement('option');
            option.value = model.name;
            option.textContent = model.display_name || model.name;
            modelSelector.appendChild(option);
        });

        if (modelsData.length > 0) {
            modelSelector.value = modelsData[0].name;
        }
    } catch (error) {
        console.error('Failed to load models:', error);
        const modelSelector = document.getElementById('modelSelector');
        modelSelector.innerHTML = '<option>Failed to load models</option>';
    }
}

// Submit request to gateway via Python backend
async function submitRequest() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();

    if (!message) {
        alert('Please enter a message.');
        return;
    }

    const validationErrors = validateAllPaths();
    if (validationErrors.length > 0) {
        showValidationError(validationErrors);
        return;
    }

    messageHistory.push(message);
    historyIndex = -1;

    const sendBtn = document.getElementById('sendBtn');
    const loading = document.getElementById('loading');
    const downloadBtn = document.getElementById('downloadBtn');
    const clearBtn = document.getElementById('clearBtn');

    sendBtn.disabled = true;
    messageInput.disabled = true;
    downloadBtn.disabled = true;
    loading.classList.add('active');

    // Toggle Clear Chat button to Stop button
    isRequestInProgress = true;
    clearBtn.textContent = 'Stop';
    clearBtn.classList.add('stop-mode');

    // Create AbortController for this request
    currentAbortController = new AbortController();    // Collapse the panel after sending
    const panel = document.getElementById('unifiedPanel');
    const btn = document.getElementById('collapseBtn');
    if (!panel.classList.contains('collapsed')) {
        panel.classList.add('collapsed');
        btn.textContent = '▶';
    }

    addMessage('user', message);
    messageInput.value = '';

    if (!conversationId) {
        conversationId = generateUUID();
        console.log('New conversation:', conversationId);
    }

    const targetPaths = document.getElementById('targetPaths').value.trim()
        ? document.getElementById('targetPaths').value.split('\n').map(p => p.trim()).filter(p => p)
        : null;

    const referenceFiles = document.getElementById('referenceFiles').value.trim()
        ? document.getElementById('referenceFiles').value.split('\n').map(p => p.trim()).filter(p => p)
        : null;

    const seedUrls = document.getElementById('seedUrlsInput').value.trim()
        ? document.getElementById('seedUrlsInput').value.split(',').map(url => url.trim()).filter(url => url)
        : null;

    const enableEmbedding = document.getElementById('enableEmbedding').checked;
    const crawlDepth = parseInt(document.getElementById('crawlDepth').value) || 1;

    const exposeToLlm = {
        local_mcp: document.getElementById('exposeLocalMcp').checked,
        azure_devops_mcp: document.getElementById('exposeAzureMcp').checked,
        crawler: document.getElementById('exposeCrawler').checked,
        windows_composition: document.getElementById('exposeWindowsComposition').checked
    };

    try {
        const requestBody = {
            workflow: currentWorkflow,
            user_message: message,
            model: document.getElementById('modelSelector').value,
            conversation_id: conversationId,
            target_paths: targetPaths,
            reference_files: referenceFiles,
            seed_urls: seedUrls,
            enable_embedding: enableEmbedding,
            crawl_depth: crawlDepth,
            expose_to_llm: exposeToLlm,
            clear_history: clearHistoryFlag
        };

        clearHistoryFlag = false;

        console.log('Sending request:', JSON.stringify(requestBody, null, 2));

        const response = await fetchWithAuth('/api/agent/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
            signal: currentAbortController.signal
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Failed to send message');
        }

        const data = await response.json();

        if (data.conversation_id) {
            conversationId = data.conversation_id;
        }

        let contextInfo = '';
        if (data.context_gathered) {
            const ctx = data.context_gathered;
            const parts = [];
            if (ctx.target_files > 0) parts.push(ctx.target_files + ' target files');
            if (ctx.reference_files > 0) parts.push(ctx.reference_files + ' reference files');
            if (ctx.crawled_urls > 0) parts.push(ctx.crawled_urls + ' crawled URLs');
            if (ctx.web_search_results > 0) parts.push(ctx.web_search_results + ' web results');

            if (parts.length > 0) {
                contextInfo = '\n\n*Context gathered: ' + parts.join(', ') + '*';
            }
        }

        addMessage('assistant', data.response + contextInfo, {
            model: data.model,
            tokens: data.tokens_used
        });

    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request was stopped by user');
            addMessage('assistant', '*Request stopped by user.*', null, false);
        } else {
            console.error('Request error:', error);
            addMessage('assistant', 'Error: ' + error.message, null, true);
        }
    } finally {
        // Reset UI state
        sendBtn.disabled = false;
        messageInput.disabled = false;
        loading.classList.remove('active');
        updateDownloadButtonState();
        messageInput.focus();

        // Reset Stop button back to Clear Chat
        isRequestInProgress = false;
        currentAbortController = null;
        clearBtn.textContent = 'Clear Chat';
        clearBtn.classList.remove('stop-mode');
    }
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function addMessage(role, content, meta = null, isError = false) {
    const chatArea = document.getElementById('chatArea');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ' + role;

    let metaHTML = '';
    if (meta) {
        metaHTML = '<div class="message-meta">Model: ' + meta.model + ' | Tokens: ' + meta.tokens + '</div>';
    }

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (role === 'assistant' && !isError) {
        const markdownDiv = document.createElement('div');
        markdownDiv.className = 'markdown-content';
        markdownDiv.innerHTML = marked.parse(content);
        contentDiv.appendChild(markdownDiv);

        setTimeout(() => renderMermaidDiagrams(markdownDiv), 0);
    } else {
        contentDiv.textContent = content;
    }

    messageDiv.appendChild(contentDiv);
    if (metaHTML) {
        messageDiv.innerHTML += metaHTML;
    }

    chatArea.appendChild(messageDiv);
    chatArea.scrollTop = chatArea.scrollHeight;
}

async function exportToMarkdown() {
    const downloadBtn = document.getElementById('downloadBtn');
    const seedUrlsInput = document.getElementById('seedUrlsInput').value.trim();
    const crawlDepthInput = document.getElementById('crawlDepth');

    if (!seedUrlsInput) {
        alert('Please provide at least one Seed URL to download content from.');
        return;
    }

    const seedUrls = seedUrlsInput.split(',').map(url => url.trim()).filter(url => url);
    if (seedUrls.length === 0) {
        alert('Please provide valid Seed URLs.');
        return;
    }

    const depth = parseInt(crawlDepthInput.value) || 1;

    try {
        downloadBtn.disabled = true;
        downloadBtn.textContent = 'Downloading...';

        const requestBody = {
            seed_urls: seedUrls,
            depth: depth,
            freshness_days: 365
        };

        const response = await fetchWithAuth(currentConfig.serviceUrl + '/api/v1/export/markdown', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Download failed');
        }

        const result = await response.json();

        const downloadUrl = currentConfig.serviceUrl + result.download_url;
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = result.download_url.split('/').pop();
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        addMessage('assistant',
            '**Download Complete!** ✅\n\n' +
            '- **Pages Downloaded:** ' + result.pages_exported + '\n' +
            '- **File Size:** ' + result.file_size_kb + ' KB\n' +
            '- **Download ID:** ' + result.export_id + '\n\n' +
            'The markdown file has been saved to your computer.',
            null, false
        );

    } catch (error) {
        console.error('Download error:', error);
        addMessage('assistant', '**Download Failed:** ' + error.message, null, false);
    } finally {
        const hasSeedUrls = document.getElementById('seedUrlsInput').value.trim().length > 0;
        downloadBtn.disabled = !hasSeedUrls;
        downloadBtn.textContent = 'Download';
    }
}

function updateDownloadButtonState() {
    const downloadBtn = document.getElementById('downloadBtn');
    const seedUrlsInput = document.getElementById('seedUrlsInput');
    const hasSeedUrls = seedUrlsInput.value.trim().length > 0;
    downloadBtn.disabled = !hasSeedUrls;
}

function handleClearOrStop() {
    if (isRequestInProgress) {
        stopRequest();
    } else {
        clearChat();
    }
}

async function stopRequest() {
    if (!conversationId) {
        console.log('No conversation to stop');
        return;
    }

    const clearBtn = document.getElementById('clearBtn');
    clearBtn.textContent = 'Stopping...';
    clearBtn.disabled = true;

    try {
        // First, abort the client-side fetch
        if (currentAbortController) {
            console.log('Aborting client-side request...');
            currentAbortController.abort();
        }

        // Then, call the server to cancel the agent
        console.log('Sending cancel request to server for conversation:', conversationId);
        const cancelResponse = await fetchWithAuth(`/api/agent/cancel/${conversationId}`, {
            method: 'POST'
        });
        const cancelData = await cancelResponse.json();
        console.log('Cancel response:', cancelData);

        // Poll for completion - wait until agent is fully stopped
        let attempts = 0;
        const maxAttempts = 30; // 30 seconds max wait
        while (attempts < maxAttempts) {
            await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second

            const statusResponse = await fetchWithAuth(`/api/agent/status/${conversationId}`);
            const statusData = await statusResponse.json();
            console.log('Status check:', statusData);

            if (!statusData.busy) {
                console.log('Agent fully stopped');
                break;
            }
            attempts++;
        }

        if (attempts >= maxAttempts) {
            console.warn('Timeout waiting for agent to stop');
        }

    } catch (error) {
        console.error('Error stopping request:', error);
    } finally {
        // Reset UI - the finally block in submitRequest may have already done this
        // but we do it again in case the fetch was already aborted
        isRequestInProgress = false;
        currentAbortController = null;
        clearBtn.textContent = 'Clear Chat';
        clearBtn.classList.remove('stop-mode');
        clearBtn.disabled = false;

        const sendBtn = document.getElementById('sendBtn');
        const messageInput = document.getElementById('messageInput');
        const loading = document.getElementById('loading');

        sendBtn.disabled = false;
        messageInput.disabled = false;
        loading.classList.remove('active');
        updateDownloadButtonState();
        messageInput.focus();
    }
}

function clearChat() {
    const chatArea = document.getElementById('chatArea');
    chatArea.innerHTML = '';
    conversationId = '';
    clearHistoryFlag = true;
    document.getElementById('messageInput').value = '';
    addMessage('assistant', '**Chat cleared!** Start a new conversation.', null, false);
}

// Initialize on page load
loadConfig();

// =============================================================================
// Fullscreen Mode
// =============================================================================

let isFullscreen = false;

function toggleFullscreen() {
    const container = document.getElementById('mainContainer');
    isFullscreen = !isFullscreen;

    if (isFullscreen) {
        container.classList.add('fullscreen-mode');
        document.body.style.overflow = 'hidden';
    } else {
        container.classList.remove('fullscreen-mode');
        document.body.style.overflow = '';
    }
}

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isFullscreen) {
        toggleFullscreen();
    }
});

// =============================================================================
// Save Conversation to Markdown
// =============================================================================

function saveConversationToMarkdown() {
    const chatArea = document.getElementById('chatArea');
    const messages = chatArea.querySelectorAll('.message');

    if (messages.length === 0) {
        alert('No conversation to save.');
        return;
    }

    let markdown = '# HiChat Conversation\n\n';
    markdown += `**Date:** ${new Date().toLocaleString()}\n\n`;
    markdown += `**Workflow:** ${currentWorkflow}\n\n`;
    markdown += '---\n\n';

    messages.forEach((msg, index) => {
        const isUser = msg.classList.contains('user');
        const role = isUser ? '👤 **User**' : '🤖 **Assistant**';

        const contentEl = msg.querySelector('.message-content');
        let content = '';

        if (isUser) {
            content = contentEl.textContent.trim();
        } else {
            const markdownEl = contentEl.querySelector('.markdown-content');
            if (markdownEl) {
                content = extractMarkdownFromElement(markdownEl);
            } else {
                content = contentEl.textContent.trim();
            }
        }

        markdown += `## ${role}\n\n`;
        markdown += content + '\n\n';

        if (index < messages.length - 1) {
            markdown += '---\n\n';
        }
    });

    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    link.href = url;
    link.download = `hichat-conversation-${timestamp}.md`;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

function extractMarkdownFromElement(element) {
    let result = '';

    const clone = element.cloneNode(true);

    const codeBlocks = clone.querySelectorAll('pre code');
    codeBlocks.forEach((block, i) => {
        const language = block.className.replace('language-', '') || '';
        const code = block.textContent;
        block.parentElement.outerHTML = `\n\`\`\`${language}\n${code}\n\`\`\`\n`;
    });

    const inlineCode = clone.querySelectorAll('code');
    inlineCode.forEach(code => {
        code.outerHTML = '`' + code.textContent + '`';
    });

    for (let i = 1; i <= 6; i++) {
        const headers = clone.querySelectorAll(`h${i}`);
        headers.forEach(h => {
            h.outerHTML = '\n' + '#'.repeat(i) + ' ' + h.textContent + '\n';
        });
    }

    const bolds = clone.querySelectorAll('strong, b');
    bolds.forEach(b => {
        b.outerHTML = '**' + b.textContent + '**';
    });

    const italics = clone.querySelectorAll('em, i');
    italics.forEach(i => {
        i.outerHTML = '*' + i.textContent + '*';
    });

    const uls = clone.querySelectorAll('ul');
    uls.forEach(ul => {
        const items = ul.querySelectorAll('li');
        let listText = '\n';
        items.forEach(li => {
            listText += '- ' + li.textContent.trim() + '\n';
        });
        ul.outerHTML = listText;
    });

    const ols = clone.querySelectorAll('ol');
    ols.forEach(ol => {
        const items = ol.querySelectorAll('li');
        let listText = '\n';
        items.forEach((li, idx) => {
            listText += (idx + 1) + '. ' + li.textContent.trim() + '\n';
        });
        ol.outerHTML = listText;
    });

    const links = clone.querySelectorAll('a');
    links.forEach(a => {
        const href = a.getAttribute('href') || '';
        const text = a.textContent;
        a.outerHTML = `[${text}](${href})`;
    });

    const paragraphs = clone.querySelectorAll('p');
    paragraphs.forEach(p => {
        p.outerHTML = p.textContent + '\n\n';
    });

    result = clone.textContent || clone.innerText;
    result = result.replace(/\n{3,}/g, '\n\n').trim();

    return result;
}

// ===================== Claude Authentication Functions =====================

let claudeAuthState = {
    enabled: false,
    authenticated: false,
    models: []
};

// Check Claude auth status on load
async function checkClaudeAuthStatus() {
    try {
        const response = await fetch('/api/claude/auth/status');
        const status = await response.json();
        claudeAuthState.enabled = status.enabled;
        claudeAuthState.authenticated = status.authenticated;

        // Show/hide Claude button and update its state
        updateClaudeAuthUI();

        // If authenticated, load Claude models
        if (status.authenticated) {
            await loadClaudeModels();
        }

        return status;
    } catch (error) {
        console.error('Failed to check Claude auth status:', error);
        return { enabled: false, authenticated: false };
    }
}

// Update Claude auth button UI
function updateClaudeAuthUI() {
    const claudeBtn = document.getElementById('claudeAuthBtn');

    if (claudeBtn) {
        // Always show the button
        claudeBtn.style.display = 'block';

        if (claudeAuthState.authenticated) {
            claudeBtn.classList.add('authenticated');
            claudeBtn.textContent = '✓ Claude Active';
            claudeBtn.title = 'Claude authenticated - Click to sign out';
        } else {
            claudeBtn.classList.remove('authenticated');
            claudeBtn.textContent = '⚡ Use Claude';
            claudeBtn.title = 'Authenticate with Claude Code';
        }
    }
}

// Toggle Claude authentication
async function toggleClaudeAuth() {
    const claudeBtn = document.getElementById('claudeAuthBtn');

    if (claudeAuthState.authenticated) {
        // Sign out
        if (confirm('Sign out from Claude Code?')) {
            try {
                claudeBtn.disabled = true;
                const response = await fetch('/api/claude/auth/logout', {
                    method: 'POST'
                });

                if (response.ok) {
                    claudeAuthState.authenticated = false;
                    claudeAuthState.models = [];
                    updateClaudeAuthUI();

                    // Remove Claude models from model selector
                    removeClaudeModelsFromSelector();

                    showToast('✓ Signed out from Claude successfully', 'success');
                } else {
                    showToast('✗ Failed to sign out', 'error');
                }
            } catch (error) {
                console.error('Claude logout error:', error);
                showToast('✗ Sign out failed: ' + error.message, 'error');
            } finally {
                claudeBtn.disabled = false;
            }
        }
    } else {
        // Sign in
        try {
            claudeBtn.disabled = true;
            claudeBtn.textContent = '⏳ Authenticating...';

            showToast('🔐 Opening browser for Claude SSO login...', 'info');

            const response = await fetch('/api/claude/auth/login', {
                method: 'POST'
            });

            const result = await response.json();

            if (response.ok) {
                claudeAuthState.authenticated = true;
                updateClaudeAuthUI();

                // Load Claude models and add to selector
                await loadClaudeModels();
                addClaudeModelsToSelector();

                showToast('✓ Claude authentication successful!', 'success');
            } else {
                showToast('✗ Authentication failed: ' + result.detail, 'error');
            }
        } catch (error) {
            console.error('Claude login error:', error);
            showToast('✗ Authentication failed: ' + error.message, 'error');
        } finally {
            claudeBtn.disabled = false;
            updateClaudeAuthUI();
        }
    }
}

// Load Claude models
async function loadClaudeModels() {
    try {
        const response = await fetch('/api/claude/models');
        const data = await response.json();
        claudeAuthState.models = data.models || [];
        console.log('Loaded Claude models:', claudeAuthState.models);
        return claudeAuthState.models;
    } catch (error) {
        console.error('Failed to load Claude models:', error);
        return [];
    }
}

// Add Claude models to model selector
function addClaudeModelsToSelector() {
    const modelSelector = document.getElementById('modelSelector');

    if (!modelSelector || claudeAuthState.models.length === 0) {
        return;
    }

    // Remove existing Claude models first
    removeClaudeModelsFromSelector();

    // Add separator if there are existing models
    if (modelSelector.options.length > 0) {
        const separator = document.createElement('option');
        separator.disabled = true;
        separator.textContent = '──────────';
        modelSelector.appendChild(separator);
    }

    // Add Claude models
    claudeAuthState.models.forEach(model => {
        const option = document.createElement('option');
        option.value = model.name;
        option.textContent = model.display_name || model.name;
        option.dataset.provider = 'claude';
        modelSelector.appendChild(option);
    });

    // Select first Claude model
    if (claudeAuthState.models.length > 0) {
        const firstClaudeOption = Array.from(modelSelector.options).find(
            opt => opt.dataset.provider === 'claude'
        );
        if (firstClaudeOption) {
            modelSelector.value = firstClaudeOption.value;
        }
    }
}

// Remove Claude models from model selector
function removeClaudeModelsFromSelector() {
    const modelSelector = document.getElementById('modelSelector');
    if (!modelSelector) return;

    // Remove all options with provider='claude' and surrounding separator
    const optionsToRemove = [];
    let foundSeparatorBefore = false;

    for (let i = 0; i < modelSelector.options.length; i++) {
        const option = modelSelector.options[i];

        // Check if this is a separator before Claude models
        if (option.disabled && option.textContent.includes('─')) {
            foundSeparatorBefore = true;
            optionsToRemove.push(i);
            continue;
        }

        if (option.dataset.provider === 'claude') {
            optionsToRemove.push(i);
        } else if (foundSeparatorBefore && option.dataset.provider !== 'claude') {
            // Reset flag if we find non-Claude model after separator
            foundSeparatorBefore = false;
        }
    }

    // Remove in reverse order to maintain indices
    for (let i = optionsToRemove.length - 1; i >= 0; i--) {
        modelSelector.remove(optionsToRemove[i]);
    }

    // Select first available model if current selection was Claude
    if (modelSelector.selectedOptions.length === 0 && modelSelector.options.length > 0) {
        modelSelector.selectedIndex = 0;
    }
}

// Show toast notification
function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background: ${type === 'success' ? '#38ef7d' : type === 'error' ? '#ff6b6b' : '#667eea'};
        color: white;
        padding: 15px 25px;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        z-index: 10000;
        font-weight: 600;
        animation: slideInRight 0.3s ease;
    `;

    document.body.appendChild(toast);

    // Remove after 4 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 4000);
}

// Add CSS animations for toast
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Initialize Claude auth on page load
window.addEventListener('DOMContentLoaded', async () => {
    await checkClaudeAuthStatus();
});
