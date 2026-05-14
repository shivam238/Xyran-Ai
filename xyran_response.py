import json


def process_response(reply, run_command, command_failed, summarize_output, clean_json):
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
                    print(f"\n[Xyran] {summarize_output(output)}")
                else:
                    print(f"[Output] {output}")
            if not command_failed(output):
                print("[Xyran] Ho gaya.")
            else:
                print("[Xyran] Ye command sahi se run nahi hui.")

        elif action == "run_multi":
            commands = [
                str(cmd).strip() for cmd in data.get("commands", [])
                if str(cmd).strip().lower() not in ("", "none", "null", "n/a", "no command")
            ]
            if not commands:
                print("\n[Xyran] Koi valid commands nahi mile, isliye main kuch run nahi kar raha.")
                return
            had_failure = False
            for command in commands:
                print(f"[CMD] {command}")
                output = run_command(command)
                if output and output != "Done.":
                    if len(output) > 300:
                        print(f"\n[Xyran] {summarize_output(output)}")
                    else:
                        print(f"[Output] {output}")
                if command_failed(output):
                    had_failure = True
            if not had_failure:
                print("[Xyran] Sab ho gaya.")
            else:
                print("[Xyran] Kuch commands sahi se run nahi hui.")

        elif action == "answer":
            message = data.get("message", "")
            print(f"\n[Xyran] {message}")

    except json.JSONDecodeError:
        print(f"\n[Xyran] {reply}")
