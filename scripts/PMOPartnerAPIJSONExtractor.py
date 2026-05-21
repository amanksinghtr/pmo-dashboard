"""
PMO Partner API - JSON Extractor (v11 - Fix R8 due-date field)
- Filtered to Critical tiering only
- Uses /programs/{id}/projects to build project → program linkage cleanly
- Removes the non-existent program_id field on projects
- FIX (v11): Action due-date is stored as 'target_date' in the API response,
  NOT 'due_date'. The dashboard R8 rule (Actions have due dates) was reading
  a.get('due_date') which always returned None, causing every action to be
  counted as missing a date regardless of its actual value. Fixed in
  build_entity() by normalising the field to 'due_date' on output so the
  dashboard contract stays stable, and the correct source field is read.
Run with: python "PMO Partner API - JSON Extractor.py"
"""

import requests
import json
from datetime import datetime

BASE_URL    = "https://bxd4pvbnhh.execute-api.us-east-1.amazonaws.com/prod"
OUTPUT_FILE = r"/Users/amankumarsingh/Desktop/PMOPartner/pmo_data_export.json"


def get(path, headers, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params)
    r.raise_for_status()
    return r.json()


def clean(value):
    if not isinstance(value, str):
        return value
    return "".join(c for c in value if ord(c) >= 32 or c in "\t\n\r")


def person_str(p):
    if not p:
        return ""
    return clean(p.get("name", "")) if isinstance(p, dict) else clean(str(p))


def fetch_all_projects(headers):
    data = requests.get(
        f"{BASE_URL}/projects",
        headers=headers,
        params={"limit": 1000, "project_tiering": "Critical"}
    )
    if data.status_code == 401:
        return None
    data.raise_for_status()
    return data.json().get("data", [])


def fetch_all_programs(headers):
    data = requests.get(
        f"{BASE_URL}/programs",
        headers=headers,
        params={"limit": 1000, "program_tiering": "Critical"}
    )
    if data.status_code == 401:
        return None
    data.raise_for_status()
    return data.json().get("data", [])


def fetch_program_projects(program_pid, headers):
    """
    Fetch all projects linked to a program.
    Returns a list of project objects (each at minimum has id/uuid and friendly_id).
    """
    try:
        data = get(f"/programs/{program_pid}/projects", headers)
        items = data.get("data", data) if isinstance(data, dict) else data
        return items or []
    except Exception as e:
        print(f"  Warning: could not fetch linked projects for {program_pid}: {e}")
        return []


def fetch_latest_report(pid, entity_type, headers):
    try:
        path = f"/projects/{pid}/reports" if entity_type == "project" else f"/programs/{pid}/reports"
        reports = get(path, headers)
        if isinstance(reports, dict):
            reports = reports.get("data", [])
        if not reports:
            return None
        latest = reports[0]
        report_id = latest.get("id") or latest.get("report_id")
        date = latest.get("created_at") or latest.get("updated_at") or ""
        content = clean(latest.get("content", ""))
        return {
            "report_id": clean(str(report_id)) if report_id else "",
            "date": date[:10] if date else "",
            "content": content,
        }
    except Exception as e:
        print(f"  Warning: could not fetch report for {pid}: {e}")
        return None


def fetch_status_history(pid, entity_type, headers):
    if entity_type != "project":
        return []
    try:
        data = get(
            f"/projects/{pid}/status-history",
            headers,
            params={"days": 365}
        )
        history = data.get("data", data) if isinstance(data, dict) else data
        return history or []
    except Exception as e:
        print(f"  Warning: could not fetch status history for {pid}: {e}")
        return []


def fetch_raaid(pid, entity_type, headers):
    base = f"/projects/{pid}" if entity_type == "project" else f"/programs/{pid}"
    result = {}
    for category in ["risks", "actions", "assumptions", "issues", "dependencies", "decisions", "milestones", "stakeholders"]:
        try:
            data = get(f"{base}/{category}", headers)
            items = data.get("data", data) if isinstance(data, dict) else data
            items = items or []
            # ── R8 FIX ──────────────────────────────────────────────────────
            # The API returns action due-dates under the key 'target_date',
            # not 'due_date'. Normalise here so the rest of the pipeline
            # (dashboard scoring rule R8) can safely call a.get('due_date').
            if category == "actions":
                for action in items:
                    if "due_date" not in action:
                        action["due_date"] = action.get("target_date") or None
            # ────────────────────────────────────────────────────────────────
            result[category] = items
        except Exception as e:
            print(f"  Warning: {category} for {pid}: {e}")
            result[category] = []
    if entity_type == "project":
        try:
            data = get(f"/projects/{pid}/objectives", headers)
            items = data.get("data", data) if isinstance(data, dict) else data
            result["objectives"] = items or []
        except Exception as e:
            print(f"  Warning: objectives for {pid}: {e}")
            result["objectives"] = []
    else:
        result["objectives"] = []
    return result


def build_entity(p, entity_type, headers):
    pid = p.get("friendly_id") or p.get("id")
    manager_key = "project_manager" if entity_type == "project" else "program_manager"
    tiering_key = "project_tiering" if entity_type == "project" else "program_tiering"
    status_key  = "status" if entity_type == "project" else "current_status"

    report         = fetch_latest_report(pid, entity_type, headers)
    status_history = fetch_status_history(pid, entity_type, headers)
    raaid          = fetch_raaid(pid, entity_type, headers)

    return {
        "id":             clean(p.get("friendly_id")),
        "uuid":           clean(p.get("id")),
        "type":           entity_type,
        "name":           clean(p.get("name")),
        "rag_status":     clean(p.get("rag_status")),
        "status_history": status_history,
        "status":         clean(p.get(status_key)),
        "manager":        person_str(p.get(manager_key)),
        "sponsor":        person_str(p.get("sponsor")),
        "start_date":     clean(p.get("start_date")),
        "end_date":       clean(p.get("end_date")),
        "budget":         clean(p.get("budget")),
        "pillar":         clean(p.get("pillar")),
        "tiering":        clean(p.get(tiering_key)),
        "program_id":     "",         # resolved after all entities built
        "program_name":   "",         # resolved after all entities built
        "latest_report":  report,
        "risks":          raaid["risks"],
        "actions":        raaid["actions"],
        "assumptions":    raaid["assumptions"],
        "issues":         raaid["issues"],
        "dependencies":   raaid["dependencies"],
        "decisions":      raaid["decisions"],
        "milestones":     raaid["milestones"],
        "stakeholders":   raaid["stakeholders"],
        "objectives":     raaid["objectives"],
    }


def resolve_program_links(entities, programs, headers):
    """
    For each program, call /programs/{id}/projects to get the list of linked projects.
    Build a map of project UUID → (program friendly_id, program name) and apply to
    each project entity in the entities list.
    
    Note: critical projects may be linked to programs of any tiering, so the program
    may not be in our 'critical programs' entity list. We resolve the friendly_id
    and name directly from the API response.
    """
    proj_uuid_to_prog = {}
    for i, prog in enumerate(programs, 1):
        prog_pid = prog.get("friendly_id") or prog.get("id")
        print(f"  Resolving links for program {i}/{len(programs)}: {prog_pid}", end="\r")
        linked = fetch_program_projects(prog_pid, headers)
        for linked_proj in linked:
            uuid = linked_proj.get("id")
            if uuid:
                proj_uuid_to_prog[uuid] = (
                    clean(prog.get("friendly_id")),
                    clean(prog.get("name")),
                )
    print()
    linked_count = 0
    for e in entities:
        if e["type"] != "project":
            continue
        uuid = e.get("uuid")
        if uuid and uuid in proj_uuid_to_prog:
            e["program_id"], e["program_name"] = proj_uuid_to_prog[uuid]
            linked_count += 1
    return linked_count


def main():
    token = input("Enter your API token: ").strip()
    headers = {"Authorization": f"Bearer {token}"}

    print("Fetching critical projects...")
    projects = fetch_all_projects(headers)
    if projects is None:
        print("Error: Invalid or revoked token.")
        return
    print(f"  Found {len(projects)} critical projects")

    print("Fetching critical programs...")
    programs = fetch_all_programs(headers)
    if programs is None:
        print("Error: Could not fetch programs — check token permissions.")
        programs = []
    else:
        print(f"  Found {len(programs)} critical programs")

    entities = []
    total = len(projects) + len(programs)

    for i, p in enumerate(projects, 1):
        pid = p.get("friendly_id") or p.get("id")
        print(f"  Processing {i}/{total}: {pid}", end="\r")
        entities.append(build_entity(p, "project", headers))

    for i, p in enumerate(programs, len(projects) + 1):
        pid = p.get("friendly_id") or p.get("id")
        print(f"  Processing {i}/{total}: {pid}", end="\r")
        entities.append(build_entity(p, "program", headers))

    print()
    print("Resolving project → program linkage...")
    linked = resolve_program_links(entities, programs, headers)
    print(f"  Resolved program linkage for {linked} of {len(projects)} critical projects")
    print(f"  (Projects with no link may belong to a non-Critical program — to capture those, the script would need to fetch all programs not just critical ones.)")

    output = {
        "generated_at":   datetime.now().isoformat(),
        "tiering_filter": "Critical",
        "project_count":  len(projects),
        "program_count":  len(programs),
        "entities":       entities,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! File saved to: {OUTPUT_FILE}")
    print(f"Total entities: {total}")
    print("Note: status_history and objectives are only available for projects (API limitation)")


if __name__ == "__main__":
    main()