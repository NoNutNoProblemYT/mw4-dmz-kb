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
                    
                    content_body = ""
                    if hasattr(entry, 'content') and entry.content:
                        content_body = entry.content[0].get('value', '')
                    elif hasattr(entry, 'summary'):
                        content_body = entry.summary
                        
                    new_articles.append({
                        "id": article_id,
                        "source": feed_info["name"],
                        "title": entry.title,
                        "content": content_body,
                        "link": entry.link,
                        "published": entry.get("published", "")
                    })
        except Exception as e:
            print(f"Warning: Could not fetch {feed_info['name']}: {e}")
    return new_articles

def verify_and_format_with_gemini(db_index, articles):
    existing_topics = db_index.get("verified_topics", [])
    prompt = f"""
    You are an automated official documentation engineer for the Modern Warfare 4 (MW4 / 2026) DMZ mode knowledge base.

    DATABASE STATE (Already logged topics):
    {json.dumps(existing_topics, indent=2)}

    INCOMING CANDIDATE ENTRIES FROM OFFICIAL SOURCES (INCLUDING FULL POST/BODY CONTENT):
    {json.dumps(articles, indent=2)}

    STRICT VERSION & GAME FILTERING RULES:
    1. MUST be explicitly for Modern Warfare 4 (MW4 / 2026) DMZ mode. Check titles, post text, and context carefully.
    2. STRICTLY REJECT and IGNORE any content regarding MW2 (Modern Warfare II / 2022/2023) DMZ, old Al Mazrah, Ashika Island, Vondel, Building 21, or legacy MWII updates.
    3. MUST be directly about MW4 DMZ gameplay mechanics, FOB, Hajin map, patch notes, or official blog releases.
    4. REJECT all general multiplayer, Warzone battle royale, mobile, or campaign notes unless they specifically alter MW4 DMZ.
    5. REJECT any item that duplicates information already present in the existing database state.

    OUTPUT INSTRUCTIONS:
    - If valid, non-duplicate, MW4 DMZ intel exists:
      - Add new topics to `new_topics`.
      - Write clean Markdown format for documentation appending (`markdown_entry`).
      - Draft a detailed text-based summary of what was found (`discord_summary`).
      - Draft a concise, quick-reading TL;DR summary highlighting the key new additions (`tldr_summary`).
    
    Respond ONLY with valid JSON matching this schema:
    {{
      "has_new_intel": boolean,
      "new_topics": ["topic1", "topic2"],
      "markdown_entry": "formatted markdown string or empty",
      "discord_summary": "detailed text-based summary of what updated info was found or empty",
      "tldr_summary": "quick-reading TL;DR summary of the new items or empty"
    }}
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        prompt, 
        generation_config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

def write_step_summary(status_text, details=""):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(f"### 🔍 MW4 DMZ Intel Check Report\n")
            f.write(f"- **Check Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write(f"- **Feeds Checked:** {len(OFFICIAL_FEEDS)} official sources\n")
            f.write(f"- **Status:** {status_text}\n")
            if details:
                f.write(f"\n{details}\n")

def send_discord_notification(title, description, color):
    if not DISCORD_WEBHOOK_URL:
        return
    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "url": "https://github.com/NoNutNoProblemYT/mw4-dmz-kb",
            "color": color, 
            "footer": {"text": f"MW4 DMZ Official Monitor • {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def main():
    print("Starting Official MW4 DMZ Intel Sync...")
    db_index = load_db_index()
    articles = fetch_official_news()
    unprocessed = [a for a in articles if a["id"] not in db_index["processed_ids"]]
    
    check_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') + " UTC"
    singular_date = datetime.utcnow().strftime('%B %d, %Y') # e.g., October 11, 2026

    if not unprocessed:
        print("No new RSS entries from official feeds.")
        write_step_summary("💤 Checked. No new raw RSS items found from official feeds. Discord was kept silent.")
        return # NOTHING posts to Discord when empty

    print(f"Evaluating {len(unprocessed)} new official entries via Gemini verification...")
    result = verify_and_format_with_gemini(db_index, unprocessed)

    for a in unprocessed:
        db_index["processed_ids"].append(a["id"])

    if result.get("has_new_intel"):
        print("New official MW4 DMZ patch notes/updates verified! Updating database...")
        
        if os.path.exists(DOCS_PATH):
            with open(DOCS_PATH, "a") as f:
                f.write(f"\n\n## 🔄 Automated Updates ({singular_date})\n\n" + result["markdown_entry"])
        
        db_index["verified_topics"].extend(result.get("new_topics", []))
        db_index["verified_topics"] = list(set(db_index["verified_topics"]))
        db_index["last_updated"] = datetime.utcnow().isoformat()
        
        save_db_index(db_index)
        
        # DISCORD PING ONLY WHEN REAL INTEL IS FOUND
        tldr_block = f"\n\n**TL;DR - {singular_date}**\n{result.get('tldr_summary', 'Quick summary unavailable.')}"
        full_discord_desc = f"**Check Time:** `{check_time}`\n\n**Updated Information Summary:**\n{result['discord_summary']}{tldr_block}"
        
        send_discord_notification(
            "🛠️ MW4 DMZ New Official Intel Discovered!",
            full_discord_desc,
            3066993
        )
        
        write_step_summary(
            "✅ **New intel found and synced!**", 
            f"**Synced Topics:** {', '.join(result.get('new_topics', []))}\n**README & Discord updated successfully.**"
        )
        print("Sync complete. Discord notified.")
    else:
        save_db_index(db_index)
        write_step_summary("💤 Checked. New RSS items were found, but were either legacy MW2 info, duplicates, or non-DMZ news. Discord was kept silent.")
        print("No new MW4 DMZ patch notes or non-duplicate updates found.")

if __name__ == "__main__":
    main()
