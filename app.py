import os
import requests
import streamlit as st
import pandas as pd
from urllib.parse import quote
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# ─── 1) 環境変数読み込み (.env)
load_dotenv(override=True)
API_TOKEN   = os.getenv("BRAWL_API_TOKEN")
PASSWORD    = os.getenv("BLACKLIST_PASSWORD", "Debu")
CREDS_PATH  = os.getenv("GCP_CREDS_JSON_PATH")
SHEET_KEY   = os.getenv("SHEET_KEY")
HEADERS     = {"Authorization": f"Bearer {API_TOKEN}"}

# ─── 2) Google Sheets ユーティリティ
def get_sheet():
    creds = Credentials.from_service_account_file(
        CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_KEY).sheet1

def load_entries_from_sheet():
    sheet = get_sheet()
    recs  = sheet.get_all_records()  # カラム: tag, reasons, note
    return {
        r["tag"]: {
            "reasons": r["reasons"].split(",") if r["reasons"] else [],
            "note":    r["note"]
        }
        for r in recs
    }

def save_entries_to_sheet(entries: dict):
    sheet = get_sheet()
    values = [["tag","reasons","note"]]
    for tag, e in entries.items():
        values.append([tag, ",".join(e["reasons"]), e["note"]])
    sheet.clear()
    sheet.update(values)

# ─── 3) Brawl Stars API 呼び出し
session = requests.Session()
session.trust_env = False  # プロキシ無視

def encode_tag(raw: str) -> str:
    """# を付けて大文字化、%23 にエンコード"""
    t = raw.strip().upper()
    if not t.startswith("#"):
        t = "#" + t
    return quote(t, safe="")

@st.cache_data(ttl=600)
def fetch_player(tag: str) -> dict:
    url = f"https://api.brawlstars.com/v1/players/{encode_tag(tag)}"
    r   = session.get(url, headers=HEADERS)
    if r.status_code in (403, 404):
        return {}
    r.raise_for_status()
    return r.json()

# ─── **修正** 4) normalize_tag を追加
def normalize_tag(raw: str) -> str:
    """新規追加時のタグ正規化 (#付き & 大文字化)"""
    t = raw.strip().upper()
    if not t.startswith("#"):
        t = "#" + t
    return t

# ─── 5) セッションステート初期化
if "entries" not in st.session_state:
    st.session_state.entries = load_entries_from_sheet()

# ─── 6) UI セットアップ
st.set_page_config(page_title="BrawlStars ブラックリスト", layout="centered")
st.title("📋 ブラックリスト一覧")
mode = st.sidebar.selectbox("モード選択", ["全件一覧","検索／編集","新規追加"])

# ─── 7) 全件一覧モード
if mode == "全件一覧":
    entries = st.session_state.entries
    st.markdown(f"**登録人数：{len(entries)}**")

    # 表示用 DataFrame を作成
    df = pd.DataFrame([
        {
            "タグ": tag,
            "名前": fetch_player(tag).get("name", "取得失敗"),
            "理由": ", ".join(e["reasons"])
        }
        for tag, e in entries.items()
    ])
    df_display = df.reset_index().rename(columns={"index":"No"})
    st.table(df_display)

    # No順に詳細エリア
    for _, row in df_display.iterrows():
        no, tag, name = row["No"], row["タグ"], row["名前"]
        e = entries[tag]
        with st.expander(f"{no} — {tag} — {name} の詳細"):
            data = fetch_player(tag)
            if data:
                st.write(f"- **最高トロフィー:** {data['highestTrophies']}")
                st.write(f"- **3v3勝利数:** {data['3vs3Victories']}")
                st.write(f"- **ソロ勝利数:** {data['soloVictories']}")
                st.write(f"- **デュオ勝利数:** {data['duoVictories']}")
            st.write(f"- **備考:** {e['note'] or '–'}")

            pwd = st.text_input("編集パスワード", type="password", key=f"pwd_{tag}")
            if pwd == PASSWORD:
                new_reasons = st.multiselect(
                    "理由",
                    ["代行・買い垢","人格破綻・コミュ障","神","デブ"],
                    default=e["reasons"],
                    key=f"r_{tag}"
                )
                new_note = st.text_area("備考", value=e["note"], key=f"n_{tag}")
                if st.button("保存", key=f"save_{tag}"):
                    st.session_state.entries[tag]["reasons"] = new_reasons
                    st.session_state.entries[tag]["note"]    = new_note
                    save_entries_to_sheet(st.session_state.entries)
                    st.success(f"{tag} を更新しました")
                if st.button("削除", key=f"del_{tag}"):
                    st.session_state.entries.pop(tag)
                    save_entries_to_sheet(st.session_state.entries)
                    st.success(f"{tag} をブラックリストから削除しました")
            else:
                st.caption("※ 編集にはパスワードが必要です")

# ─── 8) 検索／編集モード
elif mode == "検索／編集":
    st.header("🔍 タグ or 名前 で検索")
    q = st.text_input("", placeholder="検索ワードを入力").strip().lower()
    if st.button("検索"):
        hits = []
        for tag, e in st.session_state.entries.items():
            name = fetch_player(tag).get("name","")
            if q in tag.lower() or q in name.lower():
                hits.append((tag, name, e))
        if not hits:
            st.info("ヒットしませんでした。")
        else:
            df2 = pd.DataFrame([
                {"タグ": tag, "名前": name, "理由": ", ".join(e["reasons"])}
                for tag,name,e in hits
            ]).reset_index().rename(columns={"index":"No"})
            st.table(df2)

            for _, row in df2.iterrows():
                no, tag, name = row["No"], row["タグ"], row["名前"]
                e = st.session_state.entries[tag]
                with st.expander(f"{no} — {tag} — {name} の詳細"):
                    data = fetch_player(tag)
                    if data:
                        st.write(f"- **最高トロフィー:** {data['highestTrophies']}")
                        st.write(f"- **3v3勝利数:** {data['3vs3Victories']}")
                        st.write(f"- **ソロ勝利数:** {data['soloVictories']}")
                        st.write(f"- **デュオ勝利数:** {data['duoVictories']}")
                    st.write(f"- **備考:** {e['note'] or '–'}")

                    pwd = st.text_input(
                        "編集パスワード", type="password", key=f"spwd_{tag}"
                    )
                    if pwd == PASSWORD:
                        new_reasons = st.multiselect(
                            "理由",
                            ["代行・買い垢","人格破綻・コミュ障","神","デブ"],
                            default=e["reasons"],
                            key=f"s_r_{tag}"
                        )
                        new_note = st.text_area(
                            "備考", value=e["note"], key=f"s_n_{tag}"
                        )
                        if st.button("保存", key=f"s_save_{tag}"):
                            st.session_state.entries[tag]["reasons"] = new_reasons
                            st.session_state.entries[tag]["note"]    = new_note
                            save_entries_to_sheet(st.session_state.entries)
                            st.success(f"{tag} を更新しました")
                        if st.button("削除", key=f"s_del_{tag}"):
                            st.session_state.entries.pop(tag)
                            save_entries_to_sheet(st.session_state.entries)
                            st.success(f"{tag} を削除しました")
                    else:
                        st.caption("※ 編集にはパスワードが必要です")

# ─── 9) 新規追加モード
else:
    st.header("➕ 新規追加")
    pwd = st.text_input("パスワード", type="password")
    if pwd != PASSWORD:
        st.error("パスワードが違います")
    else:
        with st.form("add_form"):
            raw = st.text_input("プレイヤータグ (#なし可)").strip()
            if st.form_submit_button("名前取得"):
                info = fetch_player(raw)
                if not info:
                    st.error("タグが見つかりません")
                else:
                    st.success(f"{info.get('tag')} → `{info.get('name')}` さん")
            reasons = st.multiselect(
                "理由",
                ["代行・買い垢","人格破綻・コミュ障","神","デブ"]
            )
            note = st.text_area("備考 (任意)")

            if st.form_submit_button("追加"):
                tag = normalize_tag(raw)
                info = fetch_player(tag)
                if not tag or not reasons:
                    st.error("タグと理由は必須です")
                elif not info:
                    st.error("有効なタグを入力してください")
                else:
                    st.session_state.entries[tag] = {
                        "reasons": reasons,
                        "note":    note
                    }
                    save_entries_to_sheet(st.session_state.entries)
                    st.success(f"{tag} を追加しました：{info.get('name')}")
