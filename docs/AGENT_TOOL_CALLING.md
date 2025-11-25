# Agent Tool Calling Architecture

## Overview

The Code Intelligence Agent now supports **iterative tool calling**, allowing the LLM to dynamically search and read files from multiple sources during workflow execution.

## Architecture Changes (v2.1)

### Before: Single-Pass Template Execution
```
User Request → Gather Context → Single LLM Call → Response
```

**Limitations:**
- Required all context upfront
- No dynamic file discovery
- Couldn't adapt based on findings

### After: Iterative Tool Calling
```
User Request → Gather Initial Context → LLM Call
                                         ↓
                                    Tool Calls? ──No──→ Response
                                         ↓ Yes
                                    Execute Tools
                                         ↓
                                    LLM Call (with results)
                                         ↓
                                    (repeat up to 20 iterations)
```

**Benefits:**
- Dynamic file discovery
- Intelligent search strategies
- Adapts based on findings
- Handles complex multi-step queries

## Available Tools

### Local File Access (MCP Server)
- `read_file`: Read file content
- `list_directory`: List files in directory
- `search_files`: Semantic search (optional)

### Azure DevOps (MCP Server)
- `search_azure_devops_files`: Search files with patterns
- `search_azure_devops_code`: Fast indexed code search
- `get_azure_devops_file`: Retrieve file content

## Iteration Management

### Configuration
```python
max_iterations = 20  # Default limit
```

### Iteration Flow
1. **Initial LLM Call**: With user prompt and initial context
2. **Tool Call Detection**: Check if LLM requested tools
3. **Tool Execution**: Execute all requested tools in parallel
4. **Result Injection**: Add tool results to conversation
5. **Next Iteration**: LLM processes results and decides next action
6. **Termination**: Stop when LLM provides final answer or hits limit

### Logging
```python
logger.info(f"LLM requested {len(response['tool_calls'])} tool call(s)")
logger.debug(f"Tool arguments: {arguments}")
logger.info(f"Tool call {tool_name} succeeded")
logger.warning(f"Reached max iterations ({max_iterations})")
```

## Example: Package Dependency Analysis

**User Request:** "Recursively scan Microsoft-NanoServer-IIS package and show full package tree"

**Execution Flow:**

| Iteration | Tool Call | Purpose |
|-----------|-----------|---------|
| 1 | `search_azure_devops_files(keyword='Microsoft-NanoServer-IIS')` | Find main package file |
| 2 | `get_azure_devops_file('/MergedComponents/pkggen/Microsoft-NanoServer-IIS.json')` | Read package definition |
| 3 | `search_azure_devops_files(keyword='Microsoft-NanoServer-IIS-Internal')` | Find dependency |
| 4 | `search_azure_devops_code(query='IIS-Internal package')` | Broad search for related packages |
| 5-19 | Multiple searches with different patterns | Explore different paths |
| 20 | `search_azure_devops_code(query='Microsoft-NanoServer-IIS-ServerCommon-Internal-Package')` | Final search |

**Result:** Hit 20-iteration limit, returned last LLM response

## Performance Considerations

### Typical Iteration Counts
- **Simple queries**: 1-3 iterations
- **File reading**: 2-5 iterations
- **Complex searches**: 5-15 iterations
- **Deep exploration**: 15-20 iterations

### Time Per Iteration
- Tool execution: 0.2-1 second (Azure DevOps API)
- LLM call: 3-5 seconds (Claude Sonnet 4.5)
- **Total per iteration**: ~4-6 seconds

### Optimization Strategies

**1. Increase Iteration Limit** (when needed)
```python
max_iterations = 30  # For complex analysis
```

**2. Better System Prompts** (guide LLM behavior)
```python
"After finding the target file, analyze it immediately rather than exploring alternatives."
```

**3. Result Caching** (avoid redundant searches)
```python
# Cache successful tool results
self._tool_result_cache[cache_key] = result
```

**4. Early Stopping** (detect completion)
```python
if "final answer" in response.get("content", "").lower():
    logger.info("LLM indicated completion, stopping early")
    break
```

## Comparison: Before vs After

### Before (Single-Pass)
```
User: "Find Microsoft-NanoServer-IIS dependencies"
Agent: Reads all pkggen files → LLM analyzes → Response
Time: 2 minutes (timeout on large reads)
Success: Failed (too slow)
```

### After (Iterative Tool Calling)
```
User: "Find Microsoft-NanoServer-IIS dependencies"
Agent: Search for file → Read file → Search dependencies → Read dependencies → Analyze → Response
Time: 4 minutes (20 iterations × 12 seconds)
Success: Completed (but hit iteration limit)
```

### Optimized (With Better Prompts)
```
User: "Find Microsoft-NanoServer-IIS dependencies"
Agent: Search for file → Read file → Analyze dependencies → Response
Time: 30 seconds (3 iterations × 10 seconds)
Success: Completed (stopped early)
```

## Error Handling

### Timeout Handling
```python
try:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(...)
except httpx.TimeoutException:
    return {"error": "Tool call timed out after 60 seconds"}
```

### Tool Failure Recovery
```python
if tool_result.get("error"):
    logger.error(f"Tool call {tool_name} failed: {tool_result['error']}")
    # Continue to next iteration with error message
    # LLM can try alternative approaches
```

### Iteration Limit Handling
```python
if iteration >= max_iterations:
    logger.warning(f"Reached max iterations ({max_iterations}), returning last response")
    # Return whatever LLM has produced so far
    return response
```

## Future Improvements

### 1. Parallel Tool Execution
Currently: Sequential tool calls
Planned: Execute independent tools in parallel
```python
# Execute all tool calls concurrently
results = await asyncio.gather(*[
    self._handle_tool_call(tc) for tc in tool_calls
])
```

### 2. Smart Caching
Currently: No caching
Planned: Cache file content and search results
```python
cache_key = f"{tool_name}:{json.dumps(arguments)}"
if cache_key in self._cache:
    return self._cache[cache_key]
```

### 3. Adaptive Iteration Limits
Currently: Fixed at 20
Planned: Adjust based on query complexity
```python
if is_simple_query(request):
    max_iterations = 10
elif is_complex_analysis(request):
    max_iterations = 40
```

### 4. Progress Streaming
Currently: Silent until completion
Planned: Stream progress updates to client
```python
yield {"type": "progress", "iteration": 5, "action": "searching files"}
```

## Best Practices

### For Users
1. **Be Specific**: "Read file X and analyze dependencies" vs "Explore package tree"
2. **Limit Scope**: "Find 2 child packages" vs "Find all related packages"
3. **Provide Context**: Include reference files to guide LLM

### For Developers
1. **Monitor Iterations**: Watch for inefficient search patterns
2. **Tune Prompts**: Guide LLM to be more direct
3. **Set Appropriate Limits**: Balance thoroughness vs cost
4. **Add Logging**: Track tool usage patterns

## Troubleshooting

### Problem: Too Many Iterations
**Symptoms:** Hits 20-iteration limit frequently
**Solutions:**
- Add system prompt to be more direct
- Increase iteration limit if legitimate need
- Cache frequently accessed files

### Problem: Redundant Searches
**Symptoms:** Same searches repeated multiple times
**Solutions:**
- Implement result caching
- Improve LLM prompt to avoid redundancy
- Add deduplication logic

### Problem: Slow Response
**Symptoms:** Takes 3-4 minutes to complete
**Solutions:**
- Optimize Azure DevOps queries (use indexed search)
- Reduce context size passed to LLM
- Use faster LLM model for simple queries

## Related Documentation

- [Code Intelligence Agent](CODE_INTELLIGENCE_AGENT.md) - Main agent documentation
- [Azure DevOps MCP Server](../mcp_servers/azure_devops_mcp_server/README.md) - Tool provider
- [Architecture](ARCHITECTURE.md) - System overview
