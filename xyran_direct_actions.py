import os
import re
import time
from datetime import datetime
from modules.image_gen.handler import handle_image

from config import AI_NAME
from vision import take_screenshot
from xyran_search import has_action_connector, search_consumes_open_phrase
from xyran_app_utils import (
    resolve_app_launch,
    resolve_known_website,
    save_screenshot_copy,
    smart_open_browser,
    smart_search_web,
    smart_open_website,
    smart_open_youtube,
)
from xyran_input_utils import (
    extract_explicit_website_target,
    extract_code_topic_request,
    extract_generated_note_request,
    extract_python_code_request,
    extract_requested_app_name,
    extract_text_to_write,
    extract_web_search_query,
    get_available_text_editor,
    get_editor_open_command,
    generate_code_from_topic,
    get_local_joke,
    get_local_smalltalk_reply,
    is_acknowledgement,
    is_ambiguous_open_request,
    is_api_status_query,
    is_app_launch_request,
    is_browser_open_request,
    is_explicit_website_request,
    is_files_open_request,
    is_greeting,
    is_joke_request,
    is_more_news_request,
    is_news_request,
    is_news_summary_request,
    is_open_youtube_request,
    is_python_file_request,
    is_rate_limit_time_query,
    is_screenshot_request,
    is_text_editor_request,
    wants_to_show_screenshot,
    is_dnd_request,
    extract_dnd_action,
    is_keyboard_light_request,
    extract_keyboard_light_action,
    extract_keyboard_light_brightness,
    is_screen_brightness_request,
    extract_screen_brightness_percent,
    percent_to_screen_raw,
    SCREEN_BACKLIGHT_PATH,
)


def prepare_editor_file(runtime_state, initial_text=None):
    folder = os.path.expanduser(f"~/Documents/{AI_NAME}")
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = os.path.join(folder, f"note-{timestamp}.txt")
    with open(file_path, "w", encoding="utf-8") as file_obj:
        if initial_text:
            file_obj.write(initial_text)
            if not initial_text.endswith("\n"):
                file_obj.write("\n")
    runtime_state.last_editor_file_path = file_path
    return file_path


def prepare_python_file(runtime_state, initial_code=None):
    folder = os.path.expanduser(f"~/Documents/{AI_NAME}")
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = os.path.join(folder, f"script-{timestamp}.py")
    with open(file_path, "w", encoding="utf-8") as file_obj:
        if initial_code:
            file_obj.write(initial_code)
            if not initial_code.endswith("\n"):
                file_obj.write("\n")
    runtime_state.last_created_code_file = file_path
    return file_path


def _normalize_tokens(text):
    return {
        token
        for token in re.findall(r"[a-zA-Z]+", (text or "").lower())
        if len(token) > 2
    }


def should_write_last_answer(user_input, extracted_text, runtime_state):
    if not extracted_text or not runtime_state.last_assistant_text or not runtime_state.prev_user_input:
        return False

    lowered = user_input.lower()
    if "code" in lowered:
        return False
    if "write " in lowered:
        return False
    if len(runtime_state.last_assistant_text.strip()) < 80:
        return False

    explicit_note_phrases = [
        "notepad me likh", "notepad me likho", "notepad me likhna",
        "notpad me likh", "notpad me likho", "notpad me likhna",
        "notrpad me likh", "notrpad me likho", "notrpad me likhna",
        "editor me likh", "editor me likho", "editor me likhna",
    ]
    if not any(phrase in lowered for phrase in explicit_note_phrases):
        return False

    current_tokens = _normalize_tokens(extracted_text)
    previous_user_tokens = _normalize_tokens(runtime_state.prev_user_input)
    overlap = current_tokens & previous_user_tokens
    return len(overlap) >= 2


def handle_direct_action(user_input, runtime_state, news_manager, pyjokes_module, run_command, command_failed, ai=None):
    lowered = user_input.lower().strip()
    did_something = False

    # FLAGS FIRST (IMPORTANT)
    screenshot_requested = is_screenshot_request(lowered)
    text_editor_requested = is_text_editor_request(lowered)
    compound_requested = has_action_connector(lowered)

    search_query = extract_web_search_query(user_input)
    search_requested = bool(search_query)
    search_handles_browser_open = search_requested and search_consumes_open_phrase(user_input)

    known_website = resolve_known_website(user_input)

    # NOW SAFE TO DEFINE THIS
    continue_after_action = screenshot_requested or compound_requested

    youtube_handled = False
    search_handled = False

    # IMAGE GENERATION (NEW MODULE)
    image_result = handle_image(user_input, AI_NAME)
    if image_result:
        print(image_result)
        did_something = True
        if not continue_after_action:
            return True

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
        print(f"[Xyran] {get_local_joke(pyjokes_module)}")
        return True

    prev_cat = runtime_state.last_action_category if runtime_state else None

    if is_dnd_request(lowered, prev_action_category=prev_cat):
        action = extract_dnd_action(user_input, runtime_state.prev_user_input if runtime_state else None, prev_action_category=prev_cat)
        if action == "on":
            msg = "Do Not Disturb mode on kar raha hoon."
            cmd = "gsettings set org.gnome.desktop.notifications show-banners false"
        else:
            msg = "Do Not Disturb mode off kar raha hoon."
            cmd = "gsettings set org.gnome.desktop.notifications show-banners true"
        
        print(f"[Xyran] {msg}")
        print(f"[CMD] {cmd}")
        output = run_command(cmd)
        if output and output != "Done.":
            print(f"[Output] {output}")
        if command_failed(output):
            print("[Xyran] Do Not Disturb toggling fail ho gaya.")
            if ai:
                ai.conversation_history.append({"role": "user", "content": user_input})
                ai.conversation_history.append({"role": "assistant", "content": f"{msg} Lekin toggling fail ho gaya."})
        else:
            print("[Xyran] Ho gaya.")
            if runtime_state:
                runtime_state.last_action_category = "dnd"
            if ai:
                ai.conversation_history.append({"role": "user", "content": user_input})
                ai.conversation_history.append({"role": "assistant", "content": f"{msg} Ho gaya."})
        return True

    if is_keyboard_light_request(lowered, prev_action_category=prev_cat):
        brightness = extract_keyboard_light_brightness(user_input, runtime_state.prev_user_input if runtime_state else None, prev_action_category=prev_cat)
        if brightness == 0:
            msg = "Keyboard wali light off kar raha hoon."
        else:
            msg = f"Keyboard wali light {brightness}% brightness pe set kar raha hoon."
            
        print(f"[Xyran] {msg}")
        cmd = f'gdbus call --session --dest org.gnome.SettingsDaemon.Power --object-path /org/gnome/SettingsDaemon/Power --method org.freedesktop.DBus.Properties.Set org.gnome.SettingsDaemon.Power.Keyboard Brightness "<int32 {brightness}>"'
        print(f"[CMD] {cmd}")
        output = run_command(cmd)
        if output and output != "Done.":
            print(f"[Output] {output}")
        if command_failed(output):
            print("[Xyran] Keyboard light setting fail ho gaya.")
            if ai:
                ai.conversation_history.append({"role": "user", "content": user_input})
                ai.conversation_history.append({"role": "assistant", "content": f"{msg} Lekin setting fail ho gaya."})
        else:
            print("[Xyran] Ho gaya.")
            if runtime_state:
                runtime_state.last_action_category = "keyboard"
            if ai:
                ai.conversation_history.append({"role": "user", "content": user_input})
                ai.conversation_history.append({"role": "assistant", "content": f"{msg} Ho gaya."})
        return True

    if is_screen_brightness_request(user_input, prev_action_category=prev_cat):
        current_pct = runtime_state.last_screen_brightness_percent if runtime_state else None
        percent = extract_screen_brightness_percent(user_input, current_percent=current_pct)
        raw = percent_to_screen_raw(percent)
        brightness_file = f"{SCREEN_BACKLIGHT_PATH}/brightness"
        msg = f"Screen brightness {percent}% par set kar raha hoon."
        print(f"[Xyran] {msg}")
        try:
            with open(brightness_file, "w") as bf:
                bf.write(str(raw))
            print(f"[Xyran] Ho gaya. ({raw}/{percent_to_screen_raw(100)})")  
            if runtime_state:
                runtime_state.last_action_category = "screen"
                runtime_state.last_screen_brightness_percent = percent
            if ai:
                ai.conversation_history.append({"role": "user", "content": user_input})
                ai.conversation_history.append({"role": "assistant", "content": f"{msg} Ho gaya."})
        except PermissionError:
            print("[Xyran] Permission denied. Pehle terminal mein yeh run karo:")
            print("  sudo chgrp video /sys/class/backlight/intel_backlight/brightness")
            print("  sudo chmod g+w /sys/class/backlight/intel_backlight/brightness")
            print("[Xyran] (Yeh ek-baar karna hoga, reboot ke baad udev rule se automatic hoga)")
        except FileNotFoundError:
            print("[Xyran] Backlight path nahi mila. intel_backlight support nahi hai is system pe.")
        return True

    if is_news_summary_request(lowered, bool(news_manager.last_news_articles)):
        print("[Xyran] News ka summary bana raha hoon...")
        print(f"[Xyran] {news_manager.summarize_article(user_input)}")
        return True

    if is_more_news_request(lowered, bool(news_manager.last_news_query_signature)):
        print("[Xyran] Aur news la raha hoon...")
        print(f"[Xyran] {news_manager.fetch_headlines(user_input)}")
        return True

    if is_news_request(lowered):
        print("[Xyran] News la raha hoon...")
        print(f"[Xyran] {news_manager.fetch_headlines(user_input)}")
        return True

    if is_api_status_query(lowered):
        if runtime_state.last_rate_limit_wait_text:
            print(f"[Xyran] Abhi nahi, lagbhag {runtime_state.last_rate_limit_wait_text} baad phir try karna.")
        else:
            print("[Xyran] Haan, abhi try karke dekh sakte ho.")
        return True

    if is_open_youtube_request(lowered):
        print("[Xyran] YouTube handle kar raha hoon")
        message, runtime_state.last_browser_action = smart_open_youtube(
            user_input,
            run_command,
            runtime_state.last_browser_action,
        )
        print(f"[Xyran] {message}")
        youtube_handled = True
        did_something = True
        if not continue_after_action:
            return True

    if search_handles_browser_open:
        print("[Xyran] Web search kar raha hoon...")
        message = smart_search_web(search_query, user_input, run_command)
        print(f"[Xyran] {message}")
        search_handled = True
        did_something = True
        if not continue_after_action:
            return True

    if is_browser_open_request(lowered) and not search_handles_browser_open:
        print("[Xyran] Browser khol raha hoon...")
        message = smart_open_browser(user_input, run_command)
        print(f"[Xyran] {message}")
        did_something = True
        if not continue_after_action:
            return True

    if known_website and not youtube_handled:
        if search_handles_browser_open and known_website["resolved_key"] == "google":
            pass
        else:
            print("[Xyran] Website khol raha hoon...")
            message = smart_open_website(known_website["website"], user_input, run_command)
            print(f"[Xyran] {message}")
            did_something = True
            if not continue_after_action:
                return True

    if is_explicit_website_request(lowered):
        website_target = extract_explicit_website_target(user_input)
        if not website_target:
            print("[Xyran] Website kholne ke liye exact URL ya domain chahiye, jaise `open github.com`.")
            return True
        print("[Xyran] Website khol raha hoon...")
        message = smart_open_website(website_target, user_input, run_command)
        print(f"[Xyran] {message}")
        did_something = True
        if not continue_after_action:
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
            did_something = True
            if not continue_after_action:
                return True

    if search_requested and not search_handled:
        print("[Xyran] Web search kar raha hoon...")
        message = smart_search_web(search_query, user_input, run_command)
        print(f"[Xyran] {message}")
        did_something = True
        if not continue_after_action:
            return True

    if is_ambiguous_open_request(lowered):
        requested_app = extract_requested_app_name(user_input) or "yeh"
        print(f"[Xyran] `{requested_app}` mujhe known app ya clear website nahi laga. App naam, exact domain, ya `search {requested_app}` jaisa bolo.")
        return True

    if is_rate_limit_time_query(lowered):
        if runtime_state.last_rate_limit_wait_text:
            print(f"[Xyran] Lagbhag {runtime_state.last_rate_limit_wait_text} baad phir try kar sakte ho.")
        else:
            print("[Xyran] Abhi mere paas exact wait time saved nahi hai.")
        return True

    if is_python_file_request(lowered):
        code_to_write = extract_python_code_request(user_input)
        file_path = prepare_python_file(runtime_state, code_to_write)
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

    if text_editor_requested:
        editor = get_available_text_editor()
        if not editor:
            print("[Xyran] Koi supported text editor nahi mila. `gnome-text-editor` ya `gedit` install hona chahiye.")
            return True

        code_snippet = generate_code_from_topic(user_input)
        generated_note_request = None if code_snippet else extract_generated_note_request(user_input)
        text_to_write = code_snippet or extract_text_to_write(user_input)
        if should_write_last_answer(user_input, text_to_write, runtime_state):
            text_to_write = runtime_state.last_assistant_text
        elif generated_note_request and ai:
            try:
                content_type = generated_note_request["type"]
                topic = generated_note_request["topic"]
                generated_text = ai.generate_text_reply(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You write concise, clean study/help content in simple English. "
                                "Return only the requested content as plain text. No JSON, no markdown fences."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Write a {content_type} on {topic}. Keep it clear and natural.",
                        },
                    ],
                    user_input=f"write a {content_type} on {topic}",
                    temperature=0.4,
                    max_tokens=500,
                )
                text_to_write = generated_text.strip()
            except Exception:
                pass
        file_path = prepare_editor_file(runtime_state, text_to_write)

        if code_snippet:
            print(f"[Xyran] {editor} khol raha hoon aur code file mein likh diya hai")
        elif generated_note_request and text_to_write and text_to_write != extract_text_to_write(user_input):
            print(f"[Xyran] {editor} khol raha hoon aur generated content file mein likh diya hai")
        elif text_to_write:
            print(f"[Xyran] {editor} khol raha hoon aur file mein text likh diya hai")
        else:
            print(f"[Xyran] {editor} khol raha hoon")

        # Wayland focus fix: Force a NEW window so the compositor grants focus
        editor_cmd = editor
        if editor in ("gnome-text-editor", "gedit"):
            editor_cmd = f"{editor} --new-window"

        print(f"[CMD] {editor_cmd} \"{file_path}\" &")
        output = run_command(f'{editor_cmd} "{file_path}" &')
        if output and output != "Done.":
            print(f"[Output] {output}")
            if command_failed(output):
                print("[Xyran] File ban gayi, lekin editor khul nahi paya.")
                return True

        if code_snippet:
            topic = extract_code_topic_request(user_input) or "requested"
            print(f"[Xyran] `{topic}` ka code file mein likh diya aur editor khol diya: {file_path}")
        elif generated_note_request and text_to_write and text_to_write != extract_text_to_write(user_input):
            topic = generated_note_request["topic"]
            print(f"[Xyran] `{topic}` ke liye generated content file mein likh diya aur editor khol diya: {file_path}")
        elif text_to_write:
            print(f"[Xyran] `{text_to_write}` file mein likh diya aur editor khol diya: {file_path}")
        else:
            print(f"[Xyran] Editor khol diya: {file_path}")
        did_something = True
        if not continue_after_action:
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
        if text_editor_requested:
            time.sleep(1.2)
        elif did_something:
            time.sleep(1.0)
        print("[Xyran] Screenshot le raha hoon...")
        temp_path, err = take_screenshot()
        if not temp_path:
            print(f"[Xyran] Screenshot nahi le paya: {err}")
            return True

        saved_path = save_screenshot_copy(temp_path, AI_NAME)
        os.remove(temp_path)
        runtime_state.last_screenshot_path = saved_path

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
        if not runtime_state.last_screenshot_path:
            print("[Xyran] Abhi tak koi screenshot save nahi hua hai.")
            return True
        if wants_to_show_screenshot(lowered):
            print(f"[CMD] xdg-open \"{runtime_state.last_screenshot_path}\" &")
            output = run_command(f'xdg-open "{runtime_state.last_screenshot_path}" &')
            if output and output != "Done.":
                print(f"[Output] {output}")
            print(f"[Xyran] Yeh raha last screenshot: {runtime_state.last_screenshot_path}")
        else:
            print(f"[Xyran] Last screenshot yahan saved hai: {runtime_state.last_screenshot_path}")
        return True

    return did_something
