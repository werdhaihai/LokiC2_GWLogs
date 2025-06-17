import re
import argparse
from pathlib import Path
from datetime import datetime
import requests
import sys

# ghostwriter vars
ghostwriter_url = ""
ghostwriter_oplog_id = ""
ghostwriter_api_key = ""

# Replace host with hostname payload is executing on for the log file
host = ""
# Replace operator with operator executing commands
operator = ""

# GraphQL Mutation Template
INSERT_QUERY = """
mutation InsertMythicSyncLog (
    $oplog: bigint!, $startDate: timestamptz!, $sourceIp: String!,
    $tool: String!, $userContext: String!, $command: String!,
    $description: String!, $comments: String!, $operatorName: String!,
    $entry_identifier: String!, $extraFields: jsonb!
) {
    insert_oplogEntry(objects: {
        oplog: $oplog,
        startDate: $startDate,
        sourceIp: $sourceIp,
        tool: $tool,
        userContext: $userContext,
        command: $command,
        description: $description,
        comments: $comments,
        operatorName: $operatorName,
        entryIdentifier: $entry_identifier,
        extraFields: $extraFields
    }) {
        returning {
            id
        }
    }
}
"""

def convert_timestamp(ts_str):
    """Convert LOKI timestamps to GW timestamps"""
    try:
        dt = datetime.strptime(ts_str, "%m-%d-%Y %I:%M%p %Z")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def parse_log_lines(file_path):
    """Regex to find all lines with commands"""
    pattern = re.compile(
        r'<span style="color:#acdff2">\[(.*?)\]</span> '
        r'<span style="color:#ff0000">(.*?)</span>\$ (.*)'
    )

    results = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.match(line.strip())
            if match:
                raw_time, username, command = match.groups()
                converted_time = convert_timestamp(raw_time)
                if converted_time:
                    results.append({
                        "startDate": converted_time,
                        "userContext": username,
                        "command": command,
                        "tool": "LokiC2",
                        "sourceIp": host,
                        "oplog": ghostwriter_oplog_id,
                        "entryIdentifier": f"{username}_{converted_time}_{hash(command)}",
                        "extraFields": {},
                        "description": command
                    })
    return results

def send_logs_to_ghostwriter(entries):
    url = ghostwriter_url.rstrip("/") + "/v1/graphql"
    api_key = ghostwriter_api_key

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    for entry in entries:
        payload = {
            "query": INSERT_QUERY,
            "variables": {
                "oplog": int(entry["oplog"]),
                "startDate": entry["startDate"],
                "sourceIp": entry["sourceIp"],
                "tool": entry["tool"],
                "userContext": entry["userContext"],
                "command": entry["command"],
                "description": entry["description"],
                "comments": entry.get("comments", ""),
                "operatorName": operator,
                "entry_identifier": entry["entryIdentifier"],
                "extraFields": entry["extraFields"]
            }
        }

        response = requests.post(url, headers=headers, json=payload, verify=False)
        if response.status_code != 200 or "errors" in response.json():
            print("Error posting to Ghostwriter:", response.text, file=sys.stderr)
        else:
            print("Successfully posted logs to Ghostwriter")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse and send logs to Ghostwriter.")
    parser.add_argument("input_file", help="Path to the log file")
    args = parser.parse_args()

    parsed_data = parse_log_lines(args.input_file)
    if parsed_data:
        send_logs_to_ghostwriter(parsed_data)
    else:
        print("No valid log entries found.")
