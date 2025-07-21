import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import openai

openai.api_key = st.secrets.get("openai_api_key", "DEIN_OPENAI_API_KEY")
BASE_URL = "https://www.fernsehserien.de"

@st.cache_data
def scrape_episoden_data(series_slug):
    url = f"{BASE_URL}/{series_slug}/episodenguide"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    episodes = soup.find_all("a", itemtype="http://schema.org/TVEpisode")
    data = []
    for ep in episodes:
        href = ep.get("href")
        full_url = BASE_URL + href if href.startswith("/") else href
        title_attr = ep.get("title", "")
        season_episode = title_attr.split(" ")[0] if title_attr else ""
        title_text = title_attr[len(season_episode):].strip() if title_attr else ""
        name_tag = ep.find("span", itemprop="name")
        episode_name = name_tag.get_text(strip=True) if name_tag else ""
        date_cell = ep.find_all("div", role="cell")[-3] if ep.find_all("div", role="cell") else None
        air_date = date_cell.get_text(strip=True) if date_cell else ""
        data.append({
            "Titel": episode_name,
            "Staffel_Episode": season_episode,
            "URL": full_url,
            "Erstausstrahlung": air_date
        })
    df = pd.DataFrame(data)
    df[['Staffel', 'Episode']] = df['Staffel_Episode'].str.split('.', expand=True)
    df['Staffel'] = pd.to_numeric(df['Staffel'], errors='coerce').astype('Int64')
    df['Episode'] = pd.to_numeric(df['Episode'], errors='coerce').astype('Int64')
    return df

def extract_episode_content(url):
    try:
        time.sleep(0.5)
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "html.parser")
        content_div = soup.find("div", class_="episode-output-inhalt-inner")
        return content_div.get_text(strip=True) if content_div else "Inhalt nicht gefunden"
    except Exception as e:
        return f"Fehler: {str(e)}"

def get_season_summary(season_plot_texts, model="gpt-4o"):
    full_text = "\n\n---\n\n".join(season_plot_texts)
    prompt = (
        "Fasse die folgenden Episodenbeschreibungen zu einer kompakten Staffelzusammenfassung (100–150 Wörter) zusammen:\n\n"
        f'"{full_text}"'
    )
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent, der Serieninhalte zusammenfasst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Fehler bei der API-Anfrage: {str(e)}"

# ------------------ STREAMLIT APP ------------------

st.title("📺 Serien-Tool: Episodenguide & Zusammenfassung")

series_slug = st.text_input("🔍 Serien-Slug von fernsehserien.de (z. B. 'sloborn'):")

model = st.selectbox("💡 OpenAI Modell wählen:", ["gpt-3.5-turbo", "gpt-4", "gpt-4o"], index=2)

if series_slug:
    if st.button("🔄 Episoden laden"):
        with st.spinner("Scraping läuft..."):
            df = scrape_episoden_data(series_slug)
            st.session_state["df"] = df
        st.success(f"{len(df)} Episoden gefunden.")
        st.dataframe(df)

    if "df" in st.session_state:
        df = st.session_state["df"]

        if st.button("📥 Inhalte extrahieren"):
            inhalte = []
            progress = st.progress(0)
            for i, url in enumerate(df["URL"]):
                inhalt = extract_episode_content(url)
                inhalte.append(inhalt)
                progress.progress((i + 1) / len(df))
            df["Inhalt"] = inhalte
            st.success("Episodeninhalte geladen.")
            st.dataframe(df[["Staffel", "Episode", "Titel", "Inhalt"]])

        if "Inhalt" in df.columns:
            mögliche_staffeln = df["Staffel"].dropna().unique().astype(int)
            gewählte_staffeln = st.multiselect("🎯 Wähle Staffeln für Zusammenfassung:", mögliche_staffeln.tolist(), default=mögliche_staffeln.tolist())

            if st.button("📝 Staffelzusammenfassungen erstellen"):
                summaries = {}
                for season in gewählte_staffeln:
                    group = df[df["Staffel"] == season]
                    st.write(f"🔹 Staffel {season}: wird verarbeitet...")
                    contents = group["Inhalt"].dropna().tolist()
                    summary = get_season_summary(contents, model=model) if contents else "Keine Inhalte."
                    summaries[season] = summary
                    st.markdown(f"**Staffel {season}:** {summary}")
                df["Staffelzusammenfassung"] = df["Staffel"].map(summaries)

        if st.button("📤 Ergebnisse als Excel herunterladen"):
            df.to_excel(f"{series_slug}_episoden.xlsx", index=False)
            st.success("Excel-Datei gespeichert.")

