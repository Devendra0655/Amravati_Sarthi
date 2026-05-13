import requests
import pandas as pd
import time

AMRAVATI_BBOX = "20.8800,77.7000,20.9800,77.8200"
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"

CATEGORIES = {
    "hospital":   "amenity=hospital",
    "pharmacy":   "amenity=pharmacy",
    "restaurant": "amenity=restaurant",
    "atm":        "amenity=atm",
    "hotel":      "tourism=hotel",
    "bank":       "amenity=bank",
    "clinic":     "amenity=clinic",
    "police":     "amenity=police",
    "college":    "amenity=college",
}

def fetch_category(category_name, osm_tag):
    key, value = osm_tag.split("=")
    query = f"""
    [out:json][timeout:30];
    (
      node["{key}"="{value}"]({AMRAVATI_BBOX});
      way["{key}"="{value}"]({AMRAVATI_BBOX});
    );
    out center;
    """
    resp = requests.get(OVERPASS_URL, params={"data": query}, timeout=30)
    print(f"  Status: {resp.status_code}")
    resp.raise_for_status()

    rows = []
    for el in resp.json().get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or tags.get("name:mr")
        if not name:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lng = el.get("lon") or el.get("center", {}).get("lon")
        rows.append({
            "name":          name,
            "category":      category_name,
            "address":       tags.get("addr:full") or tags.get("addr:street", "Amravati"),
            "lat":           lat,
            "lng":           lng,
            "phone":         tags.get("phone") or tags.get("contact:phone", ""),
            "opening_hours": tags.get("opening_hours", ""),
        })
    return rows

all_rows = []
for cat_name, osm_tag in CATEGORIES.items():
    print(f"Fetching {cat_name}...")
    try:
        rows = fetch_category(cat_name, osm_tag)
        print(f"  Found {len(rows)} entries")
        all_rows.extend(rows)
        time.sleep(2)  # be polite to the server
    except Exception as e:
        print(f"  Failed: {e}")

df = pd.DataFrame(all_rows).drop_duplicates(subset=["name", "lat", "lng"])
df.to_csv("amravati_businesses.csv", index=False)
print(f"\nDone. Total: {len(df)} entries saved to amravati_businesses.csv")