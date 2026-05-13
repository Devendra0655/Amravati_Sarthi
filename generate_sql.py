import pandas as pd

df = pd.read_csv("amravati_businesses.csv")

# drop rows with missing coordinates
df = df.dropna(subset=["lat", "lng"])

# clean up empty strings
df["phone"]         = df["phone"].fillna("").str.strip()
df["opening_hours"] = df["opening_hours"].fillna("").str.strip()
df["address"]       = df["address"].fillna("Amravati").str.strip()

print(f"Clean entries: {len(df)}")
print(df["category"].value_counts().to_string())

# escape single quotes in text fields
def esc(val):
    return str(val).replace("'", "''")

lines = []
lines.append("""
CREATE TABLE IF NOT EXISTS businesses (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(255)  NOT NULL,
    category       VARCHAR(100)  NOT NULL,
    address        TEXT          NOT NULL,
    lat            DOUBLE PRECISION NOT NULL,
    lng            DOUBLE PRECISION NOT NULL,
    phone          VARCHAR(50)   DEFAULT '',
    opening_hours  VARCHAR(255)  DEFAULT '',
    rating         NUMERIC(2,1)  DEFAULT NULL
);
""")

lines.append("INSERT INTO businesses (name, category, address, lat, lng, phone, opening_hours) VALUES")

rows = []
for _, row in df.iterrows():
    rows.append(
        f"('{esc(row['name'])}', '{esc(row['category'])}', "
        f"'{esc(row['address'])}', {row['lat']}, {row['lng']}, "
        f"'{esc(row['phone'])}', '{esc(row['opening_hours'])}')"
    )

lines.append(",\n".join(rows) + ";")

sql = "\n".join(lines)
with open("businesses.sql", "w", encoding="utf-8") as f:
    f.write(sql)

print("\nbusinesses.sql generated successfully!")