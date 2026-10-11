import os
import json
import requests
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID")

genai.configure(api_key=GEMINI_API_KEY)

def fetch_discord_structure():
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    
    roles_resp = requests.get(f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/roles", headers=headers)
    roles = roles_resp.json() if roles_resp.status_code == 200 else []
    
    channels_resp = requests.get(f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/channels", headers=headers)
    channels = channels_resp.json() if channels_resp.status_code == 200 else []
    
    clean_roles = [{"name": r["name"], "permissions": r["permissions"], "position": r["position"], "hoist": r["hoist"]} for r in roles]
    clean_channels = []
    for c in channels:
        clean_channels.append({
            "name": c.get("name"),
            "type": c.get("type"),
            "parent_id": c.get("parent_id"),
            "permission_overwrites": c.get("permission_overwrites", [])
        })
        
    return {"roles": clean_roles, "channels": clean_channels}

def audit_server_with_gemini(server_data):
    prompt = f"""
    You are an expert Discord server architect and security auditor. 
    Analyze the following Discord server roles and channel/permission setup:

    {json.dumps(server_data, indent=2)}

    INSTRUCTIONS:
    1. Provide a clear summary of how the server's channels, categories, and role hierarchy are currently organized.
    2. Identify any permission flaws, risky overrides (e.g., @everyone having send/manage permissions where they shouldn't, overlapping role hierarchies, or broken channel nesting), or redundant structures.
    3. Suggest specific, actionable fixes to streamline the setup, secure permissions, and improve member experience.
    
    Format your response cleanly in Markdown with bold headers and bullet points.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    return response.text

def main():
    print("Fetching server structure from Discord API...")
    server_data = fetch_discord_structure()
    
    if not server_data["roles"] and not server_data["channels"]:
        print("Error: Could not fetch server data. Check your bot token and Guild ID.")
        return

    print("Running AI architectural audit via Gemini...")
    audit_report = audit_server_with_gemini(server_data)
    
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write("# 🛡️ Discord Server Permissions & Architecture Audit\n\n")
            f.write(audit_report)
            
    print("Audit complete! Check your GitHub Actions run summary for the full report.")

if __name__ == "__main__":
    main()
