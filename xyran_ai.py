import base64
import json
import re
import urllib.request

from groq import RateLimitError

from xyran_input_utils import humanize_wait_time


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


class XyranAI:
    def __init__(
        self,
        *,
        client,
        model,
        system_prompt,
        vision_system_prompt,
        fallback_api_key,
        fallback_model,
        fallback_base_url,
        runtime_state,
    ):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.vision_system_prompt = vision_system_prompt
        self.fallback_api_key = fallback_api_key
        self.fallback_model = fallback_model
        self.fallback_base_url = fallback_base_url
        self.runtime_state = runtime_state
        self.conversation_history = []

    def has_fallback_provider(self):
        return bool(self.fallback_api_key and self.fallback_model and self.fallback_base_url)

    def call_fallback_chat(self, messages, model, temperature=0.2, max_tokens=600):
        payload = {
            "model": self.fallback_model or model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.fallback_base_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.fallback_api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()

    def summarize_output(self, output):
        try:
            followup = self.client.chat.completions.create(
                model=self.model,
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
            summary_json = json.loads(summary_data)
            return summary_json.get("message", output[:200])
        except Exception:
            return output[:200]

    def ask(self, user_input, screen_context=None):
        content = user_input
        if screen_context:
            content = f"[SCREEN CONTEXT]\n{screen_context}\n\n[USER COMMAND]\n{user_input}"

        self.conversation_history.append({"role": "user", "content": content})
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=600
            )
            self.runtime_state.last_provider_used = "groq"
        except RateLimitError as e:
            if self.has_fallback_provider():
                try:
                    reply = self.call_fallback_chat(messages, self.model, temperature=0.2, max_tokens=600)
                    self.runtime_state.last_provider_used = "fallback"
                    self.conversation_history.append({"role": "assistant", "content": reply})
                    return reply
                except Exception:
                    pass
            wait_match = re.search(r"Please try again in ([0-9hms.]+)", str(e))
            wait_text = humanize_wait_time(wait_match.group(1)) if wait_match else "thodi der"
            self.runtime_state.last_rate_limit_wait_text = wait_text
            return json.dumps({
                "action": "answer",
                "message": f"Groq API ka daily token limit hit ho gaya hai. Lagbhag {wait_text} baad phir try karo, ya direct local commands use karo. Agar fallback provider set hoga to next time auto-switch ho jayega."
            })

        reply = response.choices[0].message.content.strip()
        self.conversation_history.append({"role": "assistant", "content": reply})
        return reply

    def ask_with_image(self, user_input, image_path):
        with open(image_path, "rb") as file_obj:
            image_data = base64.standard_b64encode(file_obj.read()).decode("utf-8")

        messages = [
            {"role": "system", "content": self.vision_system_prompt},
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
            response = self.client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=messages,
                temperature=0,
                max_tokens=600
            )
            self.runtime_state.last_provider_used = "groq"
        except RateLimitError:
            if self.has_fallback_provider():
                try:
                    reply = self.call_fallback_chat(
                        messages,
                        "meta-llama/llama-4-scout-17b-16e-instruct",
                        temperature=0,
                        max_tokens=600
                    )
                    self.runtime_state.last_provider_used = "fallback"
                    return reply
                except Exception:
                    pass
            self.runtime_state.last_rate_limit_wait_text = "thodi der"
            return json.dumps({
                "action": "answer",
                "message": "Vision API ka token limit hit ho gaya hai, isliye abhi screenshot analyze nahi kar pa raha. Thodi der baad phir try karo, ya fallback provider configure karo."
            })

        return response.choices[0].message.content.strip()
