# Multi-Provider LLM Support

LLMCrawl supports multiple LLM providers with automatic routing based on model configuration.

## Supported Providers

### 1. OpenAI (Direct)
- Standard OpenAI API endpoint
- Supports: GPT-4, GPT-3.5-turbo, etc.
- Features: Full tool calling support, streaming

### 2. Azure OpenAI
- Azure-hosted OpenAI models
- Supports: GPT-4, GPT-3.5-turbo, GPT-4-turbo, etc.
- Features: Full tool calling support, streaming, Azure deployment names

### 3. Azure Anthropic (Claude)
- Azure AI Foundry hosted Claude models
- Supports: Claude Sonnet 4-5, Claude 3.5 Sonnet, etc.
- Features: HTTP-based Messages API, extended timeout (180s) for large contexts
- Limitations: No native tool calling (uses text-based workflow)

## Configuration

### Environment Variables

```bash
# Provider Selection (openai or azure)
LLM_PROVIDER=azure

# OpenAI Direct
OPENAI_API_KEY=sk-...

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_API_VERSION=2025-01-01-preview

# Azure Anthropic (Claude)
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/
# Note: Uses same AZURE_OPENAI_API_KEY

# Model Configuration (JSON array)
LLM_MODELS=[
  {
    "name": "gpt-4",
    "display_name": "GPT-4",
    "deployment_name": "gpt-4",
    "provider_type": "openai"
  },
  {
    "name": "claude-sonnet-4-5",
    "display_name": "Claude Sonnet 4-5",
    "deployment_name": "claude-sonnet-4-5",
    "provider_type": "anthropic"
  }
]
```

### Model Configuration Fields

- **name**: API identifier used in requests
- **display_name**: Human-readable name shown in UI
- **deployment_name**: Azure deployment name (for Azure providers)
- **provider_type**: Routing key (`"openai"` or `"anthropic"`)

## Usage

### API Requests

Specify the model in your chat request:

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain quantum computing",
    "model": "claude-sonnet-4-5"
  }'
```

If `model` is omitted, the first model in `LLM_MODELS` is used.

### Get Available Models

```bash
curl http://localhost:8000/api/models/available
```

Response:
```json
[
  {"name": "gpt-4", "display_name": "GPT-4"},
  {"name": "claude-sonnet-4-5", "display_name": "Claude Sonnet 4-5"}
]
```

## Implementation Details

### Routing Logic

The gateway automatically routes requests based on `provider_type`:

1. **OpenAI Provider** (`provider_type: "openai"`):
   - Uses `AsyncAzureOpenAI` or `AsyncOpenAI` client
   - Supports full tool calling API
   - Standard timeout (45s)

2. **Anthropic Provider** (`provider_type: "anthropic"`):
   - Direct HTTP POST to Azure Anthropic endpoint
   - Converts OpenAI message format → Anthropic Messages API
   - Filters out "tool" role messages (not supported)
   - Extended timeout (180s for large contexts)
   - Converts response back to OpenAI-compatible format

### Message Format Conversion

**OpenAI Format:**
```json
{
  "messages": [
    {"role": "system", "content": "You are helpful"},
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
    {"role": "tool", "content": "..."}
  ]
}
```

**Anthropic Format:**
```json
{
  "system": "You are helpful",
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ]
}
```

Notes:
- System message extracted to separate field
- Tool messages filtered out (Anthropic doesn't support them)
- Only user/assistant roles in messages array

## Best Practices

### When to Use Each Model

**GPT-4 (OpenAI):**
- ✅ Complex workflows requiring tool calls
- ✅ Web crawling and indexing operations
- ✅ Shorter contexts (<10k tokens)
- ✅ Faster response times needed

**Claude Sonnet (Anthropic):**
- ✅ Deep code analysis and understanding
- ✅ Large context analysis (up to 200k tokens)
- ✅ Nuanced writing and explanations
- ⚠️ Text-only workflows (no tool calling)
- ⚠️ Longer response times (especially for large contexts)

### Timeout Considerations

- **OpenAI models**: 45-second timeout suitable for most requests
- **Anthropic models**: 180-second timeout for large contexts (20k+ tokens)
- If you see timeout errors with Claude, consider:
  - Reducing the amount of context/code being analyzed
  - Breaking large requests into smaller chunks
  - Using GPT models for time-sensitive operations

## Troubleshooting

### "Unknown model" Error
- Ensure model name in request matches a `name` field in `LLM_MODELS`
- Check that `LLM_MODELS` environment variable is valid JSON
- Restart gateway after changing `.env` file

### Anthropic Timeout
- Default 180s timeout may be exceeded for very large contexts
- Solution: Reduce context size or split into multiple requests
- Check logs for "ReadTimeout" or "TimeoutException"

### Provider Routing Issues
- Check logs for "Model resolution" messages showing detected provider
- Verify `provider_type` field matches "openai" or "anthropic"
- Ensure correct endpoint configured for provider type

## Code Reference

- **Model Config Parsing**: `gateway/llm/client.py::get_model_config()`
- **Routing Logic**: `gateway/llm/client.py::chat_completion()`
- **OpenAI Handler**: `gateway/llm/client.py::_openai_chat_completion()`
- **Anthropic Handler**: `gateway/llm/client.py::_anthropic_chat_completion()`
- **Model API**: `gateway/routers/models.py::get_available_models()`

## Future Enhancements

- [ ] Support Anthropic tool use API when available in Azure
- [ ] Add streaming support for Anthropic models
- [ ] Support for additional providers (Gemini, Mistral, etc.)
- [ ] Per-model timeout configuration
- [ ] Automatic fallback between models
