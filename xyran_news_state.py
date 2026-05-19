import json
import os


def load_news_state(state_path):
    if not os.path.exists(state_path):
        return [], None, 1, []

    try:
        with open(state_path, "r", encoding="utf-8") as file_obj:
            state = json.load(file_obj)
        return (
            state.get("last_news_titles", []),
            state.get("last_news_query_signature"),
            int(state.get("last_news_page", 1)),
            state.get("last_news_articles", []),
        )
    except Exception:
        return [], None, 1, []


def save_news_state(state_path, last_news_titles, last_news_query_signature, last_news_page, last_news_articles):
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as file_obj:
            json.dump(
                {
                    "last_news_titles": last_news_titles,
                    "last_news_query_signature": last_news_query_signature,
                    "last_news_page": last_news_page,
                    "last_news_articles": last_news_articles,
                },
                file_obj,
                ensure_ascii=True,
                indent=2,
            )
    except Exception:
        pass
