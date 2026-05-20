import json


def process_response(reply, run_command, command_failed, summarize_output, clean_json, runtime_state):
    reply = clean_json(reply)
    try:
        data = json.loads(reply)
        action = data.get("action")
        explain = data.get("explain", "")

        if explain and action != "answer":
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
                    print(f"\n[Xyran] {summarize_output(output)}")
                else:
                    print(f"[Output] {output}")
            if not command_failed(output):
                print("[Xyran] Ho gaya.")
            else:
                print("[Xyran] Ye command sahi se run nahi hui.")

        elif action == "run_multi":
            import time
            # Support BOTH formats:
            # OLD: {"commands": ["cmd1", "cmd2"]}
            # NEW: {"steps": [{"cmd": "...", "delay": 2}, ...]}
            steps = data.get("steps", None)
            if steps and isinstance(steps, list):
                # New smart format with per-step delays
                valid_steps = [
                    s for s in steps
                    if isinstance(s, dict) and str(s.get("cmd", "")).strip().lower()
                    not in ("", "none", "null", "n/a", "no command")
                ]
                if not valid_steps:
                    print("\n[Xyran] Koi valid steps nahi mile, isliye main kuch run nahi kar raha.")
                    return
                had_failure = False
                last_screenshot_path = None
                for i, step in enumerate(valid_steps):
                    cmd = str(step["cmd"]).strip()
                    delay = float(step.get("delay", 0.5))

                    # --- Internal screenshot handler ---
                    if cmd.lower() in ("screenshot", "take_screenshot"):
                        print(f"[Step {i+1}/{len(valid_steps)}] Screenshot le raha hoon...")
                        from vision import take_screenshot
                        from xyran_app_utils import save_screenshot_copy
                        from config import AI_NAME
                        temp_path, err = take_screenshot()
                        if temp_path:
                            import os
                            saved_path = save_screenshot_copy(temp_path, AI_NAME)
                            os.remove(temp_path)
                            last_screenshot_path = saved_path
                            runtime_state.last_screenshot_path = saved_path
                            print(f"[Xyran] Screenshot saved: {saved_path}")
                        else:
                            print(f"[Xyran] Screenshot nahi le paya: {err}")
                            had_failure = True

                    # --- Internal open last screenshot ---
                    elif cmd.lower() in ("open_screenshot", "show_screenshot"):
                        path_to_open = last_screenshot_path or getattr(runtime_state, 'last_screenshot_path', None)
                        if path_to_open:
                            print(f"[Step {i+1}/{len(valid_steps)}] Screenshot open kar raha hoon...")
                            run_command(f'xdg-open "{path_to_open}" &')
                            print(f"[Xyran] Screenshot khol diya: {path_to_open}")
                        else:
                            print(f"[Step {i+1}/{len(valid_steps)}] Koi screenshot nahi mila open karne ke liye.")
                            had_failure = True

                    # --- Normal shell command ---
                    else:
                        print(f"[Step {i+1}/{len(valid_steps)}] {cmd}")
                        output = run_command(cmd)
                        if output and output != "Done.":
                            if len(output) > 300:
                                print(f"\n[Xyran] {summarize_output(output)}")
                            else:
                                print(f"[Output] {output}")
                        if command_failed(output):
                            had_failure = True
                            print(f"[Xyran] Step {i+1} fail hua, aage continue kar raha hoon...")

                    if delay > 0 and i < len(valid_steps) - 1:
                        time.sleep(delay)
            else:
                # Old simple format: list of command strings
                commands = [
                    str(cmd).strip() for cmd in data.get("commands", [])
                    if str(cmd).strip().lower() not in ("", "none", "null", "n/a", "no command")
                ]
                if not commands:
                    print("\n[Xyran] Koi valid commands nahi mile, isliye main kuch run nahi kar raha.")
                    return
                had_failure = False
                for i, command in enumerate(commands):
                    print(f"[CMD] {command}")
                    output = run_command(command)
                    if output and output != "Done.":
                        if len(output) > 300:
                            print(f"\n[Xyran] {summarize_output(output)}")
                        else:
                            print(f"[Output] {output}")
                    if command_failed(output):
                        had_failure = True
                    # Auto-delay between commands for GUI stability
                    if i < len(commands) - 1:
                        time.sleep(0.5)

            if not had_failure:
                print("[Xyran] Sab ho gaya.")
            else:
                print("[Xyran] Kuch steps sahi se run nahi hui.")

        elif action == "answer":
            message = data.get("message", "")
            runtime_state.last_assistant_text = message
            print(f"\n[Xyran] {message}")

        elif action == "remember":
            category = data.get("category", "facts")
            content = data.get("content", "")
            key = data.get("key", "")
            value = data.get("value", "")
            explain = data.get("explain", "")

            msg = ""
            if category == "facts" and key and value:
                from xyran_brain import set_fact
                set_fact(key, value)
                msg = f"Maine yaad rakh liya ki aapka {key} '{value}' hai."
            elif content:
                from xyran_memory import remember as remember_json
                remember_json(category, content)
                msg = f"Maine yaad rakh liya: {content}"
            else:
                msg = "Invalid remember format."

            if explain:
                runtime_state.last_assistant_text = explain
            else:
                print(f"\n[Xyran] {msg}")
                runtime_state.last_assistant_text = msg

    except json.JSONDecodeError:
        runtime_state.last_assistant_text = reply
        print(f"\n[Xyran] {reply}")
