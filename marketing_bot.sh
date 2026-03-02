#!/usr/bin/env bash
# marketing_bot.sh — Trending Product Market Research Bot
#
# Fetches trending product data from Google Trends, Amazon Best Sellers,
# eBay, and TikTok (categories A-Z), then emails a human-readable report
# plus a CSV attachment to the configured recipient.
#
# Usage:
#   ./marketing_bot.sh [OPTIONS]
#
# Options:
#   -e, --email  EMAIL    Recipient address (overrides MARKETING_BOT_EMAIL)
#   -o, --output DIR      Directory for saved reports  (default: /tmp)
#   -h, --help            Show this help and exit
#
# Environment variables (all optional):
#   MARKETING_BOT_EMAIL   Recipient e-mail  (default: eddieguy.2025@gmail.com)
#   EBAY_APP_ID           eBay Finding API App ID — enables eBay trending data
#   RAPIDAPI_KEY          RapidAPI key        — enables TikTok trending data
#   SMTP_HOST             SMTP relay hostname (enables curl-based delivery)
#   SMTP_PORT             SMTP relay port     (default: 587)
#   SMTP_USER             SMTP username
#   SMTP_PASS             SMTP password
#   SMTP_FROM             From address        (default: same as recipient)
#
# Dependencies: curl, awk, sed, grep, base64
#   Optional:   jq (for TikTok/eBay JSON parsing), mail/mailx (system MTA)
#
# When no mail transport is available the reports are written to:
#   ./market_report_YYYY-MM-DD.txt
#   ./market_report_YYYY-MM-DD.csv

set -euo pipefail
IFS=$'\n\t'

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

RECIPIENT="${MARKETING_BOT_EMAIL:-eddieguy.2025@gmail.com}"
OUTPUT_DIR="${MARKETING_BOT_OUTPUT_DIR:-/tmp}"

REPORT_DATE=$(date '+%Y-%m-%d')
REPORT_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')
REPORT_FILE="${OUTPUT_DIR}/market_report_${REPORT_DATE}.txt"
CSV_FILE="${OUTPUT_DIR}/market_report_${REPORT_DATE}.csv"

EBAY_APP_ID="${EBAY_APP_ID:-}"
RAPIDAPI_KEY="${RAPIDAPI_KEY:-}"

SMTP_HOST="${SMTP_HOST:-}"
SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASS="${SMTP_PASS:-}"
SMTP_FROM="${SMTP_FROM:-${RECIPIENT}}"

TMP_DIR=$(mktemp -d)
# shellcheck disable=SC2064
trap 'rm -rf "${TMP_DIR}"' EXIT

# Accumulated data rows: "Source|Rank|Name|Category|Notes"
ROWS_FILE="${TMP_DIR}/rows.tsv"
touch "$ROWS_FILE"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

log()  { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
err()  { printf '[ERROR] %s\n' "$*" >&2; }

require() {
    local missing=()
    for cmd in "$@"; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done
    if (( ${#missing[@]} )); then
        err "Missing required commands: ${missing[*]}"
        err "Please install them and retry."
        exit 1
    fi
}

strip_html() {
    sed 's/<[^>]*>//g' \
    | sed 's/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/"/g; s/&#39;/'"'"'/g; s/&nbsp;/ /g' \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
    | grep -v '^$'
}

csv_quote() {
    # Wrap a value in double-quotes, escaping embedded double-quotes.
    local v="${1//\"/\"\"}"
    printf '"%s"' "$v"
}

append_rows() {
    # append_rows SOURCE CATEGORY
    # Reads product names from stdin, one per line.
    local source="$1" category="$2" rank=1 name
    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        printf '%s\t%s\t%s\t%s\t%s\n' \
            "$source" "$rank" "$name" "$category" "" >> "$ROWS_FILE"
        (( rank++ )) || true
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

fetch_google_trends() {
    log "Fetching Google Trends (daily trending, US)…"
    local url="https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
    local raw="${TMP_DIR}/google_trends.xml"
    if ! curl -fsSL --max-time 20 "$url" -o "$raw" 2>/dev/null; then
        warn "Google Trends: request failed — skipping."
        return
    fi
    # Each trending item has a <title> inside an <item> block.
    # The first <title> is the feed title, so skip it.
    grep -oE '<title>[^<]+</title>' "$raw" \
        | sed 's/<title>//; s/<\/title>//' \
        | tail -n +2 \
        | head -20
}

# Amazon Best Sellers RSS feeds — publicly available, no API key required.
declare -A AMAZON_CATS=(
    [Automotive]="https://www.amazon.com/gp/rss/bestsellers/automotive"
    [Beauty]="https://www.amazon.com/gp/rss/bestsellers/beauty"
    [Books]="https://www.amazon.com/gp/rss/bestsellers/books"
    [Electronics]="https://www.amazon.com/gp/rss/bestsellers/electronics"
    [Fashion]="https://www.amazon.com/gp/rss/bestsellers/apparel"
    [Health]="https://www.amazon.com/gp/rss/bestsellers/hpc"
    [Home]="https://www.amazon.com/gp/rss/bestsellers/home-garden"
    [Kitchen]="https://www.amazon.com/gp/rss/bestsellers/kitchen"
    [Music]="https://www.amazon.com/gp/rss/bestsellers/music"
    [Outdoors]="https://www.amazon.com/gp/rss/bestsellers/outdoor-living"
    [PetSupplies]="https://www.amazon.com/gp/rss/bestsellers/pet-supplies"
    [Sports]="https://www.amazon.com/gp/rss/bestsellers/sporting-goods"
    [Tools]="https://www.amazon.com/gp/rss/bestsellers/hi"
    [Toys]="https://www.amazon.com/gp/rss/bestsellers/toys-and-games"
    [VideoGames]="https://www.amazon.com/gp/rss/bestsellers/videogames"
)

fetch_amazon_category() {
    local cat_name="$1" url="$2"
    local raw="${TMP_DIR}/amz_${cat_name}.xml"
    if ! curl -fsSL --max-time 20 \
            -H 'User-Agent: Mozilla/5.0 (compatible; MarketBot/1.0)' \
            "$url" -o "$raw" 2>/dev/null; then
        warn "Amazon ${cat_name}: request failed — skipping."
        return
    fi
    # Extract titles from <item> blocks
    awk '/<item>/,/<\/item>/' "$raw" \
        | grep -oE '<title>[^<]+</title>' \
        | sed 's/<title>//; s/<\/title>//' \
        | strip_html \
        | head -10
}

fetch_amazon_all() {
    log "Fetching Amazon Best Sellers (A-Z by category)…"
    # Sort categories alphabetically
    local sorted_cats
    mapfile -t sorted_cats < <(printf '%s\n' "${!AMAZON_CATS[@]}" | sort)
    for cat in "${sorted_cats[@]}"; do
        log "  Amazon › ${cat}"
        fetch_amazon_category "$cat" "${AMAZON_CATS[$cat]}" \
            | append_rows "Amazon – ${cat}" "${cat}"
    done
}

fetch_ebay_trending() {
    if [[ -z "$EBAY_APP_ID" ]]; then
        warn "EBAY_APP_ID not set — skipping eBay data."
        warn "  Register free at https://developer.ebay.com/ and export EBAY_APP_ID=<id>"
        return
    fi
    log "Fetching eBay trending items…"
    local base_url="https://svcs.ebay.com/services/search/FindingService/v1"
    local params="OPERATION-NAME=findPopularItems"
    params+="&SERVICE-VERSION=1.0.0"
    params+="&SECURITY-APPNAME=${EBAY_APP_ID}"
    params+="&RESPONSE-DATA-FORMAT=JSON"
    params+="&REST-PAYLOAD"
    params+="&entriesPerPage=20"
    local response="${TMP_DIR}/ebay.json"
    if ! curl -fsSL --max-time 20 \
            "${base_url}?${params}" \
            -o "$response" 2>/dev/null; then
        warn "eBay: request failed — skipping."
        return
    fi
    if ! command -v jq &>/dev/null; then
        warn "jq not found — cannot parse eBay JSON; skipping."
        return
    fi
    jq -r '.findPopularItemsResponse[0].itemRecommendations[0].item[]?.title[0] // empty' \
        "$response" 2>/dev/null | head -20
}

fetch_tiktok_trending() {
    if [[ -z "$RAPIDAPI_KEY" ]]; then
        warn "RAPIDAPI_KEY not set — skipping TikTok data."
        warn "  Subscribe to a TikTok API on https://rapidapi.com/ and export RAPIDAPI_KEY=<key>"
        return
    fi
    log "Fetching TikTok trending products (via RapidAPI)…"
    local response="${TMP_DIR}/tiktok.json"
    # Uses the "tokapi-mobile-version" endpoint available on RapidAPI
    if ! curl -fsSL --max-time 20 \
            -H "X-RapidAPI-Key: ${RAPIDAPI_KEY}" \
            -H "X-RapidAPI-Host: tokapi-mobile-version.p.rapidapi.com" \
            "https://tokapi-mobile-version.p.rapidapi.com/v1/trending/product?count=20&offset=0" \
            -o "$response" 2>/dev/null; then
        warn "TikTok: request failed — skipping."
        return
    fi
    if ! command -v jq &>/dev/null; then
        warn "jq not found — cannot parse TikTok JSON; skipping."
        return
    fi
    jq -r '.product_list[]? | .title // empty' "$response" 2>/dev/null | head -20
}

# ─────────────────────────────────────────────────────────────────────────────
# REPORT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

build_text_report() {
    log "Building human-readable report…"
    {
        printf '%s\n' \
"═══════════════════════════════════════════════════════════════════════" \
"  MARKET RESEARCH REPORT — Trending Products A-Z" \
"  Generated : ${REPORT_TIMESTAMP}" \
"  Recipient : ${RECIPIENT}" \
"═══════════════════════════════════════════════════════════════════════" \
"" \
"This automated report covers trending products sourced from:" \
"  • Google Trends       — daily trending searches in the US" \
"  • Amazon Best Sellers — 15 categories, sorted A-Z" \
"  • eBay Trending Items — requires EBAY_APP_ID env var" \
"  • TikTok Trending     — requires RAPIDAPI_KEY env var" \
""

        local current_source="" rank name category notes
        while IFS=$'\t' read -r source rank name category notes; do
            if [[ "$source" != "$current_source" ]]; then
                [[ -n "$current_source" ]] && printf '\n'
                printf '──────────────────────────────────────────────────────────────────────\n'
                printf '  %s\n\n' "$source"
                current_source="$source"
            fi
            printf '  %3d.  %s\n' "$rank" "$name"
        done < "$ROWS_FILE"

        local total
        total=$(wc -l < "$ROWS_FILE")
        printf '\n%s\n' \
"═══════════════════════════════════════════════════════════════════════" \
"  Total products tracked: ${total}" \
"═══════════════════════════════════════════════════════════════════════" \
"" \
"NOTE: Rankings reflect trending/best-seller positions at the time of" \
"      report generation. For real-time TikTok and eBay data, configure" \
"      the respective API keys (see script header for details)." \
""
    } > "$REPORT_FILE"
}

build_csv() {
    log "Building CSV file…"
    {
        printf 'Source,Rank,Product Name,Category,Notes,Report Date\n'
        while IFS=$'\t' read -r source rank name category notes; do
            printf '%s,%s,%s,%s,%s,%s\n' \
                "$(csv_quote "$source")" \
                "$rank" \
                "$(csv_quote "$name")" \
                "$(csv_quote "$category")" \
                "$(csv_quote "${notes:-}")" \
                "$(csv_quote "$REPORT_DATE")"
        done < "$ROWS_FILE"
    } > "$CSV_FILE"
}

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL DELIVERY
# ─────────────────────────────────────────────────────────────────────────────

send_via_mail() {
    # Try the system mail/mailx command (plain-text body only; CSV saved to disk).
    # Attachment flags vary between implementations so we avoid them for portability.
    command -v mail &>/dev/null || return 1
    log "Sending via system mail (plain-text body; see CSV file on disk)…"
    mail -s "Market Research Report — ${REPORT_DATE}" \
         "$RECIPIENT" < "$REPORT_FILE" 2>/dev/null
}

send_via_curl_smtp() {
    # Use curl as an SMTP client.
    [[ -n "$SMTP_HOST" && -n "$SMTP_USER" && -n "$SMTP_PASS" ]] || return 1
    log "Sending via SMTP (${SMTP_HOST}:${SMTP_PORT})…"

    local boundary="MarketBot_${REPORT_DATE//-/}"
    local mail_file="${TMP_DIR}/email.mime"
    local csv_b64="${TMP_DIR}/csv.b64"

    base64 "$CSV_FILE" > "$csv_b64"

    # Build a minimal MIME multipart message
    {
        printf 'From: Marketing Bot <%s>\r\n' "$SMTP_FROM"
        printf 'To: %s\r\n' "$RECIPIENT"
        printf 'Subject: Market Research Report — %s\r\n' "$REPORT_DATE"
        printf 'MIME-Version: 1.0\r\n'
        printf 'Content-Type: multipart/mixed; boundary="%s"\r\n' "$boundary"
        printf '\r\n'
        printf '--%s\r\n' "$boundary"
        printf 'Content-Type: text/plain; charset=utf-8\r\n'
        printf '\r\n'
        cat "$REPORT_FILE"
        printf '\r\n--%s\r\n' "$boundary"
        printf 'Content-Type: text/csv; charset=utf-8\r\n'
        printf 'Content-Disposition: attachment; filename="market_report_%s.csv"\r\n' "$REPORT_DATE"
        printf 'Content-Transfer-Encoding: base64\r\n'
        printf '\r\n'
        cat "$csv_b64"
        printf '\r\n--%s--\r\n' "$boundary"
    } > "$mail_file"

    # Port 465 → implicit TLS (smtps://); anything else → STARTTLS (smtp://)
    local smtp_scheme="smtp"
    [[ "$SMTP_PORT" == "465" ]] && smtp_scheme="smtps"

    curl --url "${smtp_scheme}://${SMTP_HOST}:${SMTP_PORT}" \
         --ssl-reqd \
         --user "${SMTP_USER}:${SMTP_PASS}" \
         --mail-from "${SMTP_FROM}" \
         --mail-rcpt "${RECIPIENT}" \
         --upload-file "$mail_file" \
         --silent
}

send_email() {
    log "Delivering report to ${RECIPIENT}…"
    # Save reports to current directory (for easy access); skip if already there.
    [[ "$(realpath "$REPORT_FILE")" != "$(realpath "./market_report_${REPORT_DATE}.txt")" ]] \
        && cp "$REPORT_FILE" "./market_report_${REPORT_DATE}.txt"
    [[ "$(realpath "$CSV_FILE")" != "$(realpath "./market_report_${REPORT_DATE}.csv")" ]] \
        && cp "$CSV_FILE"    "./market_report_${REPORT_DATE}.csv"
    if send_via_curl_smtp; then
        log "Report (text + CSV attachment) delivered via SMTP."
        log "Reports also saved locally:"
    elif send_via_mail; then
        log "Report (text body) delivered via system mail."
        log "CSV saved locally (no attachment via system mail):"
    else
        warn "No mail transport available. Configure SMTP_HOST/SMTP_USER/SMTP_PASS"
        warn "or install mailutils to enable email delivery."
        warn "Reports saved to current directory:"
    fi
    log "  Text : ./market_report_${REPORT_DATE}.txt"
    log "  CSV  : ./market_report_${REPORT_DATE}.csv"
}

# ─────────────────────────────────────────────────────────────────────────────
# ARGUMENT PARSING
# ─────────────────────────────────────────────────────────────────────────────

usage() {
    # Print the contiguous comment block at the top of this file (the header).
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} /^[^#]/{exit}' "$0"
}

while (( $# )); do
    case "$1" in
        -e|--email)  RECIPIENT="$2"; shift 2 ;;
        -o|--output) OUTPUT_DIR="$2"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *) err "Unknown option: $1"; usage >&2; exit 1 ;;
    esac
done

# Recalculate paths if OUTPUT_DIR was overridden via flag
REPORT_FILE="${OUTPUT_DIR}/market_report_${REPORT_DATE}.txt"
CSV_FILE="${OUTPUT_DIR}/market_report_${REPORT_DATE}.csv"

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

main() {
    require curl awk sed grep

    log "=== Marketing Bot — Market Research Report ==="
    log "Recipient  : ${RECIPIENT}"
    log "Report date: ${REPORT_DATE}"
    log "Output dir : ${OUTPUT_DIR}"

    # ── Google Trends ──────────────────────────────────────────────────────
    fetch_google_trends | append_rows "Google Trends" "Trending"

    # ── Amazon Best Sellers (A-Z) ──────────────────────────────────────────
    fetch_amazon_all

    # ── eBay Trending ──────────────────────────────────────────────────────
    fetch_ebay_trending | append_rows "eBay Trending" "Marketplace"

    # ── TikTok Trending ────────────────────────────────────────────────────
    fetch_tiktok_trending | append_rows "TikTok Trending" "Social Commerce"

    # ── Build reports ──────────────────────────────────────────────────────
    build_text_report
    build_csv

    # ── Send email ─────────────────────────────────────────────────────────
    send_email

    local total
    total=$(wc -l < "$ROWS_FILE" | tr -d ' ')
    log "Done. Collected ${total} trending product entries."
}

main "$@"
