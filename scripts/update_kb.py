import os
import json
import hashlib
import requests
import feedparser
from datetime import datetime
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
INDEX_PATH = "db/intel_index.json"
DOCS_PATH = "README.md" # Appends safely to your main README so old work stays safe

genai.configure(api_key=GEMINI_API_KEY)

OFFICIAL_FEEDS = [
    {
        "name": "Official Call of Duty Blog",
        "url": "https://www.callofduty.com/blog/rss"
    },
    {
        "name": "r/DMZ Official Patch Notes",
        "url": "https://www.reddit.com/r/DMZ/search.rss?q=flair%3A%22Patch+Notes%22+OR+flair%3A%22Official%22&restrict_sr=on&sort=new&t=all"
    },
    {
        "name": "Infinity Ward Official Reddit",
        "url": "https://www.reddit.com/user/InfinityWard/submitted.rss"
    },
    {
        "name": "@CODUpdates Official Feed",
        "url": "https://rsshub.app/twitter/user/CODUpdates"
    }
]

def load_db_index():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            return json.load(f)
    return {"processed_ids": [], "last_updated": "", "verified_topics": []}

def save_db_index(index):
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)

def fetch_official_news():
    new_articles = []
    headers = {'User-Agent': 'MW4-DMZ-KnowledgeBase-Bot/1.0'}
    for feed_info in OFFICIAL_FEEDS:
        try:
            resp = requests.get(feed_info["url"], headers=headers, timeout=10)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                for entry in feed.entries[:5]:
                    article_id = hashlib.sha256(entry.link.encode()).hexdigest()
                    new_articles.append({
                        "id": article_id,
                        "source": feed_info["name"],
                        "title": entry.title,
                        "summary": entry.get("summary", entry.title),
                        "link": entry.link,
                        "published": entry.get("published", "")
                    })
        except Exception as e:
            print(f"Warning: Could not fetch {feed_info['name']}: {e}")
    return new_articles

def verify_and_format_with_gemini(db_index, articles):
    existing_topics = db_index.get("verified_topics", [])
    prompt = f"""
    You are an automated official documentation engineer for the MW4 DMZ mode knowledge base.

    DATABASE STATE (Already logged topics):
    {json.dumps(existing_topics, indent=2)}

    INCOMING CANDIDATE ENTRIES FROM OFFICIAL SOURCES:
    {json.dumps(articles, indent=2)}

    STRICT FILTERING RULES:
    1. MUST be directly about MW4 DMZ mode, patch notes, official mechanic adjustments, FOB updates, map changes, or bug fixes.
    2. REJECT all general multiplayer, Warzone battle royale, mobile, or campaign notes unless they specifically alter DMZ.
    3. REJECT any item that duplicates information already present in the existing database state.
    4. MUST be official developer patch notes or verified official blog releases.

    OUTPUT INSTRUCTIONS:
    - If valid, non-duplicate, official DMZ intel exists:
      - Add new topics to `new_topics`.
      - Write clean Markdown format for documentation appending.
      - Draft an official Discord alert embed summary highlighting exact patch/change details.

    Respond ONLY with valid JSON matching this schema:
    {{
      "has_new_intel": boolean,
      "new_topics": ["topic1", "topic2"],
      "markdown_entry": "formatted markdown string or empty",
      "discord_summary": "official patch/notes summary for discord or empty"
    }}
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        prompt, 
        generation_config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

def send_discord_notification(summary):
    if not DISCORD_WEBHOOK_URL or not summary:
        return
    payload = {
        "embeds": [{
            "title": "🛠️ MW4 DMZ Official Patch Notes / Intel Sync",
            "description": summary,
            "url": "https://github.com/NoNutNoProblemYT/mw4-dmz-kb",
            "color": 3066993,
            "footer": {"text": "MW4 DMZ Official Source Monitor • No Duplicates Verified"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def main():
    print("Starting Official MW4 DMZ Intel Sync...")
    db_index = load_db_index()
    articles = fetch_official_news()
    unprocessed = [a for a in articles if a["id"] not in db_index["processed_ids"]]

    if not unprocessed:
        print("No new RSS entries from official feeds.")
        return

    print(f"Evaluating {len(unprocessed)} new official entries via Gemini verification...")
    result = verify_and_format_with_gemini(db_index, unprocessed)

    for a in unprocessed:
        db_index["processed_ids"].append(a["id"])

    if result.get("has_new_intel"):
        print("New official DMZ patch notes/updates verified! Updating database...")

        if os.path.exists(DOCS_PATH):
            with open(DOCS_PATH, "a") as f:
                f.write("\n\n## 🔄 Automated Updates\n\n" + result["markdown_entry"])

        db_index["verified_topics"].extend(result.get("new_topics", []))
        db_index["verified_topics"] = list(set(db_index["verified_topics"]))
        db_index["last_updated"] = datetime.utcnow().isoformat()

        save_db_index(db_index)
        send_discord_notification(result["discord_summary"])
        print("Sync complete. Discord notified.")
    else:
        save_db_index(db_index)
        print("No new official DMZ patch notes or non-duplicate updates found.")

if __name__ == "__main__":
    main()
