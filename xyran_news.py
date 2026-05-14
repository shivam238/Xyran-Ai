import json
import urllib.error
import urllib.parse
import urllib.request

from groq import RateLimitError

from xyran_input_utils import (
    extract_news_selection_index,
    get_news_query_params,
    is_more_news_request,
)
from xyran_news_state import load_news_state as read_news_state, save_news_state as write_news_state


class NewsManager:
    def __init__(
        self,
        *,
        news_api_key,
        news_api_url,
        news_state_path,
        model,
        client,
        call_fallback_chat,
        has_fallback_provider,
    ):
        self.news_api_key = news_api_key
        self.news_api_url = news_api_url
        self.news_state_path = news_state_path
        self.model = model
        self.client = client
        self.call_fallback_chat = call_fallback_chat
        self.has_fallback_provider = has_fallback_provider
        self.last_news_titles = []
        self.last_news_query_signature = None
        self.last_news_page = 1
        self.last_news_articles = []

    def load_state(self):
        (
            self.last_news_titles,
            self.last_news_query_signature,
            self.last_news_page,
            self.last_news_articles,
        ) = read_news_state(self.news_state_path)

    def save_state(self):
        write_news_state(
            self.news_state_path,
            self.last_news_titles,
            self.last_news_query_signature,
            self.last_news_page,
            self.last_news_articles,
        )

    def summarize_article(self, user_input):
        if not self.last_news_articles:
            return "Pehle `news` chalao, phir main selected article ka summary de dunga."

        index = extract_news_selection_index(user_input, len(self.last_news_articles))
        if index is None or not (0 <= index < len(self.last_news_articles)):
            return "Kaunsi news chahiye woh clear nahi hua. Jaise `1 ka summary` ya `dusri news explain` bolo."

        article = self.last_news_articles[index]
        title = article.get("title", "Untitled")
        source = article.get("source", "Unknown source")
        description = article.get("description", "")
        content = article.get("content", "")
        url = article.get("url", "")

        info_parts = [
            f"Title: {title}",
            f"Source: {source}",
        ]
        if description:
            info_parts.append(f"Description: {description}")
        if content:
            info_parts.append(f"Content snippet: {content}")
        if url:
            info_parts.append(f"URL: {url}")
        article_context = "\n".join(info_parts)

        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize news in short Hinglish. Keep it factual and concise. "
                    "If details are limited, say that clearly. "
                    "Return ONLY plain text, no JSON."
                )
            },
            {
                "role": "user",
                "content": (
                    "Is news article ko 3 short lines mein samjhao. "
                    "Line 1: kya hua. Line 2: kyu matter karta hai. "
                    "Line 3: agar context limited ho to mention karo.\n\n"
                    f"{article_context}"
                )
            }
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=180
            )
            reply = response.choices[0].message.content.strip()
            return f"{index + 1}. {title} - {source}\n{reply}"
        except RateLimitError:
            if self.has_fallback_provider():
                try:
                    reply = self.call_fallback_chat(messages, self.model, temperature=0.2, max_tokens=180)
                    return f"{index + 1}. {title} - {source}\n{reply}"
                except Exception:
                    pass
            return "Abhi summary API limit hit ho gayi hai. Thodi der baad phir try karo."
        except Exception as exc:
            return f"Summary nahi bana paya: {exc}"

    def fetch_headlines(self, user_input):
        if not self.news_api_key:
            return "NEWS_API_KEY configured nahi hai. `.env` mein add karo."

        def request_news(params):
            query_string = urllib.parse.urlencode(params)
            request = urllib.request.Request(
                f"{self.news_api_url}?{query_string}",
                headers={"X-Api-Key": self.news_api_key},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))

        params = get_news_query_params(user_input)
        is_more_request = is_more_news_request(user_input, bool(self.last_news_query_signature))
        default_params = {"country": "in", "pageSize": "5"}
        if is_more_request and params == default_params and self.last_news_query_signature:
            try:
                params = json.loads(self.last_news_query_signature)
            except Exception:
                pass
        query_signature = json.dumps(params, sort_keys=True)
        target_page = 1

        if is_more_request and self.last_news_query_signature == query_signature:
            target_page = self.last_news_page + 1
            params["page"] = str(target_page)
        else:
            params["page"] = "1"

        fallback_params_list = [params]

        if "q" in params and not is_more_request:
            without_q = dict(params)
            without_q.pop("q", None)
            fallback_params_list.append(without_q)

        if params.get("country") != "us" and not is_more_request:
            us_fallback = dict(params)
            us_fallback["country"] = "us"
            us_fallback.pop("q", None)
            fallback_params_list.append(us_fallback)

        generic_fallback = {"country": "us", "pageSize": "5", "page": str(target_page)}
        if not is_more_request and generic_fallback not in fallback_params_list:
            fallback_params_list.append(generic_fallback)

        articles = []
        last_error = None
        for attempt_params in fallback_params_list:
            try:
                body = request_news(attempt_params)
            except urllib.error.HTTPError as exc:
                try:
                    error_body = json.loads(exc.read().decode("utf-8"))
                    last_error = f"News API error: {error_body.get('message', str(exc))}"
                except Exception:
                    last_error = f"News API error: {exc}"
                continue
            except Exception as exc:
                last_error = f"News fetch nahi ho payi: {exc}"
                continue

            fetched_articles = body.get("articles", [])
            if self.last_news_titles:
                filtered_articles = [
                    article for article in fetched_articles
                    if article.get("title") not in self.last_news_titles
                ]
            else:
                filtered_articles = fetched_articles

            articles = filtered_articles[:5] if filtered_articles else fetched_articles[:5]
            if articles:
                self.last_news_query_signature = json.dumps(
                    {key: value for key, value in attempt_params.items() if key != "page"},
                    sort_keys=True
                )
                try:
                    self.last_news_page = int(attempt_params.get("page", "1"))
                except ValueError:
                    self.last_news_page = 1
                self.last_news_titles = [article.get("title") for article in articles if article.get("title")]
                self.last_news_articles = [
                    {
                        "title": article.get("title", ""),
                        "source": article.get("source", {}).get("name", "Unknown source"),
                        "description": article.get("description", "") or "",
                        "content": article.get("content", "") or "",
                        "url": article.get("url", "") or "",
                    }
                    for article in articles
                ]
                self.save_state()
                break

        if not articles:
            if last_error:
                return last_error
            if is_more_request:
                return "Aur fresh news nahi mili. Nayi category ya country try karo."
            return "Koi news headlines nahi mili."

        lines = []
        for index, article in enumerate(articles, start=1):
            title = article.get("title", "Untitled")
            source = article.get("source", {}).get("name", "Unknown source")
            lines.append(f"{index}. {title} - {source}")
        return "\n".join(lines)
