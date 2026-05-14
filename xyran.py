import os
import json
import re
import shutil
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from groq import Groq, RateLimitError
from config import GROQ_API_KEY, MODEL, AI_NAME, USER_NAME, NEWS_API_KEY
from vision import analyze_screen, take_screenshot
import base64
from xyran_app_utils import (
    resolve_app_launch,
    save_screenshot_copy,
    smart_open_browser,
    smart_open_website,
    smart_open_youtube,
)
from xyran_command_utils import command_failed, run_command
from xyran_input_utils import (
    extract_news_selection_index,
    extract_python_code_request,
    extract_explicit_website_target,
    extract_text_to_write,
    get_editor_open_command,
    get_local_joke,
    get_local_smalltalk_reply,
    get_news_query_params,
    get_available_text_editor,
    humanize_wait_time,
    is_acknowledgement,
    is_ambiguous_short_followup,
    is_api_status_query,
    is_app_launch_request,
    is_browser_open_request,
    is_explicit_website_request,
    is_files_open_request,
    is_greeting,
    is_ambiguous_open_request,
    is_joke_request,
    is_more_news_request,
    is_news_request,
    is_news_summary_request,
    is_open_youtube_request,
    is_python_file_request,
    is_rate_limit_time_query,
    is_screenshot_request,
    is_text_editor_request,
    is_vision_followup,
    should_use_vision,
    wants_to_show_screenshot,
)
from xyran_news_state import load_news_state as read_news_state, save_news_state as write_news_state
from xyran_prompts import build_system_prompt, build_vision_system_prompt

try:
    import pyjokes
except Exception:
    pyjokes = None

client = Groq(api_key=GROQ_API_KEY)
conversation_history = []
last_input_used_vision = False
vision_followup_turns_left = 0
last_screenshot_path = None
last_editor_file_path = None
last_created_code_file = None
last_rate_limit_wait_text = None
last_provider_used = "groq"
last_browser_action = {"target": None, "time": 0.0}
last_news_titles = []
last_news_query_signature = None
last_news_page = 1
last_news_articles = []

FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", "").strip()
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "").strip()
FALLBACK_BASE_URL = os.environ.get(
    "FALLBACK_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions"
).strip()
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"
NEWS_STATE_PATH = os.path.join(
    os.path.expanduser("~"),
    ".local",
    "state",
    AI_NAME.lower(),
    "news_state.json",
)

SYSTEM_PROMPT = build_system_prompt(AI_NAME, USER_NAME)
VISION_SYSTEM_PROMPT = build_vision_system_prompt(AI_NAME)


def has_fallback_provider():
    return bool(FALLBACK_API_KEY and FALLBACK_MODEL and FALLBACK_BASE_URL)


def call_fallback_chat(messages, model, temperature=0.2, max_tokens=600):
    payload = {
        "model": FALLBACK_MODEL or model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        FALLBACK_BASE_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FALLBACK_API_KEY}",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def summarize_output(output):
    """Long command output ko AI se 1-2 line mein summarize karao."""
    try:
        followup = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        'Summarize this command output in 1-2 lines in Hinglish. '
                        'Only show what matters to the user (e.g. battery %, charging state, disk space, RAM). '
                        'Return ONLY JSON: {"action": "answer", "message": "summary here"}'
                    )
                },
                {"role": "user", "content": output}
            ],
            max_tokens=120
        )
        summary_reply = followup.choices[0].message.content.strip()
        summary_data = clean_json(summary_reply)
        s = json.loads(summary_data)
        return s.get("message", output[:200])
    except Exception:
        return output[:200]


def load_news_state():
    global last_news_titles, last_news_query_signature, last_news_page, last_news_articles
    (
        last_news_titles,
        last_news_query_signature,
        last_news_page,
        last_news_articles,
    ) = read_news_state(NEWS_STATE_PATH)


def save_news_state():
    write_news_state(
        NEWS_STATE_PATH,
        last_news_titles,
        last_news_query_signature,
        last_news_page,
        last_news_articles,
    )


def prepare_editor_file(initial_text=None):
    global last_editor_file_path
    folder = os.path.expanduser(f"~/Documents/{AI_NAME}")
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = os.path.join(folder, f"note-{timestamp}.txt")
    with open(file_path, "w", encoding="utf-8") as file_obj:
        if initial_text:
            file_obj.write(initial_text)
            if not initial_text.endswith("\n"):
                file_obj.write("\n")
    last_editor_file_path = file_path
    return file_path


def prepare_python_file(initial_code=None):
    global last_created_code_file
    folder = os.path.expanduser(f"~/Documents/{AI_NAME}")
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = os.path.join(folder, f"script-{timestamp}.py")
    with open(file_path, "w", encoding="utf-8") as file_obj:
        if initial_code:
            file_obj.write(initial_code)
            if not initial_code.endswith("\n"):
                file_obj.write("\n")
    last_created_code_file = file_path
    return file_path


def summarize_news_article(user_input):
    if not last_news_articles:
        return "Pehle `news` chalao, phir main selected article ka summary de dunga."

    index = extract_news_selection_index(user_input, len(last_news_articles))
    if index is None or not (0 <= index < len(last_news_articles)):
        return "Kaunsi news chahiye woh clear nahi hua. Jaise `1 ka summary` ya `dusri news explain` bolo."

    article = last_news_articles[index]
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
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=180
        )
        reply = response.choices[0].message.content.strip()
        return f"{index + 1}. {title} - {source}\n{reply}"
    except RateLimitError:
        if has_fallback_provider():
            try:
                reply = call_fallback_chat(messages, MODEL, temperature=0.2, max_tokens=180)
                return f"{index + 1}. {title} - {source}\n{reply}"
            except Exception:
                pass
        return "Abhi summary API limit hit ho gayi hai. Thodi der baad phir try karo."
    except Exception as e:
        return f"Summary nahi bana paya: {e}"


def fetch_news_headlines(user_input):
    global last_news_titles, last_news_query_signature, last_news_page, last_news_articles
    if not NEWS_API_KEY:
        return "NEWS_API_KEY configured nahi hai. `.env` mein add karo."

    def request_news(params):
        query_string = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{NEWS_API_URL}?{query_string}",
            headers={"X-Api-Key": NEWS_API_KEY},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    params = get_news_query_params(user_input)
    is_more_request = is_more_news_request(user_input, bool(last_news_query_signature))
    default_params = {"country": "in", "pageSize": "5"}
    if is_more_request and params == default_params and last_news_query_signature:
        try:
            params = json.loads(last_news_query_signature)
        except Exception:
            pass
    query_signature = json.dumps(params, sort_keys=True)
    target_page = 1

    if is_more_request and last_news_query_signature == query_signature:
        target_page = last_news_page + 1
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
        except urllib.error.HTTPError as e:
            try:
                error_body = json.loads(e.read().decode("utf-8"))
                last_error = f"News API error: {error_body.get('message', str(e))}"
            except Exception:
                last_error = f"News API error: {e}"
            continue
        except Exception as e:
            last_error = f"News fetch nahi ho payi: {e}"
            continue

        fetched_articles = body.get("articles", [])
        if last_news_titles:
            filtered_articles = [
                article for article in fetched_articles
                if article.get("title") not in last_news_titles
            ]
        else:
            filtered_articles = fetched_articles

        articles = filtered_articles[:5] if filtered_articles else fetched_articles[:5]
        if articles:
            last_news_query_signature = json.dumps(
                {k: v for k, v in attempt_params.items() if k != "page"},
                sort_keys=True
            )
            try:
                last_news_page = int(attempt_params.get("page", "1"))
            except ValueError:
                last_news_page = 1
            last_news_titles = [article.get("title") for article in articles if article.get("title")]
            last_news_articles = [
                {
                    "title": article.get("title", ""),
                    "source": article.get("source", {}).get("name", "Unknown source"),
                    "description": article.get("description", "") or "",
                    "content": article.get("content", "") or "",
                    "url": article.get("url", "") or "",
                }
                for article in articles
            ]
            save_news_state()
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


def handle_direct_action(user_input):
    global last_screenshot_path, last_rate_limit_wait_text, last_browser_action
    lowered = user_input.lower().strip()

    did_something = False

    if is_acknowledgement(lowered):
        print("[Xyran] Theek hai.")
        return True

    if is_greeting(lowered):
        print("[Xyran] Hello! Kya help chahiye?")
        return True

    smalltalk_reply = get_local_smalltalk_reply(lowered)
    if smalltalk_reply:
        print(f"[Xyran] {smalltalk_reply}")
        return True

    if is_joke_request(lowered):
        print(f"[Xyran] {get_local_joke(pyjokes)}")
        return True

    if is_news_summary_request(lowered, bool(last_news_articles)):
        print("[Xyran] News ka summary bana raha hoon...")
        print(f"[Xyran] {summarize_news_article(user_input)}")
        return True

    if is_more_news_request(lowered, bool(last_news_query_signature)):
        print("[Xyran] Aur news la raha hoon...")
        print(f"[Xyran] {fetch_news_headlines(user_input)}")
        return True

    if is_news_request(lowered):
        print("[Xyran] News la raha hoon...")
        print(f"[Xyran] {fetch_news_headlines(user_input)}")
        return True

    if is_api_status_query(lowered):
        if last_rate_limit_wait_text:
            print(f"[Xyran] Abhi nahi, lagbhag {last_rate_limit_wait_text} baad phir try karna.")
        else:
            print("[Xyran] Haan, abhi try karke dekh sakte ho.")
        return True

    if is_open_youtube_request(lowered):
        print("[Xyran] YouTube handle kar raha hoon")
        message, last_browser_action = smart_open_youtube(user_input, run_command, last_browser_action)
        print(f"[Xyran] {message}")
        return True

    if is_browser_open_request(lowered):
        print("[Xyran] Browser khol raha hoon...")
        message = smart_open_browser(user_input, run_command)
        print(f"[Xyran] {message}")
        return True

    if is_explicit_website_request(lowered):
        website_target = extract_explicit_website_target(user_input)
        if not website_target:
            print("[Xyran] Website kholne ke liye exact URL ya domain chahiye, jaise `open github.com`.")
            return True
        print("[Xyran] Website khol raha hoon...")
        message = smart_open_website(website_target, user_input, run_command)
        print(f"[Xyran] {message}")
        return True

    if is_app_launch_request(lowered):
        app_result = resolve_app_launch(user_input, run_command, command_failed)
        if app_result:
            print(f"[Xyran] {app_result['label']} khol raha hoon")
            print(f"[CMD] {app_result['command']}")
            if app_result["output"] and app_result["output"] != "Done.":
                print(f"[Output] {app_result['output']}")
            if command_failed(app_result["output"]):
                print("[Xyran] Ye app sahi se open nahi hui.")
            elif app_result["requested_app"] != app_result["resolved_key"]:
                print(f"[Xyran] `{app_result['requested_app']}` ko `{app_result['label']}` samajh kar khol diya.")
            else:
                print("[Xyran] Ho gaya.")
            return True

    if is_ambiguous_open_request(lowered):
        requested_app = extract_requested_app_name(user_input) or "yeh"
        print(f"[Xyran] `{requested_app}` mujhe known app ya clear website nahi laga, isliye guess karke kuch open nahi kar raha. App naam ya exact domain bolo.")
        return True

    if is_rate_limit_time_query(lowered):
        if last_rate_limit_wait_text:
            print(f"[Xyran] Lagbhag {last_rate_limit_wait_text} baad phir try kar sakte ho.")
        else:
            print("[Xyran] Abhi mere paas exact wait time saved nahi hai.")
        return True

    if is_python_file_request(lowered):
        code_to_write = extract_python_code_request(user_input)
        file_path = prepare_python_file(code_to_write)
        open_command = get_editor_open_command(file_path)

        if code_to_write:
            print("[Xyran] Nayi Python file bana raha hoon aur code likh raha hoon")
        else:
            print("[Xyran] Nayi Python file bana raha hoon")

        if open_command:
            print(f"[CMD] {open_command}")
            output = run_command(open_command)
            if output and output != "Done.":
                print(f"[Output] {output}")
                if command_failed(output):
                    print("[Xyran] File banana ho gaya, lekin editor khul nahi paya.")
                    return True

        if code_to_write:
            print(f"[Xyran] `{code_to_write}` likh diya: {file_path}")
        else:
            print(f"[Xyran] Python file bana di: {file_path}")
        return True

    screenshot_requested = is_screenshot_request(lowered)

    if is_text_editor_request(lowered):
        editor = get_available_text_editor()
        if not editor:
            print("[Xyran] Koi supported text editor nahi mila. `gnome-text-editor` ya `gedit` install hona chahiye.")
            return True

        text_to_write = extract_text_to_write(user_input)
        file_path = prepare_editor_file(text_to_write)

        if text_to_write:
            print(f"[Xyran] {editor} khol raha hoon aur file mein text likh diya hai")
        else:
            print(f"[Xyran] {editor} khol raha hoon")

        print(f"[CMD] {editor} \"{file_path}\" &")
        output = run_command(f'{editor} "{file_path}" &')
        if output and output != "Done.":
            print(f"[Output] {output}")
            if command_failed(output):
                print("[Xyran] File ban gayi, lekin editor khul nahi paya.")
                return True

        if text_to_write:
            print(f"[Xyran] `{text_to_write}` file mein likh diya aur editor khol diya: {file_path}")
        else:
            print(f"[Xyran] Editor khol diya: {file_path}")
        did_something = True
        if not screenshot_requested:
            return True

    if is_files_open_request(lowered):
        print("[Xyran] Files app khol raha hoon")
        print("[CMD] nautilus &")
        output = run_command("nautilus &")
        if output and output != "Done.":
            print(f"[Output] {output}")
        if not command_failed(output):
            print("[Xyran] Ho gaya.")
        else:
            print("[Xyran] Ye command sahi se run nahi hui.")
        did_something = True

    if screenshot_requested:
        if is_text_editor_request(lowered):
            time.sleep(1.2)
        print("[Xyran] Screenshot le raha hoon...")
        temp_path, err = take_screenshot()
        if not temp_path:
            print(f"[Xyran] Screenshot nahi le paya: {err}")
            return True

        saved_path = save_screenshot_copy(temp_path, AI_NAME)
        os.remove(temp_path)
        last_screenshot_path = saved_path

        if wants_to_show_screenshot(lowered):
            print(f"[CMD] xdg-open \"{saved_path}\" &")
            output = run_command(f'xdg-open "{saved_path}" &')
            if output and output != "Done.":
                print(f"[Output] {output}")
            print(f"[Xyran] Screenshot save bhi ho gaya aur khol bhi diya: {saved_path}")
        else:
            print(f"[Xyran] Screenshot save ho gaya: {saved_path}")
        did_something = True

    if "last screenshot" in lowered or "pichla screenshot" in lowered or "kaha hai screenshot" in lowered:
        if not last_screenshot_path:
            print("[Xyran] Abhi tak koi screenshot save nahi hua hai.")
            return True
        if wants_to_show_screenshot(lowered):
            print(f"[CMD] xdg-open \"{last_screenshot_path}\" &")
            output = run_command(f'xdg-open "{last_screenshot_path}" &')
            if output and output != "Done.":
                print(f"[Output] {output}")
            print(f"[Xyran] Yeh raha last screenshot: {last_screenshot_path}")
        else:
            print(f"[Xyran] Last screenshot yahan saved hai: {last_screenshot_path}")
        return True

    if did_something:
        return True

    return False


def ask_xyran(user_input, screen_context=None):
    global last_rate_limit_wait_text, last_provider_used
    content = user_input
    if screen_context:
        content = f"[SCREEN CONTEXT]\n{screen_context}\n\n[USER COMMAND]\n{user_input}"

    conversation_history.append({"role": "user", "content": content})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=600
        )
        last_provider_used = "groq"
    except RateLimitError as e:
        if has_fallback_provider():
            try:
                reply = call_fallback_chat(messages, MODEL, temperature=0.2, max_tokens=600)
                last_provider_used = "fallback"
                conversation_history.append({"role": "assistant", "content": reply})
                return reply
            except Exception:
                pass
        wait_match = re.search(r"Please try again in ([0-9hms.]+)", str(e))
        wait_text = humanize_wait_time(wait_match.group(1)) if wait_match else "thodi der"
        last_rate_limit_wait_text = wait_text
        return json.dumps({
            "action": "answer",
            "message": f"Groq API ka daily token limit hit ho gaya hai. Lagbhag {wait_text} baad phir try karo, ya direct local commands use karo. Agar fallback provider set hoga to next time auto-switch ho jayega."
        })

    reply = response.choices[0].message.content.strip()
    conversation_history.append({"role": "assistant", "content": reply})
    return reply


def ask_xyran_with_image(user_input, image_path):
    global last_rate_limit_wait_text, last_provider_used
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_data}"}
                },
                {
                    "type": "text",
                    "text": (
                        f"Screenshot ko bahut dhyan se dekho.\n"
                        f"Left sidebar, launcher, dock, app grid, pinned icons aur task icons ko IGNORE karo.\n"
                        f"Un icons se app ya website infer mat karo.\n"
                        f"Sabse pehle center/front mein jo active ya topmost window hai usko identify karo.\n"
                        f"Uske baad background mein jo aur windows visible hain unko mention karo.\n"
                        f"Sirf main visible foreground content batao.\n"
                        f"Answer karte waqt in cheezon ko separately check karo:\n"
                        f"1) Sabse aage/topmost window ka app naam aur usme kya screen dikh rahi hai?\n"
                        f"2) Uske peeche aur kaunsi windows visible hain?\n"
                        f"3) Browser/tab/website ka naam tabhi batao jab screenshot mein clearly readable ho.\n"
                        f"4) Terminal text tabhi quote karo jab readable ho, warna bolo readable nahi hai.\n"
                        f"5) Agar code editor/file explorer/file manager visible ho, to readable file names aur folder names list karo.\n"
                        f"6) Agar settings/dialog/system window visible ho, to uske section names ya options bhi batao.\n"
                        f"7) Agar certainty low ho toh clearly mention karo ki exact cheez identify nahi ho rahi.\n"
                        f"8) Pichhle messages ya common patterns ke basis par guess mat karo.\n"
                        f"Answer ko short structured Hinglish mein do: 'Front window:', 'Also visible:', 'Readable items:'.\n"
                        f"User ka command: {user_input}\n"
                        f"JSON format mein jawab do."
                    )
                }
            ]
        }
    ]

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages,
            temperature=0,
            max_tokens=600
        )
        last_provider_used = "groq"
    except RateLimitError:
        if has_fallback_provider():
            try:
                reply = call_fallback_chat(
                    messages,
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                    temperature=0,
                    max_tokens=600
                )
                last_provider_used = "fallback"
                return reply
            except Exception:
                pass
        last_rate_limit_wait_text = "thodi der"
        return json.dumps({
            "action": "answer",
            "message": "Vision API ka token limit hit ho gaya hai, isliye abhi screenshot analyze nahi kar pa raha. Thodi der baad phir try karo, ya fallback provider configure karo."
        })

    reply = response.choices[0].message.content.strip()
    return reply


def clean_json(reply):
    if "```" in reply:
        parts = reply.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            if part.startswith("{"):
                return part.strip()
    return reply.strip()


def process_response(reply):
    reply = clean_json(reply)
    try:
        data = json.loads(reply)
        action = data.get("action")
        explain = data.get("explain", "")

        if explain:
            print(f"\n[Xyran] {explain}")

        if action in ("run", "look_and_act"):
            command = str(data.get("command", "")).strip()
            if command.lower() in ("", "none", "null", "n/a", "no command"):
                print("\n[Xyran] Main iske liye koi valid command identify nahi kar paya. Jo visible hai usi ke basis par answer dena better hoga.")
                return
            print(f"[CMD] {command}")
            output = run_command(command)
            if output and output != "Done.":
                if len(output) > 300:
                    summary = summarize_output(output)
                    print(f"\n[Xyran] {summary}")
                else:
                    print(f"[Output] {output}")
            if not command_failed(output):
                print(f"[Xyran] Ho gaya.")
            else:
                print(f"[Xyran] Ye command sahi se run nahi hui.")

        elif action == "run_multi":
            commands = [
                str(cmd).strip() for cmd in data.get("commands", [])
                if str(cmd).strip().lower() not in ("", "none", "null", "n/a", "no command")
            ]
            if not commands:
                print("\n[Xyran] Koi valid commands nahi mile, isliye main kuch run nahi kar raha.")
                return
            had_failure = False
            for cmd in commands:
                print(f"[CMD] {cmd}")
                output = run_command(cmd)
                if output and output != "Done.":
                    if len(output) > 300:
                        summary = summarize_output(output)
                        print(f"\n[Xyran] {summary}")
                    else:
                        print(f"[Output] {output}")
                if command_failed(output):
                    had_failure = True
            if not had_failure:
                print(f"[Xyran] Sab ho gaya.")
            else:
                print(f"[Xyran] Kuch commands sahi se run nahi hui.")

        elif action == "answer":
            message = data.get("message", "")
            print(f"\n[Xyran] {message}")

    except json.JSONDecodeError:
        print(f"\n[Xyran] {reply}")


def main():
    global last_input_used_vision, vision_followup_turns_left
    load_news_state()
    print(f"""
╔══════════════════════════════════════════╗
║         XYRAN AI v2 - ONLINE             ║
║   Brain + Aankhein — Dono Ready Hain     ║
╚══════════════════════════════════════════╝
'exit' likho band karne ke liye.
""")

    while True:
        try:
            user_input = input(f"[{USER_NAME}] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "band karo"):
                print("[Xyran] Theek hai. Phir milenge.")
                break

            if handle_direct_action(user_input):
                last_input_used_vision = False
                continue

            use_vision = (
                should_use_vision(user_input)
                or (last_input_used_vision and is_vision_followup(user_input))
                or (vision_followup_turns_left > 0 and is_ambiguous_short_followup(user_input))
            )

            if use_vision:
                print("[Xyran] Screen dekh raha hoon...")
                img_path, err = take_screenshot()
                if img_path:
                    reply = ask_xyran_with_image(user_input, img_path)
                    os.remove(img_path)
                else:
                    print(f"[Xyran] Screenshot nahi le paya: {err}")
                    reply = ask_xyran(user_input)
                last_input_used_vision = True
                vision_followup_turns_left = 2
            else:
                reply = ask_xyran(user_input)
                last_input_used_vision = False
                if vision_followup_turns_left > 0:
                    vision_followup_turns_left -= 1

            process_response(reply)

        except KeyboardInterrupt:
            print("\n[Xyran] Band ho raha hoon.")
            break
        except RateLimitError:
            print("\n[Xyran] Groq API rate limit hit ho gaya hai. Thodi der baad phir try karo.")
        except Exception as e:
            print(f"\n[Xyran] Error aaya: {e}")


if __name__ == "__main__":
    main()
