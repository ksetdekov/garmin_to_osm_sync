from pathlib import Path

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT = 54
TOP = 742
LINE = 14


def esc(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_content_stream() -> str:
    y = TOP
    parts = []

    def line(text: str, size: int = 11, x: int = LEFT):
        nonlocal y
        parts.append(f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm ({esc(text)}) Tj ET")
        y -= LINE if size <= 11 else 18

    line("Garmin to OSM Sync - One-Page App Summary", 16)
    y -= 4

    line("What it is", 12)
    line("A Python CLI that syncs Garmin Connect activities to OpenStreetMap as GPX traces.")
    line("It uses OSM OAuth2 tokens and a local SQLite record to prevent duplicate uploads.")
    y -= 4

    line("Who it is for", 12)
    line("Primary persona: individual athletes/mappers using Garmin Connect who want OSM trace upload automation.")
    y -= 4

    line("What it does", 12)
    bullets = [
        "- Loads Garmin and OSM settings from .env (credentials, OAuth client, behavior flags).",
        "- Runs browser-based OSM OAuth2 authorization and stores tokens in tokens.json.",
        "- Refreshes expired OSM access tokens automatically via refresh_token.",
        "- Logs into Garmin Connect and fetches recent activities (MAX_ACTIVITIES).",
        "- Downloads each new activity GPX into downloads/ for upload processing.",
        "- Uploads GPX files to OSM /api/0.6/gpx/create with bearer authentication.",
        "- Records processed activity IDs in data.db (processed_activities) to avoid re-uploads.",
    ]
    for b in bullets:
        line(b)
    y -= 4

    line("How it works (repo-evidence architecture)", 12)
    arch = [
        "Components: main.py orchestrator; OAuth callback HTTP server; SQLite state store.",
        "Services: Garmin Connect API (garminconnect lib), OSM OAuth2/token and GPX upload APIs.",
        "Data flow: .env -> authorize/refresh -> fetch Garmin activities -> download GPX",
        "           -> upload to OSM -> mark activity as processed in data.db -> delete temp GPX.",
        "Not found in repo: packaged daemon/service deployment configuration.",
    ]
    for a in arch:
        line(a)
    y -= 4

    line("How to run (minimal)", 12)
    run_steps = [
        "1. cp env_example .env and fill GARMIN_EMAIL, GARMIN_PASSWORD, OSM_CLIENT_ID,",
        "   OSM_CLIENT_SECRET, REDIRECT_URI (README).",
        "2. python -m venv .venv && source .venv/bin/activate",
        "3. pip install -r requirements.txt",
        "4. python main.py",
        "5. First run: approve OSM OAuth in browser; tokens are saved to tokens.json.",
    ]
    for s in run_steps:
        line(s)

    return "\n".join(parts) + "\n"


def make_pdf(content_stream: str) -> bytes:
    content_bytes = content_stream.encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n".encode("ascii")
    )
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objects.append(
        f"5 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n".encode("ascii")
        + content_bytes
        + b"endstream\nendobj\n"
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    out.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def main():
    output = Path("output/pdf/garmin_to_osm_sync_summary.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    content = build_content_stream()
    output.write_bytes(make_pdf(content))
    print(output.resolve())


if __name__ == "__main__":
    main()
