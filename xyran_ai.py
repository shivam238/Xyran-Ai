import base64
import json
import re
import urllib.error
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
        groq_api_key,
        model,
        gemini_api_key,
        gemini_model,
        provider_mode,
        system_prompt,
        vision_system_prompt,
        fallback_api_key,
        fallback_model,
        fallback_base_url,
        runtime_state,
    ):
        self.client = client
        self.groq_api_key = groq_api_key
        self.model = model
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.provider_mode = provider_mode
        self.system_prompt = system_prompt
        self.vision_system_prompt = vision_system_prompt
        self.fallback_api_key = fallback_api_key
        self.fallback_model = fallback_model
        self.fallback_base_url = fallback_base_url
        self.runtime_state = runtime_state
        self.conversation_history = []

    def has_groq_provider(self):
        return bool(self.client and self.groq_api_key)

    def has_gemini_provider(self):
        return bool(self.gemini_api_key and self.gemini_model)

    def has_fallback_provider(self):
        return bool(self.fallback_api_key and self.fallback_model and self.fallback_base_url)

    def _call_openai_compatible_fallback(self, messages, model, temperature=0.2, max_tokens=600):
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

    def _call_groq_chat(self, messages, model, temperature=0.2, max_tokens=600):
        if not self.has_groq_provider():
            raise RuntimeError("Groq provider configured nahi hai.")
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _convert_messages_to_gemini_contents(self, messages):
        system_parts = []
        contents = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role == "system":
                if isinstance(content, str) and content.strip():
                    system_parts.append(content.strip())
                continue
            if not isinstance(content, str):
                continue
            text = content.strip()
            if not text:
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
        return "\n\n".join(system_parts).strip(), contents

    def _call_gemini_chat(self, messages, model, temperature=0.2, max_tokens=600):
        if not self.has_gemini_provider():
            raise RuntimeError("Gemini provider configured nahi hai.")

        system_instruction, contents = self._convert_messages_to_gemini_contents(messages)
        if not contents:
            raise RuntimeError("Gemini request ke liye valid content nahi mila.")

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))

        candidates = body.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini ne koi candidate return nahi kiya.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [part.get("text", "") for part in parts if part.get("text")]
        reply = "".join(text_parts).strip()
        if not reply:
            raise RuntimeError("Gemini response empty aaya.")
        return reply

    def _looks_complex_text_request(self, user_input, screen_context=None):
        lowered = user_input.lower().strip()
        complexity_keywords = [
            "why", "kaise", "explain", "compare", "difference", "optimize",
            "bug", "error", "debug", "fix", "architecture", "design",
            "refactor", "reason", "analyze", "analysis", "strategy",
            "plan", "improve", "smart", "intelligent", "code", "python",
        ]
        if screen_context:
            return True
        return len(lowered) > 220 or any(keyword in lowered for keyword in complexity_keywords)

    def _get_text_provider_order(self, user_input="", screen_context=None, preferred_order=None):
        if preferred_order:
            return [provider for provider in preferred_order if provider]

        mode = self.provider_mode or "smart"
        if mode == "gemini":
            base_order = ["gemini", "groq", "fallback"]
        elif mode == "groq":
            base_order = ["groq", "gemini", "fallback"]
        else:
            if self._looks_complex_text_request(user_input, screen_context):
                base_order = ["gemini", "groq", "fallback"]
            else:
                base_order = ["groq", "gemini", "fallback"]

        available = []
        for provider in base_order:
            if provider == "groq" and self.has_groq_provider():
                available.append(provider)
            elif provider == "gemini" and self.has_gemini_provider():
                available.append(provider)
            elif provider == "fallback" and self.has_fallback_provider():
                available.append(provider)
        return available

    def generate_text_reply(
        self,
        messages,
        *,
        user_input="",
        screen_context=None,
        preferred_order=None,
        temperature=0.2,
        max_tokens=600,
        fallback_model=None,
    ):
        provider_order = self._get_text_provider_order(
            user_input=user_input,
            screen_context=screen_context,
            preferred_order=preferred_order,
        )
        if not provider_order:
            raise RuntimeError("Koi text AI provider configured nahi hai.")

        errors = []
        target_model = fallback_model or self.model
        for provider in provider_order:
            try:
                if provider == "groq":
                    reply = self._call_groq_chat(messages, self.model, temperature=temperature, max_tokens=max_tokens)
                elif provider == "gemini":
                    reply = self._call_gemini_chat(messages, self.gemini_model, temperature=temperature, max_tokens=max_tokens)
                else:
                    reply = self._call_openai_compatible_fallback(messages, target_model, temperature=temperature, max_tokens=max_tokens)
                self.runtime_state.last_provider_used = provider
                return reply
            except RateLimitError as error:
                errors.append((provider, error))
            except urllib.error.HTTPError as error:
                errors.append((provider, error))
            except Exception as error:
                errors.append((provider, error))

        raise RuntimeError("; ".join(f"{provider}: {error}" for provider, error in errors))

    def call_fallback_chat(self, messages, model, temperature=0.2, max_tokens=600):
        preferred = []
        if self.has_gemini_provider():
            preferred.append("gemini")
        if self.has_fallback_provider():
            preferred.append("fallback")
        if not preferred:
            raise RuntimeError("Koi fallback text provider configured nahi hai.")
        return self.generate_text_reply(
            messages,
            preferred_order=preferred,
            temperature=temperature,
            max_tokens=max_tokens,
            fallback_model=model,
        )

    def summarize_output(self, output):
        try:
            summary_reply = self.generate_text_reply(
                [
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
                user_input=output,
                temperature=0.2,
                max_tokens=120,
            )
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
            reply = self.generate_text_reply(
                messages=messages,
                user_input=user_input,
                screen_context=screen_context,
                temperature=0.2,
                max_tokens=600,
            )
        except Exception as e:
            wait_match = re.search(r"Please try again in ([0-9hms.]+)", str(e))
            wait_text = humanize_wait_time(wait_match.group(1)) if wait_match else "thodi der"
            self.runtime_state.last_rate_limit_wait_text = wait_text
            return json.dumps({
                "action": "answer",
                "message": f"AI providers se reply nahi aa paya. Lagbhag {wait_text} baad phir try karo, ya direct local commands use karo. Agar Gemini/Groq/fallback configured honge to Xyran auto-switch karega."
            })

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
            if not self.has_groq_provider():
                raise RuntimeError("Groq vision provider configured nahi hai.")
            response = self.client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=messages,
                temperature=0,
                max_tokens=600
            )
            self.runtime_state.last_provider_used = "groq"
            return response.choices[0].message.content.strip()
        except RateLimitError:
            pass
        except Exception:
            pass

        if self.has_fallback_provider():
            try:
                reply = self._call_openai_compatible_fallback(
                    messages,
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                    temperature=0,
                    max_tokens=600,
                )
                self.runtime_state.last_provider_used = "fallback"
                return reply
            except Exception:
                pass

        self.runtime_state.last_rate_limit_wait_text = "thodi der"
        return json.dumps({
            "action": "answer",
            "message": "Vision API abhi available nahi hai. Thodi der baad phir try karo, ya Groq/OpenAI-compatible vision fallback configure karo."
        })
