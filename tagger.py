"""
MVP tagger: every item always gets its source's default category tag,
plus any extra tags whose keywords appear in the title/excerpt.

This is intentionally dumb -- weighted random sampling over these tags
is enough to make the app feel personalized (see README). Swap in
embeddings-based similarity once there's real behavior data to train on.
"""

KEYWORD_TAGS = {
    "photography": ["photo", "photograph", "camera", "lens"],
    "architecture": ["architecture", "building", "urban design"],
    "science": ["physics", "biology", "space", "research", "study finds"],
    "history": ["history", "ancient", "archive", "archaeolog"],
    "diy": ["how to build", "tutorial", "diy", "hardware hack"],
    "food": ["recipe", "restaurant", "cuisine", "chef"],
    "weird": ["bizarre", "unusual", "strange", "obscure"],
}


def tag_item(default_category: str, title: str, excerpt: str) -> list[str]:
    text = f"{title} {excerpt}".lower()
    tags = {default_category}
    for tag, keywords in KEYWORD_TAGS.items():
        if any(kw in text for kw in keywords):
            tags.add(tag)
    return sorted(tags)
