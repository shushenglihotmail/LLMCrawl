# Quick Reference: Environment Configuration

## ⚙️ Configuration File Location

```
LLMCrawl/
├── deploy/
│   ├── .env              ← USE THIS FILE
│   └── .env.example      ← Copy this to create .env
└── docs/
    └── CONFIGURATION.md  ← Complete documentation
```

## 🚀 Setup (3 Steps)

```bash
# 1. Copy template
cd deploy
cp .env.example .env

# 2. Edit with your credentials
nano .env  # or use your favorite editor

# 3. Start services
docker compose up -d
```

## 🔄 After Changing .env

**⚠️ IMPORTANT:** Use `--force-recreate` to reload environment variables

```bash
cd deploy
docker compose up -d --force-recreate
```

> **Why?** `docker compose restart` does NOT reload `.env` changes!

## 📝 Required Configurations

### Minimum (for basic functionality)
```env
# Azure OpenAI
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
LLM_PROVIDER=azure

# Models (JSON array)
LLM_MODELS=[{"name":"gpt-4",...}]
```

### For Azure DevOps Integration
```env
# Add to deploy/.env
AZURE_DEVOPS_PAT=your-pat-here
AZURE_DEVOPS_BRANCH=main
```

### For Authenticated Sites (Optional)
```env
# Add to deploy/.env
FIRECRAWL_AUTH_TYPE=cookies
AUTH_TEST_URL=https://your-site.com
FIRECRAWL_AUTH_STORAGE_STATE=<captured_state>
```

## 🔍 Troubleshooting

### Problem: Changes not applied
```bash
# ❌ WRONG - Won't reload .env
docker compose restart

# ✅ CORRECT - Loads new .env
cd deploy
docker compose up -d --force-recreate
```

### Problem: Missing environment variable
```bash
# Check if variable exists in deploy/.env
cd deploy
grep VARIABLE_NAME .env
```

### Problem: Wrong .env location
```bash
# ❌ DO NOT create .env here
LLMCrawl/.env

# ✅ USE this location
LLMCrawl/deploy/.env
```

## 📚 Documentation

- **[CONFIGURATION.md](CONFIGURATION.md)** - Complete configuration guide
- **[README.md](../README.md)** - Main project documentation
- **[deploy/.env.example](../deploy/.env.example)** - Example with all options
- **[MULTI_PROVIDER_LLM.md](MULTI_PROVIDER_LLM.md)** - LLM provider setup
- **[tools/msauth/README.md](../tools/msauth/README.md)** - Firecrawl authentication

## 🔐 Security

1. ✅ Never commit `deploy/.env` (already in `.gitignore`)
2. ✅ Use environment variables, not hardcoded credentials
3. ✅ Rotate API keys and PATs regularly
4. ✅ Use separate dev/prod configurations
