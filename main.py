import os
import sqlite3
import datetime
import requests
import streamlit as st
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

DB_PATH = "history.db"


def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            searched_at TEXT NOT NULL,
            subreddit TEXT NOT NULL,
            query     TEXT NOT NULL,
            title     TEXT NOT NULL,
            summary   TEXT NOT NULL,
            url       TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def save_to_history(subreddit: str, query: str, title: str, summary: str, url: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO history (searched_at, subreddit, query, title, summary, url) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), subreddit, query, title, summary, url),
    )
    con.commit()
    con.close()


def load_history() -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, searched_at, subreddit, query, title, summary, url FROM history ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return [
        {"id": r[0], "searched_at": r[1], "subreddit": r[2], "query": r[3],
         "title": r[4], "summary": r[5], "url": r[6]}
        for r in rows
    ]


def delete_history_entry(entry_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM history WHERE id = ?", (entry_id,))
    con.commit()
    con.close()


def clear_all_history():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM history")
    con.commit()
    con.close()


def fetch_reddit_posts(subreddit: str, query: str, limit: int = 5) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/search.json?q={query}&restrict_sr=on&sort=top&limit={limit}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        children = data.get("data", {}).get("children", [])
        posts = []
        for child in children:
            post_data = child.get("data", {})
            posts.append({
                "title": post_data.get("title", ""),
                "selftext": post_data.get("selftext", ""),
                "permalink": post_data.get("permalink", ""),
            })
        return posts
    except requests.exceptions.HTTPError as e:
        st.error(f"خطأ في الاتصال بـ Reddit: {e}")
        return []
    except requests.exceptions.ConnectionError:
        st.error("تعذّر الاتصال بـ Reddit. تحقق من اتصالك بالإنترنت.")
        return []
    except requests.exceptions.Timeout:
        st.error("انتهت مهلة الاتصال بـ Reddit. حاول مرة أخرى.")
        return []
    except Exception as e:
        st.error(f"حدث خطأ غير متوقع: {e}")
        return []


def summarize_in_arabic(title: str, selftext: str) -> str:
    if not client:
        return "❌ لم يتم تكوين مفتاح Gemini API. يرجى إضافته في الإعدادات."

    content = title
    if selftext and selftext.strip() and selftext.strip() != "[removed]":
        content = f"{title}\n\n{selftext}"

    prompt = (
        "اقرأ نظرية ريديت التالية، ثم قدم ملخصاً منظماً باللغة العربية يبرز النقاط والأدلة الرئيسية "
        "بأسلوب شيق وواضح. إذا كان النص طويلاً، استخرج الزبدة فقط.\n\n"
        f"النص: {content}"
    )

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"❌ حدث خطأ أثناء التلخيص: {e}"


init_db()

st.set_page_config(
    page_title="ملخّص نظريات ريديت بالعربية",
    page_icon="🌐",
    layout="wide",
)

tab_search, tab_history = st.tabs(["🔍 بحث وتلخيص", "📚 السجل"])

with tab_search:
    st.title("🌐 ملخّص نظريات ريديت بالعربية")
    st.markdown("ابحث عن نظريات ومنشورات ريديت وسيُلخّصها لك الذكاء الاصطناعي باللغة العربية فوراً.")
    st.divider()

    if not GEMINI_API_KEY:
        st.warning(
            "⚠️ لم يتم العثور على مفتاح **GEMINI_API_KEY** في المتغيرات البيئية. "
            "يرجى إضافته لتفعيل ميزة التلخيص.",
            icon="⚠️",
        )

    col1, col2 = st.columns(2)
    with col1:
        subreddit = st.text_input(
            "اسم الـ Subreddit",
            placeholder="مثال: OnePiece أو FromTVEpix",
            help="أدخل اسم المجتمع بدون علامة r/",
        )
    with col2:
        query = st.text_input(
            "كلمة البحث",
            placeholder="مثال: theory أو نظرية",
            help="الكلمات المفتاحية التي تريد البحث عنها",
        )

    num_posts = st.slider("عدد المنشورات", min_value=1, max_value=10, value=5)
    search_clicked = st.button("🔍 بحث وتلخيص", type="primary", use_container_width=True)

    if search_clicked:
        if not subreddit.strip():
            st.error("يرجى إدخال اسم الـ Subreddit.")
        elif not query.strip():
            st.error("يرجى إدخال كلمة البحث.")
        else:
            with st.spinner(f"جارٍ البحث في r/{subreddit} عن «{query}»..."):
                posts = fetch_reddit_posts(subreddit.strip(), query.strip(), num_posts)

            if not posts:
                st.info("لم يتم العثور على أي منشورات. جرّب مجتمعاً أو كلمة بحث مختلفة.")
            else:
                st.success(f"تم العثور على {len(posts)} منشور. جارٍ التلخيص...")
                st.divider()

                for i, post in enumerate(posts, start=1):
                    title = post["title"]
                    selftext = post["selftext"]
                    permalink = post["permalink"]
                    post_url = f"https://www.reddit.com{permalink}"

                    st.markdown(f"### {i}. {title}")

                    with st.spinner(f"يُلخّص المنشور {i}/{len(posts)}..."):
                        summary = summarize_in_arabic(title, selftext)

                    st.markdown(
                        "<div dir='rtl' style='text-align: right; line-height: 1.8;'>"
                        + summary.replace("\n", "<br>")
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    st.markdown(f"🔗 [اقرأ المنشور الأصلي على Reddit]({post_url})")

                    save_to_history(subreddit.strip(), query.strip(), title, summary, post_url)

                    if i < len(posts):
                        st.divider()

    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; font-size: 0.85rem;'>"
        "مدعوم بـ Google Gemini AI · البيانات من Reddit"
        "</div>",
        unsafe_allow_html=True,
    )

with tab_history:
    st.title("📚 سجل الملخّصات السابقة")
    st.markdown("جميع النظريات التي لخّصتها مسبقاً محفوظة هنا.")
    st.divider()

    history = load_history()

    if not history:
        st.info("السجل فارغ حتى الآن. ابدأ بالبحث لتظهر الملخصات هنا.")
    else:
        col_info, col_clear = st.columns([3, 1])
        with col_info:
            st.caption(f"إجمالي المحفوظات: {len(history)}")
        with col_clear:
            if st.button("🗑️ مسح كل السجل", type="secondary", use_container_width=True):
                clear_all_history()
                st.success("تم مسح السجل بالكامل.")
                st.rerun()

        st.divider()

        for entry in history:
            with st.expander(f"📌 {entry['title'][:80]}{'...' if len(entry['title']) > 80 else ''}", expanded=False):
                meta_col1, meta_col2, meta_col3 = st.columns(3)
                with meta_col1:
                    st.caption(f"🗂️ r/{entry['subreddit']}")
                with meta_col2:
                    st.caption(f"🔎 {entry['query']}")
                with meta_col3:
                    st.caption(f"🕐 {entry['searched_at']}")

                st.markdown(
                    "<div dir='rtl' style='text-align: right; line-height: 1.8; padding: 0.5rem 0;'>"
                    + entry["summary"].replace("\n", "<br>")
                    + "</div>",
                    unsafe_allow_html=True,
                )

                link_col, del_col = st.columns([4, 1])
                with link_col:
                    st.markdown(f"🔗 [اقرأ المنشور الأصلي]({entry['url']})")
                with del_col:
                    if st.button("🗑️ حذف", key=f"del_{entry['id']}", use_container_width=True):
                        delete_history_entry(entry["id"])
                        st.rerun()
