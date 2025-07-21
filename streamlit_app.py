#%%
print("Hallo Welt")
# %%
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from tqdm.auto import tqdm

# Deine Ziel-URL
BASE_URL = "https://www.fernsehserien.de"  # Basis-URL, wenn die Links relativ sind
EPISODENLISTE_URL = "https://www.fernsehserien.de/sloborn/episodenguide"  # Anpassen

# HTML abrufen
response = requests.get(EPISODENLISTE_URL)
soup = BeautifulSoup(response.content, "html.parser")

# Alle Episoden-Container finden
episodes = soup.find_all("a", itemtype="http://schema.org/TVEpisode")

# Daten extrahieren
data = []
for ep in episodes:
    href = ep.get("href")
    full_url = BASE_URL + href if href.startswith("/") else href
    title_attr = ep.get("title", "")
    
    # Staffel- und Episodennummer aus dem Titelattribut extrahieren
    season_episode = ""
    if title_attr:
        season_episode = title_attr.split(" ")[0]  # z.B. "1.01"
        title_text = title_attr[len(season_episode):].strip()  # z.B. "Heimweh"
    else:
        title_text = ep.find("span", itemprop="name").get_text(strip=True)

    # Episodentitel
    name_tag = ep.find("span", itemprop="name")
    episode_name = name_tag.get_text(strip=True) if name_tag else ""

    # Ausstrahlungsdatum (ZDF)
    date_cell = ep.find_all("div", role="cell")[-3]  # Vorletztes Datumsfeld
    air_date = date_cell.get_text(strip=True) if date_cell else ""

    data.append({
        "Titel": episode_name,
        "Staffel_Episode": season_episode,
        "URL": full_url,
        "Erstausstrahlung": air_date
    })

# In Tabelle speichern
df = pd.DataFrame(data)
print(df.head())

# Optional: Als CSV speichern
df.to_csv("episoden.csv", index=False)

#%%
# Neue Spalten für Staffel und Episode erstellen
df[['Staffel', 'Episode']] = df['Staffel_Episode'].str.split('.', expand=True)

# Datentypen in Zahlen umwandeln (Integer)
df['Staffel'] = pd.to_numeric(df['Staffel'], errors='coerce').astype('Int64')
df['Episode'] = pd.to_numeric(df['Episode'], errors='coerce').astype('Int64')


# %%
df

#%%
df.iloc[0].URL


#%%

import time
from tqdm.auto import tqdm

def extract_episode_content(url):
    """
    Extrahiert den Inhalt aus dem DIV-Element mit der Klasse 'episode-output-inhalt-inner'
    und wartet kurz, um den Server nicht zu überlasten.
    """
    try:
        time.sleep(0.5)  # Pause von 0.5 Sekunden vor jeder Anfrage
        response = requests.get(url)
        response.raise_for_status()  # Wirft eine Exception bei HTTP-Fehlern
        
        soup = BeautifulSoup(response.content, "html.parser")
        content_div = soup.find("div", class_="episode-output-inhalt-inner")
        
        if content_div:
            return content_div.get_text(strip=True)
        else:
            return "Inhalt nicht gefunden"
            
    except requests.RequestException as e:
        return f"Fehler beim Abrufen der URL: {str(e)}"
    except Exception as e:
        return f"Fehler beim Parsen: {str(e)}"

# Initialisiert tqdm für die Nutzung mit pandas
# Initialisiert tqdm für die Nutzung mit pandas
tqdm.pandas(desc="Extrahiere Episodeninhalte")

# .progress_apply statt .apply verwenden, um den Fortschrittsbalken anzuzeigen
df['Inhalt'] = df['URL'].progress_apply(extract_episode_content)
# %%
df
# %%
import openai

openai.api_key = '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'

# %%



def get_season_summary(season_plot_texts, model="gpt-4o-mini"):
    """
    Sendet die kombinierten Episodeninhalte einer Staffel an die OpenAI API
    und bittet um eine Zusammenfassung.
    """
    # Wir erstellen einen langen Text aus allen Episodeninhalten
    full_text = "\n\n---\n\n".join(season_plot_texts)
    
    # Wir erstellen einen klaren Prompt für die KI
    prompt = (
        "Du bist ein Experte für Serien. Fasse die folgenden Beschreibungen von mehreren Episoden einer Serienstaffel "
        "zu einer prägnanten und gut lesbaren Staffelzusammenfassung von etwa 100-150 Wörtern zusammen. "
        "Konzentriere dich auf die wichtigsten Handlungsstränge und Charakterentwicklungen der Staffel.\n\n"
        "Hier sind die Episodenbeschreibungen:\n\n"
        f'"{full_text}"'
    )
    
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent, der Texte zusammenfasst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        summary = response.choices[0].message.content
        return summary.strip()
    except Exception as e:
        # Hinweis auf Token-Limit: Wenn der Text zu lang ist, schlägt die API fehl.
        if "maximum context length" in str(e):
            return "Fehler: Der Text für diese Staffel ist zu lang für das KI-Modell. Eine Zusammenfassung ist nicht möglich."
        return f"Fehler bei der API-Anfrage: {str(e)}"

# --- Hauptlogik ---
# 1. Nach Staffel gruppieren und Inhalte sammeln
# Wir erstellen ein Dictionary, um für jede Staffel die Zusammenfassung zu speichern
season_summaries = {}

# Wir verwenden tqdm für eine Fortschrittsanzeige, da dies dauern kann
for season, group in tqdm(df.groupby('Staffel'), desc="Erstelle Staffelzusammenfassungen"):
    # Ignoriere Staffeln mit Nummer 0 oder NaN-Werten
    if pd.isna(season) or season == 0:
        continue
        
    print(f"\nVerarbeite Staffel {season}...")
    
    # Inhalte der Episoden dieser Staffel sammeln
    episode_contents = group['Inhalt'].dropna().tolist()
    
    if not episode_contents:
        summary = "Keine Inhalte für eine Zusammenfassung vorhanden."
    else:
        summary = get_season_summary(episode_contents)
        
    season_summaries[season] = summary
    print(f"Zusammenfassung für Staffel {season} erstellt.")

# 2. Die Zusammenfassungen dem ursprünglichen DataFrame zuordnen
df['Staffelzusammenfassung'] = df['Staffel'].map(season_summaries)

# Anzeigen der Ergebnisse (nur relevante Spalten zur Übersicht)
print("\nFertig! Hier ist ein Auszug aus dem Ergebnis:")
print(df[['Staffel', 'Titel', 'Staffelzusammenfassung']].head())

# Optional: Den gesamten DataFrame mit der neuen Spalte anzeigen
# df
# %%
df.iloc[0].Staffelzusammenfassung
# %%
df.to_excel('sloborn.xlsx')

# %%
df
# %%
