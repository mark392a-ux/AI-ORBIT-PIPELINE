"""
Discovery stage: defines *what* each extractor should search for.

Keeping this declarative and separate from extraction logic means adding
new coverage (a new search term, a new GitHub topic) never requires
touching extractor code — it's a config change, which keeps the pipeline
modular and scalable per the spec's architecture requirement.
"""

# GitHub topics/queries — covers Tools, Repositories, MCP, Robots, Devices.
GITHUB_TOPIC_QUERIES = [
    {"query": "topic:mcp-server", "category_hint": "MCP"},
    {"query": "topic:model-context-protocol", "category_hint": "MCP"},
    {"query": "mcp server in:name,description stars:>50", "category_hint": "MCP"},
    {"query": "topic:llm-agent stars:>200", "category_hint": "Tools"},
    {"query": "topic:ai-agent stars:>300", "category_hint": "Tools"},
    {"query": "topic:generative-ai stars:>500", "category_hint": "Creative"},
    {"query": "topic:robotics stars:>200", "category_hint": "Robots"},
    {"query": "topic:humanoid-robot", "category_hint": "Robots"},
    {"query": "topic:edge-ai stars:>100", "category_hint": "Devices"},
    {"query": "topic:tinyml stars:>50", "category_hint": "Devices"},
    {"query": "topic:rag stars:>300", "category_hint": "Tools"},
    {"query": "topic:llm-framework stars:>300", "category_hint": "Tools"},
    {"query": "topic:voice-assistant stars:>100", "category_hint": "Personal"},
    {"query": "topic:personal-assistant stars:>50", "category_hint": "Personal"},
    {"query": "topic:awesome-list ai stars:>500", "category_hint": "Collections"},
]

# Hugging Face Hub search terms — covers Models.
HUGGINGFACE_MODEL_QUERIES = [
    {"query": "text-generation", "sort": "downloads", "category_hint": "Models"},
    {"query": "text-to-image", "sort": "downloads", "category_hint": "Creative"},
    {"query": "speech-recognition", "sort": "downloads", "category_hint": "Models"},
    {"query": "robotics", "sort": "downloads", "category_hint": "Robots"},
]

# Hugging Face Spaces search terms — covers Tools/Collections (interactive
# apps, not raw model weights). Uses the real /api/spaces endpoint.
HUGGINGFACE_SPACE_QUERIES = [
    {"query": "agent", "category_hint": "Tools"},
    {"query": "chat", "category_hint": "Personal"},
    {"query": "image generator", "category_hint": "Creative"},
    {"query": "leaderboard", "category_hint": "Collections"},
]

# YouTube search terms — covers Videos.
YOUTUBE_SEARCH_QUERIES = [
    "AI agent tutorial 2026",
    "Model Context Protocol MCP explained",
    "best AI tools review",
    "humanoid robot demo",
    "new AI model release",
]

# RSS/news feeds — covers News, Companies (via mentions).
RSS_FEEDS = [
    {"url": "https://techcrunch.com/category/artificial-intelligence/feed/", "name": "TechCrunch AI"},
    {"url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "name": "The Verge AI"},
    {"url": "https://venturebeat.com/category/ai/feed/", "name": "VentureBeat AI"},
    {"url": "https://www.artificialintelligence-news.com/feed/", "name": "AI News"},
]

# Known official product / company sites for selective, targeted enrichment
# (used sparingly, per "Official Product Sites (selective)").
OFFICIAL_SITES = [
    {"name": "OpenAI", "url": "https://openai.com", "category_hint": "Company"},
    {"name": "Anthropic", "url": "https://www.anthropic.com", "category_hint": "Company"},
    {"name": "Mistral AI", "url": "https://mistral.ai", "category_hint": "Company"},
    {"name": "Hugging Face", "url": "https://huggingface.co", "category_hint": "Company"},
    {"name": "Figure AI", "url": "https://www.figure.ai", "category_hint": "Company"},
    {"name": "Boston Dynamics", "url": "https://bostondynamics.com", "category_hint": "Company"},
    {"name": "Stability AI", "url": "https://stability.ai", "category_hint": "Company"},
    {"name": "DeepSeek", "url": "https://www.deepseek.com", "category_hint": "Company"},
    {"name": "Black Forest Labs", "url": "https://blackforestlabs.ai", "category_hint": "Company"},
    {"name": "Qwen", "url": "https://qwenlm.github.io", "category_hint": "Company"},
]
