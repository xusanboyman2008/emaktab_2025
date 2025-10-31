import json

# Load JSON files
# with open("old.json", "r", encoding="utf-8") as f:
#     old_data = json.load(f)

with open("database_last.json", "r", encoding="utf-8") as f:
    db_data = json.load(f)

# Combine both lists
all_logins = db_data.get("Logins", [])# +old_data.get("Logins", [])

# Use a dictionary to remove duplicates based on username
unique_logins_dict = {}
for entry in all_logins:
    username = entry["username"]

    # Set grade to "6A" if it does not exist
    # if "grade" not in entry or not entry["grade"]:
    #     entry["grade"] = "6V"
    # if entry["grade"]=="11B":
    #     entry["grade"] = "9V"


    unique_logins_dict[username] = entry

# Convert back to list
unique_logins = list(unique_logins_dict.values())# Combine both lists
all_logins = db_data.get("User", [])# +old_data.get("Logins", [])

# Use a dictionary to remove duplicates based on username
unique_users_dict = {}
for entry1 in all_logins:
    username = entry1["username"]

    # Set grade to "6A" if it does not exist
    # if "grade" not in entry or not entry["grade"]:
    #     entry["grade"] = "6V"
    # if entry["grade"]=="11B":
    #     entry["grade"] = "9V"


    unique_users_dict[username] = entry1

# Convert back to list
unique_users_dicts = list(unique_users_dict.values())

# Save to new JSON file
with open("database_last_ready.json", "w", encoding="utf-8") as f:
    json.dump({"Logins": unique_logins,"Users":unique_users_dicts}, f, ensure_ascii=False, indent=4)

print(f"Saved {len(unique_logins)} unique usernames with all data (missing grades set to 6A) to new_Database.json")
