import json

# Load JSON files
# with open("old.json", "r", encoding="utf-8") as f:
#     old_data = json.load(f)

with open("new_Database.json", "r", encoding="utf-8") as f:
    db_data = json.load(f)

# Combine both lists
all_logins = db_data.get("Logins", [])# +old_data.get("Logins", [])

# Use a dictionary to remove duplicates based on username
unique_logins_dict = {}
for entry in all_logins:
    username = entry["username"]

    # Set grade to "6A" if it does not exist
    if "grade" not in entry or not entry["grade"]:
        entry["grade"] = "6V"
    if entry["grade"]=="11B":
        entry["grade"] = "9V"


    unique_logins_dict[username] = entry

# Convert back to list
unique_logins = list(unique_logins_dict.values())

# Save to new JSON file
with open("new_Database.json", "w", encoding="utf-8") as f:
    json.dump({"Logins": unique_logins}, f, ensure_ascii=False, indent=4)

print(f"Saved {len(unique_logins)} unique usernames with all data (missing grades set to 6A) to new_Database.json")
